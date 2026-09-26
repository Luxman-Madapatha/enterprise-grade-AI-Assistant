"""FastAPI application entry point.

Endpoints:
* POST /api/auth/login         — issue a signed bearer token
* GET  /api/health             — readiness + feature flags
* POST /api/chat               — stream the agent's activity + final answer (SSE)
* GET  /api/traces/{id}        — replay a conversation's trace events
* POST /api/admin/reindex      — rebuild the document index (admin only)
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.agents.events import event_bus, publish_event
from app.agents.graph import run_assistant
from app.auth.tokens import issue_token, verify_token
from app.auth.users import authenticate
from app.config import settings
from app.logging_config import configure_logging, get_logger
from app.memory.conversation_memory import conversation_memory, long_term_memory
from app.models.schemas import (
    ChatRequest,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    Role,
    User,
)
from app.observability.langsmith import setup_observability, trace_collector
from app.retrieval.indexer import ensure_indexed, index_documents
from app.retrieval.vector_store import get_vector_store
from app.security.input_validation import ValidationError, validate_user_request
from app.security.prompt_injection import scan_prompt
from app.security.rate_limiter import rate_limiter

logger = get_logger(__name__)

_INJECTION_BLOCK_SCORE = 0.8


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    setup_observability()
    await ensure_indexed()
    try:
        yield
    finally:
        # Gracefully terminate the MCP subprocess on shutdown.
        from app.tools.mcp_client import get_mcp_client

        await get_mcp_client().close()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
async def get_current_user(
    authorization: str | None = Header(default=None),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = verify_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    user = authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    logger.info("user_logged_in", username=user.username, role=user.role.value)
    return LoginResponse(access_token=issue_token(user), user=user)


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        llm_available=settings.llm_available,
        pinecone_available=settings.pinecone_available,
        langsmith_available=settings.langsmith_available,
        index_size=get_vector_store().count(),
    )


# --------------------------------------------------------------------------- #
# Chat (Server-Sent Events)
# --------------------------------------------------------------------------- #
def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@app.post("/api/chat")
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    # 1. Input validation.
    try:
        message = validate_user_request(body.message)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2. Prompt-injection screening.
    scan = scan_prompt(message)
    if scan.flagged and scan.score >= _INJECTION_BLOCK_SCORE:
        logger.warning("request_blocked_by_injection_guard", user=user.username)
        raise HTTPException(
            status_code=400,
            detail="Request blocked by prompt-injection protection.",
        )

    # 3. Rate limiting (token bucket, per user).
    if not await rate_limiter.allow(user.username):
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Please slow down."
        )

    session_id = body.session_id or str(uuid.uuid4())
    return StreamingResponse(
        _chat_event_stream(user, session_id, message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_turn(user: User, session_id: str, message: str) -> dict[str, Any] | None:
    """Execute one agent turn, emitting terminal + memory events."""
    try:
        final = await run_assistant(
            {"username": user.username, "role": user.role.value},
            session_id,
            message,
        )
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.exception("graph_execution_failed", session=session_id)
        await publish_event(session_id, "error", {"message": str(exc)})
        return None

    answer = final.get("final_answer", "")
    citations = list(final.get("citations") or [])

    # Memory: short-term conversational buffer + long-term Q&A store.
    conversation_memory.add(session_id, "user", message)
    conversation_memory.add(session_id, "assistant", answer, citations)
    if citations:
        long_term_memory.remember(message, answer, citations)

    await publish_event(
        session_id,
        "memory",
        {
            "message": "Conversation memory updated.",
            "turns": len(conversation_memory.history(session_id)),
            "long_term_entries": long_term_memory.size(),
        },
    )
    await publish_event(
        session_id,
        "final",
        {"answer": answer, "citations": citations},
    )
    return final


async def _chat_event_stream(
    user: User, session_id: str, message: str
) -> AsyncGenerator[str, None]:
    queue = event_bus.subscribe(session_id)
    await publish_event(
        session_id,
        "agent_state",
        {"node": "conversation", "message": "Conversation started.", "role": user.role.value},
    )
    task = asyncio.create_task(_run_turn(user, session_id, message))
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=45.0)
            except asyncio.TimeoutError:
                if task.done():
                    break
                continue
            yield _sse(event)
            if event["type"] in ("final", "error"):
                break
    finally:
        event_bus.unsubscribe(session_id, queue)
        if not task.done():
            task.cancel()


# --------------------------------------------------------------------------- #
# Traces & admin
# --------------------------------------------------------------------------- #
@app.get("/api/traces/{conversation_id}")
async def get_traces(
    conversation_id: str, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return {"conversation_id": conversation_id, "events": trace_collector.get(conversation_id)}


@app.post("/api/admin/reindex")
async def admin_reindex(user: User = Depends(get_current_user)) -> dict[str, Any]:
    if user.role != Role.ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="Administrator role required")
    count = await index_documents()
    return {"indexed_chunks": count}
