# RAG Design

This project implements a hybrid, metadata-aware retrieval pipeline with role-based access control and a deterministic orchestration layer. The design is intentionally built for an enterprise-style assistant that can answer grounded questions from a document corpus while preserving security and traceability.

## 1. Retrieval architecture overview

The end-to-end flow is:

1. User submits a question to the backend.
2. The retrieval agent processes the query.
3. The knowledge search tool executes a hybrid search against the document index.
4. Relevant chunks are filtered by access level and returned.
5. The response agent composes an answer from the retrieved evidence.
6. Output guardrails validate the response before sending it back to the user.

The concrete retrieval path is implemented in:

- `app/agents/retrieval.py`
- `app/tools/knowledge_search.py`
- `app/retrieval/hybrid_search.py`
- `app/retrieval/vector_store.py`

## 2. Document ingestion and chunking

The indexing process begins with `app/retrieval/document_loader.py`.

Key behaviors:

- Reads markdown/text files from the configured documents directory.
- Parses optional frontmatter metadata such as:
  - `department`
  - `document_type`
  - `access_level`
  - `title`
  - `created_date`
- Keeps metadata attached to each chunk for downstream filtering.
- Splits text into sentence-aware chunks with a small overlap.
- Assigns stable chunk IDs such as `file-name-0`, `file-name-1`, and so on.

This means the retrieval layer preserves context about where a chunk came from and what security classification it carries.

## 3. Indexing pipeline

The indexing workflow is in `app/retrieval/indexer.py`.

At a high level:

- load documents
- chunk them
- produce embeddings
- upsert vectors into the configured vector store

The design supports lazy indexing on startup when the store is empty, which keeps the app easy to run in a local/PoC environment.

## 4. Vector store abstraction

The repository implements a unified vector-store interface in `app/retrieval/vector_store.py`.

It supports two backends:

### Local backend

- In-memory dense index using numpy
- BM25 sparse index using `rank_bm25`
- JSON persistence for local use
- Intended as the default fallback when Pinecone credentials are absent

### Pinecone backend

- Dense vector search against Pinecone
- Local BM25 mirror for sparse ranking
- Hybrid fusion with the same rank-based logic as the local backend

This abstraction keeps the rest of the system agnostic to the storage backend.

## 5. Hybrid retrieval: dense + sparse

The hybrid search engine is implemented in `app/retrieval/hybrid_search.py`.

### Dense retrieval

- Encodes the user query into a vector embedding.
- Searches the vector index for semantically similar chunks.
- Best for conceptual similarity and paraphrase matching.

### Sparse retrieval

- Uses BM25 keyword matching over the corpus.
- Best for exact terms, names, product IDs, incident keywords, policy clauses, and entity-focused queries.

### Reciprocal Rank Fusion (RRF)

The system fuses the results from both search methods using Reciprocal Rank Fusion.

The score contribution for a rank is approximated by:

- 1 / (k + rank + 1)

where `k` is a constant and `rank` is the position in the candidate list.

This is a good fit because:

- dense and sparse scores are on different scales
- RRF does not require training or calibration
- it is robust and simple to reason about

The hybrid search does both operations concurrently via `asyncio.gather`, which keeps retrieval latency bounded by the slowest leg rather than the sum of both legs.

## 6. Access control and RBAC filtering

The retrieval tool enforces access levels in `app/tools/knowledge_search.py`.

Role-based access mapping:

- `VIEWER`: public, internal
- `ANALYST`: public, internal, confidential
- `ADMINISTRATOR`: public, internal, confidential, restricted

The tool merges:

- caller-provided filter parameters
- access control restrictions defined by role

This is a crucial design choice: the model is not allowed to select documents outside the user’s allowed access scope.

In other words, the retrieval tool acts as the trust boundary between the untrusted LLM reasoning process and the controlled enterprise data layer.

## 7. Retrieval agent integration

`app/agents/retrieval.py` defines the retrieval stage in the LangGraph orchestration.

It does the following:

- reads the current user query
- resolves the user role
- executes the knowledge search tool
- records retrieval events for observability
- returns the ranked chunk list to the agent graph

The node publishes events such as:

- `agent_state`
- `retrieval`

This makes the retrieval stage observable in real time from the frontend and also helps system debugging.

## 8. Why this RAG design is strong

This implementation balances retrieval quality and operational safety:

- Hybrid retrieval improves recall by combining semantic and lexical search.
- Metadata-aware indexing supports enterprise filtering by domain, sensitivity, and content type.
- RBAC enforcement prevents privilege escalation through tool usage.
- Local fallback backend keeps the system workable without cloud dependencies.
- Deterministic settings and structured observability support enterprise auditability.

## 9. Design intent

The project is not just a toy RAG demo. It follows a pattern commonly used in enterprise information assistants:

- Search over grounded sources
- Filter by authorization
- Keep evidence visible to the model
- Validate output before user delivery
- Record traceability for debugging and review

This makes the retrieval layer suitable for internal knowledge assistants, incident analysis, policy lookup, and operational support workflows.

## 10. Summary

The repo’s RAG design is a hybrid retrieval system built around:

- chunked document ingestion
- embedding-based dense retrieval
- BM25 sparse retrieval
- RRF score fusion
- role-aware document filtering
- a secure tool wrapper
- agent orchestration with end-to-end observability

That combination is a practical enterprise pattern: strong retrieval quality without sacrificing access control or traceability.
