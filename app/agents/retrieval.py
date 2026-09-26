"""Retrieval agent — single-shot hybrid RAG for direct questions."""
from __future__ import annotations

from typing import Any

from app.agents.events import publish_event
from app.agents.state import AgentState
from app.agents.tool_runner import execute_tool
from app.auth.rbac import TOOL_KNOWLEDGE_SEARCH
from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


async def retrieval_agent_node(state: AgentState) -> dict[str, Any]:
    query = state["user_query"]
    role = state["user"]["role"]
    session_id = state["session_id"]

    await publish_event(
        session_id,
        "agent_state",
        {
            "node": "retrieval_agent",
            "message": "Retrieval agent running hybrid (dense+sparse) search...",
        },
    )

    result = await execute_tool(
        session_id,
        TOOL_KNOWLEDGE_SEARCH,
        role,
        {"query": query, "top_k": settings.top_k},
    )

    if not result.success:
        await publish_event(
            session_id,
            "retrieval",
            {"query": query, "hits": 0, "status": "error", "error": result.error},
        )
        return {"retrieved_chunks": []}

    chunks = result.output.get("results", []) if isinstance(result.output, dict) else []
    await publish_event(
        session_id,
        "retrieval",
        {"query": query, "hits": len(chunks), "status": "success"},
    )
    logger.info("retrieval_agent_done", session=session_id, hits=len(chunks))
    return {"retrieved_chunks": chunks}
