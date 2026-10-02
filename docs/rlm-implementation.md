# RLM implementation

RLM in this project is best understood as a bounded recursive research loop:

- Research plan
- Targeted retrieval
- Assess evidence sufficiency
- Re-enter retrieval if missing information
- Aggregate evidence
- Answer with guardrails

This is not "free-form recursive prompting." It is a structured loop with explicit stopping conditions.

## Core idea

The system does not dump the whole corpus or whole conversation into the model and hope for the best. Instead, it iteratively narrows the search:

1. Determine what information is missing.
2. Fetch only relevant evidence.
3. Evaluate whether the evidence is enough.
4. If not, repeat with a more focused query.
5. Stop when the confidence threshold is reached or the max recursion depth is hit.

## Typical RLM flow

- The supervisor decides that a task requires deeper reasoning.
- The research plan node creates sub-questions.
- The retrieval node fetches top relevant chunks.
- The research step node checks:
  - Is the answer supported?
  - Is there still a missing fact?
  - Has the iteration limit been reached?
- If yes, continue with another retrieval pass.
- Otherwise, aggregate and pass the result to the response agent.

## Pseudo-implementation

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ResearchState:
    query: str
    plan: List[str] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    missing_facts: List[str] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 3


def research_loop(state: ResearchState) -> ResearchState:
    # 1. Build plan if not yet created
    if not state.plan:
        state.plan = generate_plan(state.query)

    # 2. For each sub-question, retrieve targeted evidence
    for subq in state.plan:
        chunk = retrieve_targeted_context(subq)
        state.evidence.extend(chunk)

    # 3. Validate if evidence answers the question
    state.missing_facts = find_missing_facts(state.query, state.evidence)

    # 4. Stop if enough evidence or max depth reached
    if not state.missing_facts or state.iteration >= state.max_iterations:
        return state

    # 5. Recurse with a refined query
    state.iteration += 1
    new_query = build_refinement_query(state.query, state.missing_facts)
    state.query = new_query
    return research_loop(state)
```

In LangGraph terms, this becomes a node that conditionally loops until a stop condition is met.

## Example graph pattern

```python
from langgraph.graph import StateGraph, END


def research_plan_node(state):
    if not state.get("research_plan"):
        state["research_plan"] = build_research_plan(state["user_message"])
    return state


def research_step_node(state):
    state["evidence"] = retrieve_targeted_context(state["research_plan"])
    missing = find_missing_facts(state["user_message"], state["evidence"])
    state["missing_facts"] = missing
    return state


def should_continue(state):
    if state["missing_facts"] and state["loop_count"] < state["max_loops"]:
        return "research_step"
    return "aggregate"


graph = StateGraph()
graph.add_node("research_plan", research_plan_node)
graph.add_node("research_step", research_step_node)
graph.add_node("aggregate", lambda s: s)
graph.add_edge("research_plan", "research_step")
graph.add_conditional_edges(
    "research_step",
    should_continue,
    {
        "research_step": "research_step",
        "aggregate": "aggregate",
    },
)
graph.add_edge("aggregate", END)
```

## Key decision points inside RLM

### 1. What is missing?

Not "what is the answer?" First, determine the gap in evidence.

### 2. What is the cheapest targeted retrieval?

Query only the missing angle instead of re-running broad search.

### 3. Is the evidence trustworthy?

- citation check
- document relevance check
- injection detection
- source validation

### 4. Is the loop bounded?

- max iterations
- max retrieval count
- max token budget
- max tool calls

### 5. When to stop?

- missing facts are empty
- answer is sufficiently grounded
- recursion limit reached
- retrieval is producing low-value or duplicate chunks

## Recommended stopping criteria

- `missing_facts` is empty
- answer has citations covering claims
- confidence score crosses threshold
- `loop_count >= max_loops`
- token budget exceeded
- retrieval returns low-value or duplicate chunks

## Good implementation patterns

- Store a structured evidence list
  - `chunk_id`
  - `source`
  - `score`
  - `snippet`
  - `trust_level`

- Keep a research journal
  - what was asked
  - what was retrieved
  - what missing fact prompted the next search

- Prefer targeted follow-up queries
  - refine based on the missing fact, not a generic retry

- Add explicit summarization before the next loop
  - collapse evidence before continuing
  - prevent context explosion

## Example evidence structure

```python
{
  "chunk_id": "doc_14_3",
  "source": "policy_manual.pdf",
  "score": 0.92,
  "text": "...",
  "relevance_reason": "answers compliance question",
  "trusted": True,
}
```

## Why this is better than naive recursion

Naive recursion often causes:

- repeated searches with little novelty
- context bloat
- unbounded reasoning
- answer drift
- hallucinated citations

RLM solves this by making recursion evidence-driven and bounded.

## In this project specifically

The architecture describes:

- Research Plan node
- Research Step node
- Research Aggregate node
- RLM recursive loop

That means the algorithm is intended to:

- decompose a complex question
- retrieve only the most relevant evidence
- refine iteratively
- aggregate the facts
- pass them to the response agent

So the RLM implementation is essentially:

- a policy-driven, bounded, evidence-gathering reasoning loop
- orchestrated by LangGraph
- guarded by retrieval validation and answer safety checks

## Summary

RLM is the project’s structured approach to deep reasoning: use a loop to gather only what is necessary, stop when the evidence is sufficient, and keep the process observable, bounded, and auditable.
