"""Tool registry — maps canonical tool names to tool instances.

Instances are created per-role so the authorization context (the caller's
role) is bound at construction time and cannot be spoofed by the agent.
"""
from __future__ import annotations

from app.auth.rbac import (
    TOOL_ADMIN_REINDEX,
    TOOL_KNOWLEDGE_SEARCH,
    TOOL_MCP_EMPLOYEE,
    TOOL_MCP_INCIDENT,
    TOOL_MCP_SERVICE,
    TOOL_PYTHON_ANALYSIS,
)
from app.models.schemas import Role
from app.tools.base import BaseTool
from app.tools.knowledge_search import KnowledgeSearchTool
from app.tools.mcp_client import (
    EmployeeDirectoryTool,
    IncidentRecordsTool,
    ServiceCatalogTool,
)
from app.tools.python_analysis import PythonAnalysisTool

TOOL_DESCRIPTIONS: dict[str, str] = {
    TOOL_KNOWLEDGE_SEARCH: "Hybrid search over internal documents (policies, runbooks, incidents, specs).",
    TOOL_PYTHON_ANALYSIS: "Run a restricted Python expression over retrieved data for structured analysis.",
    TOOL_MCP_EMPLOYEE: "Search the employee directory via MCP.",
    TOOL_MCP_SERVICE: "Search the service catalog via MCP.",
    TOOL_MCP_INCIDENT: "Search incident records via MCP.",
    TOOL_ADMIN_REINDEX: "Rebuild the document index (administrator only).",
}


def get_tool(name: str, role: Role) -> BaseTool:
    """Instantiate (or fetch) a tool bound to ``role``."""
    if name == TOOL_KNOWLEDGE_SEARCH:
        return KnowledgeSearchTool(role)
    if name == TOOL_PYTHON_ANALYSIS:
        return PythonAnalysisTool()
    if name == TOOL_MCP_EMPLOYEE:
        return EmployeeDirectoryTool()
    if name == TOOL_MCP_SERVICE:
        return ServiceCatalogTool()
    if name == TOOL_MCP_INCIDENT:
        return IncidentRecordsTool()
    raise KeyError(f"Unknown tool: {name}")
