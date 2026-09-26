"""Supervisor agent — intent understanding, task decomposition, routing."""
from __future__ import annotations

import json
from typing import Any

from app.agents.events import publish_event
from app.agents.state import AgentState
from app.config import settings
from app.llm.client import get_llm_client
from app.logging_config import get_logger

logger = get_logger(__name__)

# Routes.
ROUTE_RETRIEVAL = "retrieval_agent"
ROUTE_RESEARCH = "research_plan"
ROUTE_RESPONSE = "response_agent"

# Keywords that signal a multi-document / analytical task (RLM path).
_RESEARCH_KEYWORDS = [
    "summarize all", "all outage", "all incidents", "recurring", "across",
    "compare", "trend", "how many", "identify recurring", "analyze",
    "root cause", "aggregate", "last year", "across all", "report",
]
# Keywords that signal external enterprise data (MCP path).
_MCP_KEYWORDS = ["employee", "who is", "who works", "works in", "directory",
                 "service catalog", "on-call", "oncall", "incident records",
                 "who owns", "department"]
# Keywords that signal simple chat (no tools needed).
_CHITCHAT_KEYWORDS = ["hello", "hi ", "hey", "thanks", "thank you", "who are you",
                      "what can you do", "help"]


def _deterministic_classify(query: str) -> tuple[str, list[str], str]:
    q = query.lower().strip()
    if any(k in q for k in _CHITCHAT_KEYWORDS) and len(q.split()) <= 8:
        return "chitchat", [], ROUTE_RESPONSE
    if any(k in q for k in _RESEARCH_KEYWORDS):
        return "research", _decompose(query), ROUTE_RESEARCH
    if any(k in q for k in _MCP_KEYWORDS):
        return "external_lookup", [query], ROUTE_RESEARCH
    return "direct_question", [query], ROUTE_RETRIEVAL


def _decompose(query: str) -> list[str]:
    """Deterministic task decomposition used when no LLM is available."""
    sub = []
    if any(k in query.lower() for k in ["outage", "incident", "failure"]):
        sub.append(f"{query} - incident reports")
        sub.append(f"{query} - root causes and contributing factors")
    elif any(k in query.lower() for k in ["architecture", "design"]):
        sub.append(f"{query} - architecture overview")
        sub.append(f"{query} - components and dependencies")
    elif any(k in query.lower() for k in ["policy", "compliance"]):
        sub.append(f"{query} - policy requirements")
    elif any(k in query.lower() for k in ["runbook", "procedure", "how to"]):
        sub.append(f"{query} - step by step procedure")
    else:
        sub.append(f"{query} - overview")
        sub.append(f"{query} - details and evidence")
    return sub


async def _llm_classify(query: str) -> tuple[str, list[str], str]:
    client = get_llm_client()
    if not client.available:
        return _deterministic_classify(query)

    system = (
        "You are the supervisor of an enterprise assistant. Classify the user "
        "request and produce a JSON object with exactly three keys:\n"
        '- "intent": one of "direct_question", "research", "external_lookup", "chitchat"\n'
        '- "plan": a list of 1-4 decomposed sub-queries (strings)\n'
        '- "route": one of "retrieval_agent", "research_plan", "response_agent"\n'
        "Rules: multi-document analysis or aggregation -> research + research_plan. "
        "A simple factual question -> direct_question + retrieval_agent. "
        "Needs employee/service/incident lookup -> external_lookup + research_plan. "
        "Greetings/thanks -> chitchat + response_agent. "
        "Respond with JSON only."
    )
    try:
        raw = await client.generate(system, query)
    except Exception:  # noqa: BLE001 - degrade to deterministic
        logger.warning("llm_classify_failed_falling_back")
        return _deterministic_classify(query)
    return _parse_llm_json(raw, query)


def _parse_llm_json(raw: str, query: str) -> tuple[str, list[str], str]:
    try:
        data = json.loads(raw)
        intent = str(data.get("intent", ""))
        plan = [str(p) for p in data.get("plan", [])] or [query]
        route = str(data.get("route", ""))
        valid_routes = {ROUTE_RETRIEVAL, ROUTE_RESEARCH, ROUTE_RESPONSE}
        if route not in valid_routes:
            route = {"research": ROUTE_RESEARCH,
                     "external_lookup": ROUTE_RESEARCH,
                     "direct_question": ROUTE_RETRIEVAL,
                     "chitchat": ROUTE_RESPONSE}.get(intent, ROUTE_RETRIEVAL)
        return intent, plan, route
    except (json.JSONDecodeError, AttributeError):
        return _deterministic_classify(query)


async def supervisor_node(state: AgentState) -> dict[str, Any]:
    query = state["user_query"]
    session_id = state["session_id"]

    if settings.llm_available:
        intent, plan, route = await _llm_classify(query)
    else:
        intent, plan, route = _deterministic_classify(query)

    await publish_event(
        session_id,
        "agent_state",
        {
            "node": "supervisor",
            "intent": intent,
            "plan": plan,
            "route": route,
            "message": f"Supervisor classified intent='{intent}' and routed to '{route}'.",
        },
    )
    logger.info(
        "supervisor_decision",
        session=session_id,
        intent=intent,
        route=route,
        plan=plan,
    )
    return {"intent": intent, "plan": plan, "route": route}
