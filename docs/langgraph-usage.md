# LangGraph usage

In this architecture, LangGraph is the orchestration engine that manages the agent workflow rather than the model itself.

The main idea:
- The LLM is not allowed to "just answer."
- LangGraph coordinates multi-step reasoning, retrieval, tool calls, and safety checks.
- Each step is a node in a graph, and edges decide what happens next.

## How it is used here

### 1. Supervisor node

- Entry point for every request.
- Classifies intent:
  - direct answer
  - retrieval needed
  - research/deep analysis needed
  - tool-assisted workflow
- Decides which downstream path to take.

### 2. Retrieval agent node

- Runs hybrid retrieval:
  - dense vector search
  - sparse keyword search
  - RRF fusion
- Produces evidence chunks and citations.

### 3. Research plan node

- Creates a plan for deeper tasks.
- Breaks complex questions into sub-questions or retrieval steps.
- This is the "reasoning plan" before agent execution.

### 4. Research step node

- Executes a bounded recursive loop:
  - retrieve more context
  - evaluate if the answer is sufficient
  - continue if missing evidence
  - stop when it reaches the saturation point
- This is the recursive "RLM" cycle described in the architecture.

### 5. Research aggregate node

- Collates the evidence gathered from all research steps.
- Builds a clean fact set for the final answer.

### 6. Response agent node

- Produces the final answer from the evidence.
- Then output safety and guardrail checks happen afterward.

## Why LangGraph is a good fit here

- Multi-agent workflow control
  - Each specialized agent is a graph node.
- State persistence
  - The graph keeps state across turns and sub-steps.
- Streaming and observability
  - The API can receive events from each node as they happen.
- Checkpointing
  - Work can be resumed, replayed, and debugged.
- Conditional branching
  - The graph can choose retrieval vs answer vs research path dynamically.

## Typical state structure

The graph state likely contains things like:
- `user_message`
- `role` / `permissions`
- `retrieved_documents`
- `evidence_chunks`
- `tool_results`
- `citations`
- `errors`
- `guardrail_status`
- `final_response`
- `memory_context`

This is important because the graph is not just using raw chat messages. It is managing structured workflow state.

## Example workflow pattern

```python
from langgraph.graph import StateGraph, END


def supervisor(state):
    intent = classify_intent(state["user_message"])
    state["intent"] = intent
    return state


def retrieval_agent(state):
    docs = hybrid_search(state["user_message"])
    state["retrieved_documents"] = docs
    return state


def research_plan(state):
    plan = create_research_plan(state["user_message"], state["retrieved_documents"])
    state["research_plan"] = plan
    return state


def research_step(state):
    # iterative loop
    return state


def response_agent(state):
    answer = generate_answer(state)
    state["final_response"] = answer
    return state


graph = StateGraph()
graph.add_node("supervisor", supervisor)
graph.add_node("retrieval_agent", retrieval_agent)
graph.add_node("research_plan", research_plan)
graph.add_node("research_step", research_step)
graph.add_node("response_agent", response_agent)

graph.add_edge("supervisor", "retrieval_agent")
graph.add_edge("retrieval_agent", "research_plan")
graph.add_edge("research_plan", "research_step")
graph.add_edge("research_step", "response_agent")
graph.add_edge("response_agent", END)
```

The recursive research loop is usually implemented with:
- condition functions
- loop control
- max iteration counts
- "continue vs finish" branching

This is how the system avoids unbounded reasoning.

## How it interacts with tools

LangGraph orchestrates tool execution, but the actual tool invocations are wrapped with security policies:
- RBAC before tool execution
- validation of arguments
- timeouts
- safe execution restrictions
- structured errors returned to the graph

So the graph can say:
- "tool call allowed"
- "tool result captured"
- "progress to next node"
- "reject if unauthorized"

## Event streaming

Each node emits structured events into an in-process bus:
- node started
- node completed
- tool invoked
- retrieval complete
- research step complete
- answer generated

The API then sends those events to the browser via SSE.

This gives you:
- real-time progress tracking
- auditability
- better debugging
- a visible "thinking" trace for users

## Why not just call the LLM directly?

Because this design needs:
- deterministic routing
- explicit security checks
- multiple toolchains
- evidence-based responses
- bounded iteration
- traceability

LangGraph gives the system workflow discipline. Without it, the agent would just be a freeform prompt loop, which is too risky in an enterprise setting.

## Summary

- LangGraph is the control plane
- the model is the executor
- tools and retrieval are the data sources
- guardrails and validation are enforced around the graph

In short, LangGraph makes the system workflow-driven, safe, observable, and suitable for enterprise AI use cases.
