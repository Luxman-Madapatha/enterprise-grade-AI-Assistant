"""Conversational memory.

Design decisions (documented in docs/architecture.md):

* **Session-scoped short-term memory** — a bounded rolling buffer per
  ``session_id``. Messages are stored as raw turns plus a lightweight summary.
  The buffer is trimmed by turn count *and* by a rough token estimate so the
  context window never overflows.
* **Graph state checkpointing** — the LangGraph ``MemorySaver`` checkpointer
  keeps the agent's internal state (plan, findings, retrieved chunks) across
  turns within the same thread/session.
* **Long-term memory (bonus)** — a compact JSON-backed store of resolved Q&A
  pairs that can be searched to bootstrap future turns, giving the assistant a
  lightweight "memory" that survives beyond a single session.

The buffer lives in-process for the POC; swap in Redis/Postgres for
horizontal scaling in production.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str
    citations: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "citations": self.citations,
            "timestamp": self.timestamp,
        }


def _estimate_tokens(text: str) -> int:
    # Rough heuristic: ~4 chars per token.
    return max(1, len(text) // 4)


class ConversationMemory:
    def __init__(self, max_turns: int = 10, max_tokens: int = 4000) -> None:
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self._sessions: dict[str, list[Turn]] = {}
        self._lock = threading.Lock()

    def add(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[str] | None = None,
    ) -> None:
        with self._lock:
            turns = self._sessions.setdefault(session_id, [])
            turns.append(Turn(role=role, content=content, citations=citations or []))
            self._trim(turns)

    def _trim(self, turns: list[Turn]) -> None:
        # Trim by turn count.
        if len(turns) > self.max_turns * 2:
            turns[:] = turns[-(self.max_turns * 2):]
        # Trim by estimated token budget.
        total = sum(_estimate_tokens(t.content) for t in turns)
        while total > self.max_tokens and len(turns) > 2:
            removed = turns.pop(0)
            total -= _estimate_tokens(removed.content)

    def history(self, session_id: str, last_n: int | None = None) -> list[dict]:
        with self._lock:
            turns = self._sessions.get(session_id, [])
            if last_n:
                turns = turns[-last_n:]
            return [t.as_dict() for t in turns]

    def last_question(self, session_id: str) -> str | None:
        with self._lock:
            turns = self._sessions.get(session_id, [])
            for t in reversed(turns):
                if t.role == "user":
                    return t.content
        return None

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def active_sessions(self) -> int:
        with self._lock:
            return len(self._sessions)


# --------------------------------------------------------------------------- #
# Long-term memory (bonus): survives beyond a single session.
# --------------------------------------------------------------------------- #
class LongTermMemory:
    """Append-only JSON store of resolved Q&A pairs with keyword search."""

    _TOKEN_RE = re.compile(r"[a-zA-Z0-9]{2,}")

    def __init__(self, path: str = "data/long_term_memory.json") -> None:
        self.path = Path(path)
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._entries = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover
                logger.warning("long_term_memory_load_failed", error=str(exc))
                self._entries = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._entries, indent=2), encoding="utf-8"
        )

    def remember(self, question: str, answer: str, citations: list[str]) -> None:
        entry = {
            "question": question,
            "answer": answer,
            "citations": citations,
            "timestamp": time.time(),
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > 500:
                self._entries = self._entries[-500:]
            self._save()

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        query_tokens = set(self._TOKEN_RE.findall(query.lower()))
        if not query_tokens:
            return []
        scored = []
        for entry in self._entries:
            entry_tokens = set(
                self._TOKEN_RE.findall(entry["question"].lower())
            )
            overlap = len(query_tokens & entry_tokens)
            if overlap:
                scored.append((overlap, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]


conversation_memory = ConversationMemory()
long_term_memory = LongTermMemory()
