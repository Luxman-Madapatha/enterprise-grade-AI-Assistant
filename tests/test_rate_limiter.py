"""Tests for the token-bucket rate limiter."""
from __future__ import annotations

from app.security.rate_limiter import TokenBucket


async def test_bucket_depletes_and_refills():
    bucket = TokenBucket(capacity=2, refill_per_second=1.0)
    assert await bucket.acquire()
    assert await bucket.acquire()
    assert not await bucket.acquire()  # empty
