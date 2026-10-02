# Repository documentation summary

This repository includes a focused set of engineering documents that explain the product, architecture, security, observability, and operational trade-offs. Together they give a complete picture of the system from design through implementation and evaluation.

## Core project docs

### README.md
The main entry point for the project. It explains the product purpose, the implemented features, startup instructions, expected user roles, and the repository layout. It is the best starting point for a new developer or reviewer.

### docs/architecture.md
The system design overview. It includes the high-level diagram, the request flow for a single user turn, the key architecture decisions, security model, and assumptions/trade-offs. This is the most useful summary document for understanding how the app fits together.

### docs/agent-architecture-detailed.md
A deeper explanation of the agent structure and orchestration model. It expands on how the LangGraph supervisor, retrieval step, research path, and response agent interact.

### docs/langgraph-usage.md
A practical guide to the LangGraph usage patterns in the codebase. It explains how the graph is structured and how state, decisions, and execution flow are managed during agent runs.

## Retrieval and reasoning docs

### docs/rag-design.md
Details the retrieval architecture, including hybrid search, vector retrieval, document indexing, and chunk attribution. This is the document to read for understanding how the assistant grounds answers in documents.

### docs/rlm-implementation.md
Explains the Recursive Language Model pattern used by the project: task decomposition, targeted retrieval, bounded recursive re-querying, and aggregation. This is the design document for the multi-step reasoning loop.

## Security and platform docs

### docs/security-and-guardrails.md
The most complete security document in the repo. It covers prompt injection defense, output validation, safety checks, access control assumptions, and guardrails for dangerous behaviors.

### docs/rbac.md
Describes the role-based access control model in detail. It explains user roles, signed bearer tokens, server-side authorization, and the tool-level enforcement model.

### docs/observability.md
Covers how this system records trace data and emits real-time event streams for observability. It explains how the UI can show the agent activity while the request is executing and how traces are replayed.

## Engineering practice docs

### docs/async-engineering.md
Summarizes how the application uses async Python patterns across the backend, event bus, background jobs, and MCP subprocess communication. It explains why async orchestration is central to the product’s responsiveness.

### docs/code-quality.md
Evaluates the codebase from a software engineering perspective. It covers strengths, trade-offs, maintainability, and the difference between a strong demo/MVP and a hardened production system.

## Supporting artifacts

### docs/agent-architecture-summary.pdf
A condensed visual summary of the core architecture. Useful as a quick reference or presentation artifact.

## Recommended reading order

For a new reviewer, the most useful sequence is:

1. README.md
2. docs/architecture.md
3. docs/langgraph-usage.md
4. docs/rag-design.md
5. docs/security-and-guardrails.md
6. docs/observability.md
7. docs/async-engineering.md
8. docs/rbac.md
9. docs/code-quality.md

## Overall purpose of the documentation set

The documentation covers the full lifecycle of the project:

- what the product does
- how the architecture is organized
- how the agents reason and retrieve information
- how the system stays secure
- how it streams activity and records observability
- how it implements async and RBAC patterns
- how strong the code is as an engineering artifact

This makes the documentation set well-suited for onboarding, review, architecture understanding, and assessment preparation.
