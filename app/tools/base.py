"""Tool execution framework.

Every tool invocation flows through the same wrapper which, in order:

1. **Authorizes** the call against the caller's role (RBAC).
2. **Validates** the parameters against the tool's allow-list.
3. **Executes** with a hard timeout (graceful ``TimeoutError``).
4. **Captures** any exception into a structured ``ToolResult``.

Because RBAC + validation live *inside* the wrapper (not in the agent prompt),
a compromised or confused agent cannot bypass authorization.
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.auth.rbac import assert_tool_allowed
from app.config import settings
from app.logging_config import get_logger
from app.models.schemas import Role
from app.security.input_validation import validate_tool_params

logger = get_logger(__name__)


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None
    denied: bool = False
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "denied": self.denied,
            "duration_ms": round(self.duration_ms, 1),
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> Any:
        """The actual tool implementation (params already validated)."""

    async def run(self, role: Role, params: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        try:
            assert_tool_allowed(role, self.name)
        except PermissionError as exc:
            logger.warning("tool_denied", tool=self.name, role=role.value)
            return ToolResult(
                tool_name=self.name,
                success=False,
                denied=True,
                error=str(exc),
            )

        try:
            cleaned = validate_tool_params(self.name, params or {})
            output = await asyncio.wait_for(
                self.execute(cleaned),
                timeout=settings.tool_timeout_seconds,
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=output,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Tool '{self.name}' timed out after {settings.tool_timeout_seconds}s",
            )
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning("tool_failed", tool=self.name, error=str(exc))
            return ToolResult(tool_name=self.name, success=False, error=str(exc))
