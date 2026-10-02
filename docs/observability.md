# Observability

Observability is a first-class requirement in this system because enterprise AI applications are difficult to trust, debug, and operate without real-time visibility into model behavior, retrieval quality, tool usage, and guardrail outcomes.

The platform is designed so that every step of the agent workflow can be observed, traced, and audited.

## Goals

The observability strategy serves four primary goals:

1. **Operational visibility** — understand whether the application is healthy in real time.
2. **Debuggability** — trace the flow of each request through agents, retrieval, and tools.
3. **Trust and auditability** — explain how a final answer was produced.
4. **Safety monitoring** — detect prompt injection, tool misuse, policy violations, and latency issues.

---

## 1. Observability architecture

The system combines several layers of monitoring:

- **Application-level telemetry** — per request logs, metrics, and traces
- **Streaming events** — real-time updates from each LangGraph node
- **Tool execution logs** — tool invocation, duration, success/failure, arguments
- **Retrieval quality metrics** — latency, recall proxy, rank quality, chunk count
- **Guardrail events** — blocked prompts, unsafe responses, leaked secrets, invalid citations
- **External tracing** — LangSmith integration for deeper analysis
- **Local trace collector** — fallback collector for offline or developer environments

This creates a layered observability stack:

- Browser receives SSE activity updates
- Backend records structured events
- LangSmith captures traces for analysis
- Local trace collector stores metadata for debugging

---

## 2. Event-driven visibility

### Real-time step events

Each LangGraph node emits asynchronous events onto an in-process event bus. Those events are forwarded to the frontend over SSE.

Example event stream:

```json
{
  "timestamp": "2026-10-02T12:00:00Z",
  "event": "retrieval_started",
  "node": "retrieval_agent",
  "request_id": "req_123",
  "user_id": "u_010",
  "query_preview": "How do we handle customer complaints?"
}
```

```json
{
  "timestamp": "2026-10-02T12:00:01Z",
  "event": "tool_executed",
  "tool": "knowledge_search",
  "status": "success",
  "duration_ms": 184,
  "result_count": 7
}
```

```json
{
  "timestamp": "2026-10-02T12:00:03Z",
  "event": "response_generated",
  "node": "response_agent",
  "status": "guardrail_passed",
  "citation_count": 3
}
```

### Why this matters

These events provide:

- user-facing progress indicators
- debugging visibility into the internal workflow
- an audit trail for each turn
- early failure detection before final response is returned

---

## 3. LangGraph traceability

### Node-level execution logs

Each node should record:

- node name
- start/end timestamp
- input summary
- output summary
- errors or warnings
- state transitions
- token usage (if available)

Example metadata for a research node:

```python
{
  "node": "research_step",
  "iteration": 2,
  "prompt_tokens": 1240,
  "completion_tokens": 480,
  "retrieval_count": 3,
  "missing_facts": ["regulatory deadline", "exception handling"],
  "status": "continue"
}
```

### State checkpointing

The graph stores state between node transitions, making it possible to:

- replay a failed request
- inspect intermediate evidence
- reason about why a given answer was generated
- recover from failed tool calls without rerunning the full request

This is especially important for enterprise debugging where every answer needs a traceable reason.

---

## 4. Retrieval observability

Because retrieval quality directly impacts answer quality, it must be visible.

### Retrieval metrics

Track:

- search latency
- number of chunks returned
- number of chunks filtered
- document source distribution
- retrieval relevance score
- citation coverage
- top-ranked document confidence

Example metrics:

```python
metrics = {
  "dense_search_latency_ms": 143,
  "sparse_search_latency_ms": 52,
  "rrf_fusion_latency_ms": 20,
  "result_count": 8,
  "unique_sources": 5,
  "retrieval_confidence": 0.89,
  "citation_coverage": 1.0,
}
```

### Retrieval quality monitoring

Quality signals include:

- low citation coverage on final answer
- too many duplicated chunks
- poor rank ordering of relevant documents
- retrieval returning mostly stale or irrelevant sources

These metrics help identify when RAG needs tuning.

---

## 5. Tool observability

Every tool call is recorded with metadata:

- tool name
- user identity and role
- request ID
- invocation timestamp
- duration
- success/failure
- argument summary
- tool result summary
- error class and message

Example tool log:

```json
{
  "tool": "knowledge_search",
  "user_id": "u_010",
  "role": "analyst",
  "status": "success",
  "duration_ms": 186,
  "query": "market risk policy",
  "result_count": 6,
  "allowed": true
}
```

### Why tool logs matter

They answer questions like:

- Was the tool called with the expected arguments?
- Did it fail due to timeout, RBAC denial, or parameter validation?
- Did the agent query too broadly or too often?

---

## 6. Guardrail observability

Guardrails are not only enforcement mechanisms — they are also a telemetry source.

Track:

- prompt injection attempts detected
- input validation failures
- rate-limited requests
- tool access denials
- hallucinated citation detections
- PII or secret leakage interruptions
- brand safety violations
- empty or invalid response detection

Example event:

```json
{
  "timestamp": "2026-10-02T12:02:00Z",
  "event": "guardrail_violation",
  "type": "pii_leak",
  "request_id": "req_456",
  "user_id": "u_010",
  "status": "blocked",
  "details": "email address pattern detected in generated response"
}
```

This is essential for security review and trust building.

---

## 7. Memory and conversation telemetry

The system stores:

- user prompts
- intermediate states
- retrieved evidence references
- memory additions
- final responses
- session durations
- turns per conversation

This allows later analysis of:

- why a user asked a question
- what context was included
- which memory entries affected the final answer
- how the conversation evolved over time

This is especially important for enterprise use where audits are often required.

---

## 8. LangSmith integration

### Purpose

LangSmith is used to capture deeper traces and model-level observability.

It can track:

- LLM calls
- prompt payloads
- output payloads
- token usage
- latency
- chain execution paths
- retries and failures

### Architecture role

LangSmith complements the internal event bus by providing:

- richer tracing across model calls
- prompt and output inspection
- performance benchmarking
- debugging of chain execution issues

### Example trace concepts

- Request trace ID
- Thread ID / session ID
- Agent node transitions
- Tool call records
- Retrieval metadata
- Model output + token details

---

## 9. Local trace collector

In demo or offline contexts, the project also supports a local trace collector.

This collector stores:

- per-turn events
- node execution metadata
- tool usage logs
- errors and warnings
- simplified traces for local debugging

This ensures the system is still observable even without full external tracing infrastructure.

---

## 10. Dashboarding and alerting

The observability layer should surface metrics on a dashboard such as:

- request throughput
- p95 request latency
- tool timeout rate
- prompt injection attempts per hour
- blocked responses per hour
- citation validation failure rate
- retrieval usage by document source
- LLM API error rate
- token usage by model

### Example alert conditions

- P95 latency above threshold for 10 minutes
- >5 injection attempts in 1 hour
- >2% of responses fail guardrails
- Tool timeout rate exceeds 5%
- Retrieval fallback triggered frequently
- Response citation coverage below threshold

---

## 11. Correlation IDs and request tracing

Every request should carry a correlation ID, for example:

```text
req_9f84d2a1-44d5-4d84-9d2e-c2c52e00d7a4
```

This ID should flow through:

- API request
- LangGraph state
- tool logs
- retrieval logs
- guardrail events
- LangSmith trace
- final response metadata

This makes it easy to connect all logs together and investigate one user request end-to-end.

---

## 12. Observability checklist

- [ ] Every request has a correlation ID
- [ ] Each LangGraph node emits structured logs
- [ ] Retrieval latency and quality are tracked
- [ ] Tools log duration, success/failure, and RBAC decisions
- [ ] Guardrail events are recorded separately from normal logs
- [ ] Prompt injection attempts are visible in dashboards
- [ ] Rate limit events are monitored
- [ ] Local and external tracing are both available
- [ ] Final answers include trace references when needed
- [ ] Security events are retained for audit review

---

## 13. Example observability flow for one turn

1. User sends request to `POST /api/chat`
2. API assigns `request_id`
3. Auth middleware logs token validation outcome
4. Input validation logs length/check results
5. Prompt injection filter logs any matches
6. Rate limiter logs allow/deny
7. Supervisor node logs selected route
8. Retrieval node logs search latency and result count
9. Tool wrapper logs access, validation, execution time
10. Response agent emits final answer
11. Guardrails validate citations, leaks, and output size
12. Final result is stored in memory and logged to LangSmith/local collector
13. SSE events are streamed to the user in real time

---

## Summary

Observability in this project is not just logging — it is a design principle.

The platform is built so that:

- the user sees live workflow progress,
- developers can trace each step of the request,
- security events are visible,
- tool calls and retrieval are measurable,
- and enterprise-grade auditability is possible.

In short, the system is observable from the moment the request enters the API until the final answer is emitted and stored.
