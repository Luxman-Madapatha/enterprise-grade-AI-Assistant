# LangGraph usage and implementation

This repository uses LangGraph as the orchestration layer for the enterprise assistant. The model is not responsible for deciding the entire workflow by itself; instead, LangGraph coordinates routing, state updates, retrieval, research loops, and final response generation.

The implementation lives primarily in:
- `app/agents/graph.py` — graph assembly and routing
- `app/agents/state.py` — structured workflow state
- `app/agents/supervisor.py` — intent classification and routing
- `app/agents/retrieval.py` — direct-answer retrieval path
- `app/agents/research.py` — recursive multi-step investigation path
- `app/agents/response.py` — final answer generation and validation

## 1. Core design: a stateful graph, not a freeform chat loop

The graph is built with `StateGraph(AgentState)` and compiled with `MemorySaver()`:

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

graph = StateGraph(AgentState)
# add nodes
# add edges
# compile with checkpointing
return graph.compile(checkpointer=MemorySaver())
```

This gives the system:
- persistent session memory across turns
- deterministic transition logic between nodes
- conditional branching based on state
- resumable execution with checkpoints per session/thread

The graph entry point is always the `supervisor` node.

## 2. Shared state model

The workflow state is defined in `app/agents/state.py` using a typed dictionary. It includes both conversation context and workflow metadata.

```python
class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    user_query: str
    user: dict[str, str]
    session_id: str

    intent: str
    plan: list[str]
    route: str

    retrieved_chunks: list[dict[str, Any]]

    research_queue: list[str]
    research_index: int
    research_findings: list[dict[str, Any]]

    final_answer: str
    citations: list[str]

    errors: Annotated[list[str], lambda a, b: (a or []) + (b or [])]
```

Important details:
- `messages` uses `add_messages`, so chat history is merged correctly.
- `route` decides which downstream path to take: `retrieval_agent`, `research_plan`, or `response_agent`.
- `research_queue` and `research_index` power the recursive research loop.
- `retrieved_chunks` and `research_findings` become evidence for the final answer.

## 3. Supervisor node: intent classification and routing

The `supervisor_node` in `app/agents/supervisor.py` is the entry point for every user request.

It decides the request type by:
- deterministic keyword matching, or
- an LLM-based classification fallback if the LLM is available

```python
async def supervisor_node(state: AgentState) -> dict[str, Any]:
    query = state["user_query"]
    session_id = state["session_id"]

    if settings.llm_available:
        intent, plan, route = await _llm_classify(query)
    else:
        intent, plan, route = _deterministic_classify(query)

    return {"intent": intent, "plan": plan, "route": route}
```

The routing rules are intentionally concrete:
- `direct_question` -> `retrieval_agent`
- `research` or `external_lookup` -> `research_plan`
- `chitchat` -> `response_agent`

This keeps the graph safe and explainable instead of letting a single model decide the full workflow in one giant prompt.

### Deterministic routing examples

The classifier checks for domain-specific signals such as:
- research keywords like `compare`, `analyze`, `root cause`, `across all`, `report`
- external lookup signals like `who works`, `employee`, `on-call`, `service catalog`
- simple chat triggers like `hello`, `thanks`, `what can you do`

If the LLM is unavailable, the system falls back to this deterministic strategy.

## 4. Graph topology and execution flow

The graph is defined in `app/agents/graph.py`:

```python
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
```

After that:
- `retrieval_agent` flows directly into `response_agent`
- `research_plan` leads to `research_step`
- `research_step` loops until the queue is exhausted or the max step count is reached
- `research_aggregate` then routes to `response_agent`
- `response_agent` terminates the graph with `END`

### Research loop routing

The recursive research path is bounded:

```python
def _route_after_research_step(state: AgentState) -> str:
    idx = int(state.get("research_index") or 0)
    queue = state.get("research_queue") or []
    if idx < len(queue) and idx < MAX_RESEARCH_STEPS:
        return "research_step"
    return "research_aggregate"
```

This prevents unbounded reasoning. The max research budget is defined as:

```python
MAX_RESEARCH_STEPS = 8
```

## 5. Retrieval path: direct-answer workflow

The `retrieval_agent_node` in `app/agents/retrieval.py` handles simple factual or single-document questions.

It executes a knowledge search tool using the current role and the user query:

```python
result = await execute_tool(
    session_id,
    TOOL_KNOWLEDGE_SEARCH,
    role,
    {"query": query, "top_k": settings.top_k},
)
```

If successful, it returns the matched `results` as `retrieved_chunks`:

```python
chunks = result.output.get("results", []) if isinstance(result.output, dict) else []
return {"retrieved_chunks": chunks}
```

This path is optimized for low-latency retrieval of evidence for direct questions.

## 6. Research path: recursive language-model workflow (RLM)

The research flow is implemented in `app/agents/research.py` and is the main advanced workflow in the project.

### 6.1 Planning the investigation

`research_plan_node` decomposes the user request into targeted sub-queries:

```python
plan = list(state.get("plan") or [])
if not plan:
    plan = [f"{state['user_query']} - overview", f"{state['user_query']} - evidence"]

return {
    "research_queue": plan,
    "research_index": 0,
    "research_findings": [],
}
```

This creates a structured investigation plan before deeper retrieval begins.

### 6.2 Research step execution

`research_step_node` executes each sub-query one by one. It picks a tool based on query hints:

```python
def _choose_tool(sub_query: str) -> str:
    q = sub_query.lower()
    for tool, hints in _MCP_HINTS.items():
        if any(h in q for h in hints):
            return tool
    return TOOL_KNOWLEDGE_SEARCH
```

The system routes queries to:
- `knowledge_search` for internal enterprise documents
- `mcp_employee`, `mcp_service`, or `mcp_incident` for external structured lookups

Each research step stores a finding entry:

```python
entry = {"sub_query": sub_query, "tool": tool_name}
if result.success:
    entry["output"] = output
    entry["status"] = "success"
```

### 6.3 Recursive exploration

When a search yields a near-full result page and there are still new chunks discovered, the system automatically broadens the query by splitting it into finer sub-queries:

```python
def _split_query(query: str) -> list[str]:
    suffixes = [
        "root cause",
        "impact and affected services",
        "resolution and timeline",
    ]
    return [f"{query} - {s}" for s in suffixes]
```

This is the core recursive behavior: if the current evidence is incomplete or the search result is broad, the graph re-queues narrower research questions instead of continuing a single noisy sweep.

### 6.4 Aggregation and deduplication

The `research_aggregate_node` collects all findings and flattens them into deduplicated chunks:

```python
def _flatten_chunks(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: dict[str, dict[str, Any]] = {}
    for f in findings:
        output = f.get("output")
        if isinstance(output, dict):
            for r in output.get("results", []):
                cid = r.get("chunk_id")
                if cid and cid not in chunks:
                    chunks[cid] = r
    return list(chunks.values())
```

This ensures the evidence passed to the final answer is compact and free of repeated results.

## 7. Response agent: final answer and validation

The final stage is the `response_agent_node` in `app/agents/response.py`.

It:
- loads the evidence (`retrieved_chunks` and `research_findings`)
- calls the LLM if configured
- otherwise falls back to a deterministic template answer
- validates citations and content safety with `guard_answer`

```python
if settings.llm_available:
    answer, citations = await _llm_answer(query, chunks, findings)
else:
    answer, citations = _template_answer(query, chunks, findings)

valid_ids = {c["chunk_id"] for c in chunks if c.get("chunk_id")}
guard = guard_answer(answer, citations, valid_ids)
```

This is where the graph enforces the "evidence first" design. It does not allow unsupported or ungrounded answer content to pass through unchecked.

## 8. Observability and event streaming

The system emits structured events during each node execution via `publish_event(...)`.

Examples include:
- `agent_state`
- `retrieval`
- `validation`

This gives the frontend or operators a real-time trace of:
- which node is running
- what the supervisor decided
- how many retrieval hits were found
- whether research is recursing
- whether the final answer passed validation

This is important for enterprise settings where auditability matters as much as intelligence.

## 9. Why this is a good LangGraph implementation

This repo uses LangGraph in a way that matches strong production patterns:

- graph-based orchestration instead of monolithic prompting
- typed workflow state instead of implicit memory
- conditional transitions for routing logic
- bounded loops to avoid runaway recursion
- checkpointing for session continuity
- event-driven observability for debugging and auditing
- tool execution under explicit role-based permission checks

In short, LangGraph is the control plane while the LLM and retrieval tools are the execution layer.

## 10. Execution summary

A typical request follows this path:

1. `supervisor` classifies the question and picks a route.
2. `retrieval_agent` executes hybrid retrieval for direct questions.
3. `research_plan` breaks complex questions into sub-queries.
4. `research_step` executes those sub-queries in a bounded recursive loop.
5. `research_aggregate` consolidates findings.
6. `response_agent` produces the final answer and runs validation.
7. `END` closes the graph.

This design keeps the assistant safe, explainable, auditable, and operationally robust for enterprise use.

## 11. Repo-specific file map

- `app/agents/graph.py` — graph assembly and routing topology
- `app/agents/state.py` — typed workflow state
- `app/agents/supervisor.py` — intent classification and routing
- `app/agents/retrieval.py` — single-shot hybrid retrieval
- `app/agents/research.py` — recursive RLM investigation loop
- `app/agents/response.py` — answer generation and safety checks
- `app/agents/tool_runner.py` — tool dispatch and permission enforcement
- `app/auth/rbac.py` — authorization controls
- `app/security/guardrails.py` — output validation

This repo is a practical example of LangGraph being used as a workflow engine for an enterprise AI assistant with retrieval, multi-step research, and guardrailed response generation.
