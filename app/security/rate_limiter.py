"""Token-bucket rate limiting.

Each user gets an independent bucket with configurable capacity and refill
rate. The check is atomic and never blocks the event loop. When a bucket is
empty the request is rejected with a graceful 429-style response rather than
failing the application.
"""
from __future__ import annotations

import asyncio
import time

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class TokenBucket:
    def __init__(self, capacity: float, refill_per_second: float) -> None:
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> bool:
        """Try to consume ``tokens``; return False when the bucket is empty."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self.capacity, self._tokens + elapsed * self.refill_per_second
            )
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


class RateLimiter:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._buckets: dict[str, TokenBucket] = {}

    def _bucket(self, key: str) -> TokenBucket:
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                capacity=settings.rate_limit_capacity,
                refill_per_second=settings.rate_limit_refill_per_second,
            )
        return self._buckets[key]

    async def allow(self, key: str) -> bool:
        if not self.enabled:
            return True
        allowed = await self._bucket(key).acquire()
        if not allowed:
            logger.warning("rate_limit_exceeded", key=key)
        return allowed


# Module-level singleton used by the API layer.
rate_limiter = RateLimiter(enabled=settings.rate_limit_enabled)
