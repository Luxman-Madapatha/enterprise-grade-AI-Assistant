"""Input validation for user requests and tool parameters.

Everything that crosses a trust boundary is validated here. Fail fast with a
clear, user-safe error rather than allowing malformed input to reach the LLM
or tools.
"""
from __future__ import annotations

import re
from typing import Any

MAX_MESSAGE_LENGTH = 4000
MAX_TOOL_ARG_LENGTH = 2000
_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ValidationError(ValueError):
    """Raised when input fails validation."""


def validate_user_request(message: str) -> str:
    if not isinstance(message, str):
        raise ValidationError("Message must be a string.")
    if not message.strip():
        raise ValidationError("Message must not be empty.")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValidationError(
            f"Message too long ({len(message)} > {MAX_MESSAGE_LENGTH} chars)."
        )
    if _CTRL_CHARS.search(message):
        raise ValidationError("Message contains invalid control characters.")
    return message.strip()


def validate_tool_params(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate common tool parameter shapes.

    Each tool declares an allow-list of parameter names and a max string length.
    Unknown parameters are dropped, oversized values rejected.
    """
    allowed = {
        "knowledge_search": {"query", "top_k", "filter", "namespace"},
        "python_analysis": {"code", "data", "max_rows"},
        "mcp_employee_directory": {"query"},
        "mcp_service_catalog": {"query"},
        "mcp_incident_records": {"query", "severity"},
    }
    names = allowed.get(tool_name)
    if names is None:
        raise ValidationError(f"Unknown tool: {tool_name}")

    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if key not in names:
            continue
        if isinstance(value, str):
            if len(value) > MAX_TOOL_ARG_LENGTH:
                raise ValidationError(
                    f"Tool parameter '{key}' too long for {tool_name}."
                )
            cleaned[key] = value
        else:
            cleaned[key] = value
    return cleaned
