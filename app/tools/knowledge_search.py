"""Knowledge Search tool — hybrid retrieval with role-aware access filtering."""
from __future__ import annotations

from typing import Any

from app.auth.rbac import TOOL_KNOWLEDGE_SEARCH
from app.models.schemas import Role
from app.retrieval.hybrid_search import hybrid_search
from app.tools.base import BaseTool

# Roles map to the maximum access level they may retrieve.
_ROLE_ACCESS_LEVELS: dict[Role, list[str]] = {
    Role.VIEWER: ["public", "internal"],
    Role.ANALYST: ["public", "internal", "confidential"],
    Role.ADMINISTRATOR: ["public", "internal", "confidential", "restricted"],
}


class KnowledgeSearchTool(BaseTool):
    name = TOOL_KNOWLEDGE_SEARCH
    description = "Hybrid (dense + sparse) search across the document corpus."

    def __init__(self, role: Role) -> None:
        # The caller's role is fixed at instantiation time, not taken from the
        # (untrusted) request body.
        self.role = role

    async def execute(self, params: dict[str, Any]) -> Any:
        query = params.get("query", "")
        top_k = int(params.get("top_k") or 8)
        user_filter = params.get("filter") or {}

        access_filter = {
            "access_level": {"$in": _ROLE_ACCESS_LEVELS.get(self.role, ["public"])}
        }
        merged_filter = {**user_filter, **access_filter}
        namespace = params.get("namespace") or "default"

        results = await hybrid_search.search(
            query=query,
            top_k=top_k,
            flt=merged_filter,
            namespace=namespace,
        )
        return {
            "query": query,
            "results": [r.as_dict() for r in results],
        }
