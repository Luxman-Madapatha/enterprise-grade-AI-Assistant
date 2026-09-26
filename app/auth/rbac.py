"""Role Based Access Control.

A single declarative table maps every tool/action to the roles allowed to use
it. Tool wrappers consult this table *immediately before execution* so the
authorization check cannot be bypassed by the agent's own reasoning.
"""
from __future__ import annotations

from app.models.schemas import Role

# Canonical tool names used across the whole codebase.
TOOL_KNOWLEDGE_SEARCH = "knowledge_search"
TOOL_PYTHON_ANALYSIS = "python_analysis"
TOOL_MCP_EMPLOYEE = "mcp_employee_directory"
TOOL_MCP_SERVICE = "mcp_service_catalog"
TOOL_MCP_INCIDENT = "mcp_incident_records"
TOOL_ADMIN_REINDEX = "admin_reindex"

# role -> set of allowed tool names
_ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.VIEWER: frozenset({TOOL_KNOWLEDGE_SEARCH}),
    Role.ANALYST: frozenset(
        {
            TOOL_KNOWLEDGE_SEARCH,
            TOOL_PYTHON_ANALYSIS,
            TOOL_MCP_EMPLOYEE,
            TOOL_MCP_SERVICE,
            TOOL_MCP_INCIDENT,
        }
    ),
    Role.ADMINISTRATOR: frozenset(
        {
            TOOL_KNOWLEDGE_SEARCH,
            TOOL_PYTHON_ANALYSIS,
            TOOL_MCP_EMPLOYEE,
            TOOL_MCP_SERVICE,
            TOOL_MCP_INCIDENT,
            TOOL_ADMIN_REINDEX,
        }
    ),
}


def is_tool_allowed(role: Role, tool_name: str) -> bool:
    """Return True when ``role`` may execute ``tool_name``."""
    return tool_name in _ROLE_PERMISSIONS.get(role, frozenset())


def allowed_tools(role: Role) -> frozenset[str]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def assert_tool_allowed(role: Role, tool_name: str) -> None:
    """Raise PermissionError when the role cannot use the tool."""
    if not is_tool_allowed(role, tool_name):
        raise PermissionError(
            f"Role '{role.value}' is not authorized to use tool '{tool_name}'."
        )
