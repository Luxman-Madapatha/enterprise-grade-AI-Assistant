# Agent Architecture - Detailed Analysis

## Agent Architecture Overview

### System Components

The architecture consists of several interconnected layers:

**1. FastAPI Backend**
- **Authentication**: HMAC tokens + Role-Based Access Control (RBAC)
- **Rate Limiting**: Token bucket algorithm per user
- **Security**: Input validation, prompt injection detection, output guardrails
- **Real-time Updates**: Server-Sent Events (SSE) for streaming activity to frontend

**2. LangGraph Orchestration Layer**
The core agent system uses a multi-agent graph structure:

- **Supervisor Agent**: Intent classifier and task router
  - Routes requests to specialized agents (Retrieval, Research, Response)
  - Makes high-level orchestration decisions
  
- **Retrieval Agent**: Document and knowledge search
  - Interfaces with hybrid search system
  - Returns relevant context chunks
  
- **Research Plan Node**: Decomposes complex queries into research steps
  
- **Research Step Node**: Executes recursive loops (RLM - Recursive Loop Management)
  - Iteratively: explore → plan → retrieve targeted content → re-query
  - Avoids loading entire documents into context
  
- **Research Aggregate Node**: Combines findings from multiple research steps
  
- **Response Agent**: Generates final output with applied guardrails

**3. Tools Layer (RBAC-Gated)**
- **Knowledge Search**: Accesses the retrieval subsystem
- **Python Analysis**: Restricted AST-based code execution
- **MCP Client**: Connects to external MCP (Model Context Protocol) servers

### Data Flow for a Single Turn

1. **User Request** → `POST /api/chat` with bearer token
2. **Authentication** → Verify token, resolve user + role
3. **Input Validation** → Check length, control characters
4. **Prompt Injection Screening** → Block high-confidence injection attempts
5. **Rate Limiting** → Per-user token bucket admission
6. **LangGraph Execution** → Supervisor classifies intent and routes task
7. **Event Streaming** → Nodes emit typed events to in-process bus → forwarded as SSE
8. **Tool Execution** → Wrapped tools enforce RBAC + validation + timeouts
9. **Output Guardrails** → Filter hallucinated citations, PII/secrets, brand safety
10. **Memory & Tracing** → Record turn in memory + LangSmith

### Retrieval System

**Hybrid Search with Reciprocal Rank Fusion (RRF)**
- **Dense Search**: Pinecone or local vector store (semantic matching)
- **Sparse Search**: BM25 (exact keyword matching)
- **Fusion**: RRF combines both scores without requiring training

### Security Model

**Prompt Injection Defense**
- Heuristic pre-screening (instruction overrides, prompt leaks, exfiltration patterns)
- Retrieved content wrapped in `<untrusted_document_content>` delimiters
- Output validation catches system prompt/secret leaks

**Authorization & Access Control**
- RBAC enforced at tool wrapper construction level
- Role is bound at tool creation; agents cannot escalate privileges
- Tool-level access filters based on user role

**Input & Output Validation**
- All requests validated against allow-lists with length caps
- Control character rejection
- Citation validation (hallucinated citations must map to retrieved chunks)

**Rate Limiting & Authentication**
- Token bucket algorithm per user
- HMAC-signed, expiring bearer tokens
- Configurable capacity and refill rates

### Error Handling & Graceful Degradation

| Failure Scenario | Behavior |
|---|---|
| LLM unavailable | Falls back to deterministic supervisor/template answers |
| Pinecone down | Auto-fallback to local vector store |
| MCP server fails | Structured error returned; research continues |
| Tool timeout | `asyncio.wait_for` with graceful error result |
| Invalid request | Returns 400/401/403/429 with clear error detail |

### Key Architectural Decisions

| Decision | Rationale |
|---|---|
| **LangGraph** | Native state graphs, checkpointing, streaming for observable multi-agent workflows |
| **Supervisor + Specialized Agents** | Separation of concerns; each agent independently testable and debuggable |
| **RLM (Recursive Loop)** | Iterative refinement avoids context overload from full documents |
| **Hybrid Search + RRF** | Semantic + keyword searches complement each other; RRF is training-free and robust |
| **Local Fallbacks** | Mock LLM, hashing embeddings, local index enable offline POC and graceful degradation |
| **RBAC in Tool Wrappers** | Role binding at construction prevents privilege escalation via agent reasoning |
| **Temperature 0** | Deterministic, auditable, reproducible behavior for enterprise |
| **OpenAI-Compatible Client** | Works with OpenAI, Azure, Anthropic, Ollama, vLLM via single interface |

### Technology Stack

- **Language**: Python (99.8%)
- **API Framework**: FastAPI
- **Agent Orchestration**: LangGraph
- **Vector Database**: Pinecone (with local fallback)
- **Search**: BM25 + Dense embeddings
- **LLM**: OpenAI-compatible (default: gpt-4o-mini, temperature 0)
- **Tracing**: LangSmith
- **Frontend**: Streamlit
- **Protocol**: MCP (Model Context Protocol) for tool extensibility

### Production Readiness Considerations

**Assumptions for POC**
- Single-process deployment (in-memory event bus)
- Dummy enterprise data and sample documents

**Production Migration Path**
- Event bus → Redis/Postgres (for distributed deployments)
- Token-based auth → Keycloak or similar
- Local embeddings → Real OpenAI embeddings
- Local BM25 → Pinecone sparse vectors
- Full MCP protocol implementation

This architecture demonstrates enterprise security patterns (RBAC, guardrails, determinism) while maintaining flexibility through abstraction layers and graceful degradation paths.
