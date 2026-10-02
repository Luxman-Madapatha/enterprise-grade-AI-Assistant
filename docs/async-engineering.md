# Async engineering in this repo

This repository uses Python async patterns to keep the AI assistant responsive while it performs I/O-bound work: HTTP requests, streaming chat events, tool execution, and MCP subprocess communication. The design is intentionally async-first for orchestration and real-time feedback rather than for CPU-heavy parallel computation.

## Where async is used

### 1. FastAPI endpoints are async
The application entry point in `app/main.py` defines async handlers for authentication, health checks, chat streaming, trace replay, and admin operations:

- `async def login(...)`
- `async def health()`
- `async def chat(...)`
- `async def get_traces(...)`
- `async def admin_reindex(...)`

These handlers run without blocking the event loop while requests are being processed. The chat endpoint returns a `StreamingResponse`, which is a natural fit for asynchronous event streaming.

### 2. Startup and shutdown use async lifecycle hooks
`app/main.py` uses `@asynccontextmanager` with `lifespan(app)`. During startup it runs:

- `configure_logging()`
- `setup_observability()`
- `await ensure_indexed()`

During shutdown it cleans up the MCP process with:

- `await get_mcp_client().close()`

This keeps startup and teardown deterministic and non-blocking.

### 3. Real-time progress is streamed through an async event bus
`app/agents/events.py` implements an in-process pub/sub system with `asyncio.Queue` and async publishing:

- `EventBus.subscribe()` creates a queue per conversation
- `await queue.put(event)` pushes typed events to subscribers
- `publish_event(...)` is an async wrapper used by agent nodes

The chat loop in `app/main.py` creates a background task with:

- `task = asyncio.create_task(_run_turn(user, session_id, message))`

Then it continuously reads from the queue using:

- `await asyncio.wait_for(queue.get(), timeout=45.0)`

This enables the browser UI to display agent state, tool activity, and final results as they happen in real time.

### 4. Tool execution is bounded and async-safe
`app/tools/base.py` wraps every tool call in a common execution pattern:

- RBAC check via `assert_tool_allowed(...)`
- parameter validation via `validate_tool_params(...)`
- `await asyncio.wait_for(self.execute(cleaned), timeout=settings.tool_timeout_seconds)`

That means a bad or slow tool cannot block the entire system indefinitely. The repo intentionally treats tool calls as asynchronous operations with explicit timeouts and graceful failure handling.

### 5. MCP communication uses asyncio subprocesses
`app/tools/mcp_client.py` starts a child Python process with:

- `asyncio.create_subprocess_exec(...)`

It then reads JSON-RPC responses asynchronously from `stdout` in `_reader()`, keeps track of pending futures, and resolves responses via `await fut` semantics. This avoids blocking the main agent loop while the MCP server is doing work.

## Why this design matters

This repo uses async engineering to solve the core agentic AI challenge: the assistant must remain responsive while it is doing several things at once:

- handling incoming chat requests
- streaming status updates back to the frontend
- running the LangGraph flow
- invoking tools
- waiting on MCP or LLM-backed services
- updating memory and traces

Without async orchestration, the app would block on waiting operations and the live activity panel would stall or freeze.

## Design patterns used here

- Async HTTP handlers for FastAPI
- Async background tasks for agent execution
- `asyncio.Queue` for event streaming
- `asyncio.wait_for` for bounded timeouts
- `asyncio.create_subprocess_exec` for isolated MCP processes
- Graceful cancellation and error handling so observability never crashes the agent

## Overall engineering takeaway

The async model in this repo is best described as asynchronous orchestration for an event-driven AI system: the frontend and backend stay interactive while the assistant orchestrates retrieval, reasoning, tools, and trace collection in the background. It is a strong fit for AI agents that need to stream state, degrade gracefully under failure, and keep latency under control.
