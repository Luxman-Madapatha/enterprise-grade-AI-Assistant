"""LangGraph assembly.

Graph topology:

    supervisor
        ├─ retrieval_agent ──────────┐
        ├─ research_plan ─┐          │
        │      ↓           │          │
        │   research_step ⟲ (RLM)    │
        │      ↓           │          │
        │   research_aggregate ───────┤
        └─ response_agent ◄──────────┘
                  ↓
                 END

* The supervisor routes each request to a specialized agent.
* The research path is a bounded recursive loop (RLM): plan -> step (re-queue
  finer sub-queries when a step is saturated) -> aggregate.
* ``MemorySaver`` checkpoints state per ``thread_id`` (session id) so the
  agent's internal state survives across turns within a session.
"""
from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.research import (
    MAX_RESEARCH_STEPS,
    research_aggregate_node,
    research_plan_node,
    research_step_node,
)
from app.agents.response import response_agent_node
from app.agents.retrieval import retrieval_agent_node
from app.agents.state import AgentState, initial_state
from app.agents.supervisor import (
    ROUTE_RESEARCH,
    ROUTE_RESPONSE,
    ROUTE_RETRIEVAL,
    supervisor_node,
)
from app.logging_config import get_logger
from app.observability.langsmith import trace_config

logger = get_logger(__name__)


def _route_after_supervisor(state: AgentState) -> str:
    return state.get("route") or ROUTE_RETRIEVAL


def _route_after_research_step(state: AgentState) -> str:
    idx = int(state.get("research_index") or 0)
    queue = state.get("research_queue") or []
    if idx < len(queue) and idx < MAX_RESEARCH_STEPS:
        return "research_step"
    return "research_aggregate"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("retrieval_agent", retrieval_agent_node)
    graph.add_node("research_plan", research_plan_node)
    graph.add_node("research_step", research_step_node)
    graph.add_node("research_aggregate", research_aggregate_node)
    graph.add_node("response_agent", response_agent_node)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {
            ROUTE_RETRIEVAL: "retrieval_agent",
            ROUTE_RESEARCH: "research_plan",
            ROUTE_RESPONSE: "response_agent",
        },
    )
    graph.add_edge("retrieval_agent", "response_agent")
    graph.add_edge("research_plan", "research_step")
    graph.add_conditional_edges(
        "research_step",
        _route_after_research_step,
        {
            "research_step": "research_step",
            "research_aggregate": "research_aggregate",
        },
    )
    graph.add_edge("research_aggregate", "response_agent")
    graph.add_edge("response_agent", END)

    # MemorySaver checkpoints agent state per thread_id (session id).
    return graph.compile(checkpointer=MemorySaver())


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_assistant(
    user: dict[str, str], session_id: str, query: str
) -> dict[str, Any]:
    """Execute the graph for one user turn and return the final state."""
    graph = get_graph()
    config = trace_config(user["username"], session_id)
    final = await graph.ainvoke(
        initial_state(user, session_id, query),
        config=config,
    )
    logger.info("assistant_run_complete", session=session_id)
    return final
