"""Shared helper: execute a tool with real-time event emission.

Every tool call emits a ``tool_call`` event (started -> success/error) so the
frontend activity panel and LangSmith traces both capture exactly what the
agent executed, with what parameters, and the outcome.
"""
from __future__ import annotations

from typing import Any

from app.agents.events import publish_event
from app.logging_config import get_logger
from app.models.schemas import Role
from app.tools.base import ToolResult
from app.tools.registry import get_tool

logger = get_logger(__name__)


async def execute_tool(
    session_id: str,
    tool_name: str,
    role: str,
    params: dict[str, Any],
) -> ToolResult:
    role_enum = Role(role)
    await publish_event(
        session_id,
        "tool_call",
        {
            "tool": tool_name,
            "params": params,
            "status": "started",
        },
    )
    tool = get_tool(tool_name, role_enum)
    result = await tool.run(role_enum, params)

    payload: dict[str, Any] = {
        "tool": tool_name,
        "status": "success" if result.success else ("denied" if result.denied else "error"),
        "error": result.error,
        "duration_ms": round(result.duration_ms, 1),
    }
    if result.success and not isinstance(result.output, (dict, list, str, int, float, bool, type(None))):
        payload["output_preview"] = str(result.output)[:200]
    elif result.success:
        payload["output"] = result.output
    await publish_event(session_id, "tool_call", payload)
    return result
