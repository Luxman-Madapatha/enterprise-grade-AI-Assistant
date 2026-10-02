# LangGraph usage and implementation

This repository uses LangGraph as the orchestration layer for an enterprise AI assistant. The LLM is not the only decision-maker; LangGraph coordinates state, retrieval, tool execution, multi-step research, and answer validation in a bounded workflow.

The implementation lives primarily in:
- `app/agents/graph.py` — graph assembly, edges, and loop routing
- `app/agents/state.py` — typed workflow state
- `app/agents/supervisor.py` — intent classification and routing
- `app/agents/retrieval.py` — direct retrieval path
- `app/agents/research.py` — Recursive Language Model (RLM) workflow
- `app/agents/response.py` — answer generation and guardrails

## 1. Graph assembly and workflow shape

The graph is created with `StateGraph(AgentState)` and compiled with `MemorySaver()`:

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

graph = StateGraph(AgentState)

graph.add_node("supervisor", supervisor_node)
graph.add_node("retrieval_agent", retrieval_agent_node)
graph.add_node("research_plan", research_plan_node)
graph.add_node("research_step", research_step_node)
graph.add_node("research_aggregate", research_aggregate_node)
graph.add_node("response_agent", response_agent_node)

graph.set_entry_point("supervisor")
...
return graph.compile(checkpointer=MemorySaver())
```

This gives the system:
- session persistence across turns
- structured state transitions between steps
- conditional branching based on route decisions
- checkpointed execution for auditability and debugging

The graph entry point is always the `supervisor` node.

## 2. State model used by the graph

The workflow state is defined in `app/agents/state.py`:

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

Important state fields:
- `intent` and `route` come from the supervisor
- `plan` is the task decomposition output
- `research_queue` stores pending sub-queries
- `research_index` tracks progress through the queue
- `research_findings` stores each tool result and status
- `retrieved_chunks` are flattened evidence for final answer generation

## 3. Supervisor and routing model

The first node is `supervisor_node` in `app/agents/supervisor.py`.

It uses a deterministic classifier first, then optionally an LLM-based classification when the model is configured:

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

The route targets are:
- `retrieval_agent`
- `research_plan`
- `response_agent`

The supervisor maps user intent into workflow routing:
- factual/simple question -> retrieval path
- multi-document or analytic question -> RLM research path
- external employee/service/incident lookup -> research path
- greeting or general chatter -> response path

## 4. Direct retrieval path

For direct questions, the graph routes to `retrieval_agent` defined in `app/agents/retrieval.py`.

This node runs a single retrieval step and returns evidence chunks for the answer stage:

```python
async def retrieval_agent_node(state: AgentState) -> dict[str, Any]:
    query = state["user_query"]
    role = state["user"]["role"]
    session_id = state["session_id"]

    result = await execute_tool(
        session_id,
        TOOL_KNOWLEDGE_SEARCH,
        role,
        {"query": query, "top_k": settings.top_k},
    )

    if not result.success:
        return {"retrieved_chunks": []}

    chunks = result.output.get("results", []) if isinstance(result.output, dict) else []
    return {"retrieved_chunks": chunks}
```

This is a single-shot hybrid retrieval workflow: it retrieves candidate chunks and passes them directly to the response node.

## 5. RLM implementation: recursive multi-step research

The repository’s deeper workflow is the Recursive Language Model (RLM) implementation in `app/agents/research.py`.

This is not a generic LLM chain. It is a bounded research loop that:
1. breaks down the user request into sub-queries,
2. executes those sub-queries via tools,
3. re-queues more granular follow-ups when a search is still broad,
4. aggregates findings into a deduplicated evidence set,
5. passes evidence to the final response node.

### 5.1 Research step budget

The recursion is controlled by a hard cap:

```python
MAX_RESEARCH_STEPS = 8
```

The loop condition is defined in `graph.py`:

```python
def _route_after_research_step(state: AgentState) -> str:
    idx = int(state.get("research_index") or 0)
    queue = state.get("research_queue") or []
    if idx < len(queue) and idx < MAX_RESEARCH_STEPS:
        return "research_step"
    return "research_aggregate"
```

This is the key safety property of the RLM design: it prevents infinite loops and keeps research bounded.

### 5.2 Planning the research queue

The `research_plan_node` creates the initial investigation queue from the supervisor plan or a default fallback:

```python
async def research_plan_node(state: AgentState) -> dict[str, Any]:
    session_id = state["session_id"]
    plan = list(state.get("plan") or [])
    if not plan:
        plan = [
            f"{state['user_query']} - overview",
            f"{state['user_query']} - evidence",
        ]

    return {
        "research_queue": plan,
        "research_index": 0,
        "research_findings": [],
    }
```

This creates a structured set of sub-queries before any tool calls are made.

### 5.3 Tool selection per research question

The system decides which tool to use based on the sub-query wording.

```python
_MCP_HINTS = {
    TOOL_MCP_EMPLOYEE: ["employee", "who is", "who works", "works in", "directory"],
    TOOL_MCP_SERVICE: ["service", "catalog", "owns", "owner", "sla", "status of service"],
    TOOL_MCP_INCIDENT: ["incident record", "incident list", "sev1", "sev2", "sev3"],
}


def _choose_tool(sub_query: str) -> str:
    q = sub_query.lower()
    for tool, hints in _MCP_HINTS.items():
        if any(h in q for h in hints):
            return tool
    return TOOL_KNOWLEDGE_SEARCH
```

This means:
- internal document lookups usually go through `knowledge_search`
- employee/service metadata lookups use MCP tools
- incident-related queries can use the incident tool

### 5.4 Research step execution

Each step processes one queued query and records the result:

```python
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

    result = await execute_tool(
        session_id,
        tool_name,
        role,
        {"query": sub_query, "top_k": settings.top_k},
    )
```

The step records a result object such as:

```python
entry = {"sub_query": sub_query, "tool": tool_name}
if result.success:
    entry["output"] = output
    entry["status"] = "success"
else:
    entry["status"] = "error"
    entry["error"] = result.error
```

The findings are appended to the state and the queue index increments:

```python
findings.append(entry)
return {
    "research_queue": queue,
    "research_findings": findings,
    "research_index": idx + 1,
}
```

### 5.5 Recursive expansion of broad search results

This is the most important part of the RLM implementation. When a knowledge search returns a full page of new results, the system broadens the investigation into a more specific follow-up plan instead of blindly continuing with the same question.

```python
def _split_query(query: str) -> list[str]:
    suffixes = [
        "root cause",
        "impact and affected services",
        "resolution and timeline",
    ]
    return [f"{query} - {s}" for s in suffixes]
```

And in the step logic:

```python
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
```

This creates a recursive refinement loop:
- initial query is broad
- search returns many useful hits
- new sub-queries are generated for root cause, impact, and resolution
- those queries are added back to the queue
- the loop continues until the queue is exhausted or the step cap is reached

This is effectively a bounded RLM-style search-decompose-expand loop.

### 5.6 Deduplication and aggregation

Before the final answer, the research findings are aggregated and deduplicated:

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

This keeps the evidence set readable, compact, and resistant to repeated chunk retrieval.

### 5.7 Optional structured analysis

The aggregate stage can also perform structured analysis, but only when the role is authorized.

```python
if is_tool_allowed(role_enum, TOOL_PYTHON_ANALYSIS) and findings:
    result = await execute_tool(
        session_id,
        TOOL_PYTHON_ANALYSIS,
        role,
        {"code": "sum(1 for f in data['findings'] if f['status'] == 'success')", "data": data},
    )
```

This gives researchers a deterministic analysis capability for summarizing count-like findings without broadening the workflow to unrestricted Python execution.

## 6. Final response generation

Once the research loop ends, the graph routes to `response_agent`. That node:
- takes the flattened evidence
- optionally asks the LLM to answer with citations
- otherwise uses a deterministic template answer
- runs safety filtering with `guard_answer`

```python
if settings.llm_available:
    answer, citations = await _llm_answer(query, chunks, findings)
else:
    answer, citations = _template_answer(query, chunks, findings)

valid_ids = {c["chunk_id"] for c in chunks if c.get("chunk_id")}
guard = guard_answer(answer, citations, valid_ids)
```

This ensures the final output remains grounded and traceable.

## 7. Why this is a real RLM pattern

The repository’s RLM implementation is structured like a real recursive planning-and-search loop:
- search plan generated from the user request
- evidence gathered from sub-queries
- loop expands or narrows based on result quality and breadth
- results are deduplicated and summarized
- workflow is bounded by `MAX_RESEARCH_STEPS`
- output is validated before delivery

In other words, this is not just a long prompt chain. It is a stateful agent loop using graph transitions, evidence tracking, and controlled recursion.

## 8. End-to-end RLM flow

The actual end-to-end flow is:

1. `supervisor` decides route
2. `research_plan` initializes the queue
3. `research_step` executes current sub-query
4. if search results are broad, `_split_query()` creates finer sub-queries
5. loop continues until completion or max budget reached
6. `research_aggregate` deduplicates evidence
7. `response_agent` produces the final answer

This is the central advanced workflow of the assistant and is the clearest expression of the project’s LangGraph design.
