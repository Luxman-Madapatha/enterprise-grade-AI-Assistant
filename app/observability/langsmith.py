"""Observability setup (LangSmith) + local trace collector.

* LangSmith (mandatory requirement) — when ``LANGSMITH_API_KEY`` is present we
  enable LangChain tracing so every conversation, tool call, agent transition
  and retrieval op is recorded and inspectable in the LangSmith UI.
* ``TraceCollector`` — a lightweight in-memory event log per conversation that
  always works (even without LangSmith), powering the frontend activity panel
  and the ``/api/traces`` debug endpoint.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


def setup_observability() -> None:
    """Configure LangSmith tracing if credentials are available."""
    if settings.langsmith_available:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        logger.info("langsmith_enabled", project=settings.langsmith_project)
    else:
        # Tracing stays local; LangSmith is optional at runtime but the code
        # path is identical.
        logger.info("langsmith_disabled_using_local_traces")


def trace_config(user: str, session_id: str) -> dict[str, Any]:
    """Build the config dict passed into every LangGraph invocation."""
    return {
        "configurable": {"thread_id": session_id, "user": user},
        "metadata": {
            "user": user,
            "session_id": session_id,
            "app": settings.app_name,
        },
    }


class TraceCollector:
    """In-memory event log keyed by conversation id (fallback trace store)."""

    def __init__(self, max_conversations: int = 500) -> None:
        self._events: dict[str, list[dict]] = {}
        self._lock = threading.Lock()
        self.max_conversations = max_conversations

    def add(self, conversation_id: str, event_type: str, payload: dict) -> None:
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "payload": payload,
            "timestamp": time.time(),
        }
        with self._lock:
            events = self._events.setdefault(conversation_id, [])
            events.append(event)
            if len(events) > 500:
                events[:] = events[-500:]
            if len(self._events) > self.max_conversations:
                oldest = next(iter(self._events))
                self._events.pop(oldest, None)

    def get(self, conversation_id: str) -> list[dict]:
        with self._lock:
            return list(self._events.get(conversation_id, []))

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self._events.pop(conversation_id, None)


trace_collector = TraceCollector()
