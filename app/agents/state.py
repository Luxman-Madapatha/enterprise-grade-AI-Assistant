"""LangGraph agent state."""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    # Conversation (messages use the add_messages reducer).
    messages: Annotated[list[BaseMessage], add_messages]

    # Request context.
    user_query: str
    user: dict[str, str]  # {"username": ..., "role": ...}
    session_id: str

    # Supervisor outputs.
    intent: str
    plan: list[str]
    route: str  # retrieval_agent | research_plan | response_agent

    # Retrieval agent outputs.
    retrieved_chunks: list[dict[str, Any]]

    # Research agent (RLM) working state.
    research_queue: list[str]
    research_index: int
    research_findings: list[dict[str, Any]]

    # Response agent outputs.
    final_answer: str
    citations: list[str]

    # Graceful degradation.
    errors: Annotated[list[str], lambda a, b: (a or []) + (b or [])]


def initial_state(
    user: dict[str, str], session_id: str, user_query: str
) -> dict[str, Any]:
    return {
        "messages": [],
        "user_query": user_query,
        "user": user,
        "session_id": session_id,
        "intent": "",
        "plan": [],
        "route": "",
        "retrieved_chunks": [],
        "research_queue": [],
        "research_index": 0,
        "research_findings": [],
        "final_answer": "",
        "citations": [],
        "errors": [],
    }
