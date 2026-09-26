"""In-process pub/sub event bus for real-time agent activity.

Each conversation gets a stream of typed events (agent state changes, tool
calls, retrieval status, memory updates, validation, final answer). The API
layer subscribes and forwards these to the browser as Server-Sent Events so the
evaluator can watch what the agent is doing internally, in real time.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from app.logging_config import get_logger
from app.observability.langsmith import trace_collector

logger = get_logger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, conversation_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(conversation_id, set()).add(queue)
        return queue

    def unsubscribe(self, conversation_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(conversation_id)
        if subs is not None:
            subs.discard(queue)
            if not subs:
                self._subscribers.pop(conversation_id, None)

    async def publish(
        self,
        conversation_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "payload": payload,
            "timestamp": time.time(),
        }
        # Persist to the trace collector so /api/traces can replay the session.
        trace_collector.add(conversation_id, event_type, payload)
        subs = list(self._subscribers.get(conversation_id, set()))
        for queue in subs:
            await queue.put(event)


event_bus = EventBus()


async def publish_event(
    conversation_id: str, event_type: str, payload: dict[str, Any]
) -> None:
    """Convenience wrapper used by agent nodes."""
    try:
        await event_bus.publish(conversation_id, event_type, payload)
    except Exception as exc:  # noqa: BLE001 - observability must never crash the agent
        logger.warning("event_publish_failed", error=str(exc))
