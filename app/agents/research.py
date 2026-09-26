"""Research agent — Recursive Language Model (RLM) behaviour.

Instead of dumping whole documents into the context window, the research agent:

1. Generates a structured search plan (decomposed sub-queries).
2. Explores targeted sections one sub-query at a time (a bounded recursive
   loop — if a query returns a full page of hits it is split into finer
   sub-queries and re-queued).
3. Aggregates findings across batches, optionally using the Python analysis
   tool for structured counting.

Each step is a separate LangGraph node so the activity panel streams the
agent's progress in real time.
"""
from __future__ import annotations

from typing import Any

from app.agents.events import publish_event
from app.agents.state import AgentState
from app.agents.tool_runner import execute_tool
from app.auth.rbac import (
    TOOL_KNOWLEDGE_SEARCH,
    TOOL_MCP_EMPLOYEE,
    TOOL_MCP_INCIDENT,
    TOOL_MCP_SERVICE,
    TOOL_PYTHON_ANALYSIS,
)
from app.config import settings
from app.logging_config import get_logger
from app.models.schemas import Role

logger = get_logger(__name__)

MAX_RESEARCH_STEPS = 8

_MCP_HINTS = {
    TOOL_MCP_EMPLOYEE: ["employee", "who is", "who works", "works in", "directory",
                        "report to", "title of", "department"],
    TOOL_MCP_SERVICE: ["service", "catalog", "owns", "owner", "sla", "status of service"],
    TOOL_MCP_INCIDENT: ["incident record", "incident list", "sev1", "sev2", "sev3",
                        "outage record", "list incidents"],
}


def _split_query(query: str) -> list[str]:
    """Recursive exploration: break a broad query into finer sub-queries."""
    suffixes = ["root cause", "impact and affected services", "resolution and timeline"]
    return [f"{query} - {s}" for s in suffixes]


def _choose_tool(sub_query: str) -> str:
    q = sub_query.lower()
    for tool, hints in _MCP_HINTS.items():
        if any(h in q for h in hints):
            return tool
    return TOOL_KNOWLEDGE_SEARCH


async def research_plan_node(state: AgentState) -> dict[str, Any]:
    session_id = state["session_id"]
    plan = list(state.get("plan") or [])
    if not plan:
        # Fallback decomposition if the supervisor did not provide one.
        plan = [f"{state['user_query']} - overview", f"{state['user_query']} - evidence"]

    await publish_event(
        session_id,
        "agent_state",
        {
            "node": "research_plan",
            "message": f"RLM: decomposed the task into {len(plan)} targeted sub-queries.",
            "plan": plan,
        },
    )
    logger.info("research_plan", session=session_id, plan=plan)
    return {
        "research_queue": plan,
        "research_index": 0,
        "research_findings": [],
    }


async def research_step_node(state: AgentState) -> dict[str, Any]:
    session_id = state["session_id"]
    role = state["user"]["role"]
    queue: list[str] = list(state.get("research_queue") or [])
    idx = int(state.get("research_index") or 0)
    findings: list[dict[str, Any]] = list(state.get("research_findings") or [])

    if idx >= len(queue) or idx >= MAX_RESEARCH_STEPS:
        return {"research_index": idx, "research_findings": findings}

    sub_query = queue[idx]
    tool_name = _choose_tool(sub_query)

    await publish_event(
        session_id,
        "agent_state",
        {
            "node": "research_step",
            "message": f"RLM step {idx + 1}/{len(queue)}: '{sub_query}'",
        },
    )

    result = await execute_tool(
        session_id,
        tool_name,
        role,
        {"query": sub_query, "top_k": settings.top_k},
    )

    # Track chunk ids already seen so recursive exploration stops once the
    # corpus is exhausted (avoids re-queuing identical result sets forever).
    seen_ids = {
        r.get("chunk_id")
        for prev in findings
        if isinstance(prev.get("output"), dict)
        for r in prev["output"].get("results", [])
        if r.get("chunk_id")
    }

    entry: dict[str, Any] = {"sub_query": sub_query, "tool": tool_name}
    if result.success:
        output = result.output if isinstance(result.output, (dict, list)) else {"raw": result.output}
        entry["output"] = output
        entry["status"] = "success"
        # Recursive exploration: when a knowledge search returns a full page of
        # *new* hits and budget remains, split into finer sub-queries.
        if tool_name == TOOL_KNOWLEDGE_SEARCH and isinstance(output, dict):
            hits = len(output.get("results", []))
            new_ids = {r.get("chunk_id") for r in output.get("results", []) if r.get("chunk_id")}
            if (
                hits >= settings.top_k
                and (new_ids - seen_ids)
                and (len(queue) - idx) < MAX_RESEARCH_STEPS
            ):
                new_queries = _split_query(sub_query)
                queue.extend(new_queries)
                await publish_event(
                    session_id,
                    "agent_state",
                    {
                        "node": "research_step",
                        "message": f"Recursive exploration: '{sub_query}' returned {hits} hits "
                        f"({len(new_ids - seen_ids)} new); queued {len(new_queries)} finer sub-queries.",
                    },
                )
    else:
        entry["status"] = "error"
        entry["error"] = result.error
        # Butterfly effect: a failed step is recorded and does not abort the
        # whole investigation.
        await publish_event(
            session_id,
            "retrieval",
            {"query": sub_query, "status": "error", "error": result.error},
        )

    findings.append(entry)
    return {
        "research_queue": queue,
        "research_findings": findings,
        "research_index": idx + 1,
    }


async def research_aggregate_node(state: AgentState) -> dict[str, Any]:
    session_id = state["session_id"]
    role = state["user"]["role"]
    findings: list[dict[str, Any]] = list(state.get("research_findings") or [])

    await publish_event(
        session_id,
        "agent_state",
        {
            "node": "research_aggregate",
            "message": f"RLM: aggregating {len(findings)} findings into a summary.",
        },
    )

    # Structured analysis (analyst/admin only — enforced inside the tool).
    analysis = None
    role_enum = Role(role)
    from app.auth.rbac import is_tool_allowed

    if is_tool_allowed(role_enum, TOOL_PYTHON_ANALYSIS) and findings:
        data = {
            "findings": [
                {"query": f.get("sub_query"), "status": f.get("status")}
                for f in findings
            ],
            "successful": sum(1 for f in findings if f.get("status") == "success"),
        }
        result = await execute_tool(
            session_id,
            TOOL_PYTHON_ANALYSIS,
            role,
            {"code": "sum(1 for f in data['findings'] if f['status'] == 'success')", "data": data},
        )
        if result.success:
            analysis = result.output.get("result")
    elif findings:
        await publish_event(
            session_id,
            "validation",
            {
                "message": "Python analysis skipped: role lacks permission "
                "(analyst/admin required).",
            },
        )

    return {
        "research_findings": findings,
        "retrieved_chunks": _flatten_chunks(findings),
    }


def _flatten_chunks(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect knowledge-search chunks from all research findings (deduped)."""
    chunks: dict[str, dict[str, Any]] = {}
    for f in findings:
        output = f.get("output")
        if isinstance(output, dict):
            for r in output.get("results", []):
                cid = r.get("chunk_id")
                if cid and cid not in chunks:
                    chunks[cid] = r
    return list(chunks.values())
