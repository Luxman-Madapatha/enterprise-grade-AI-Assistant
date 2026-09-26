"""Tests for output guardrails."""
from __future__ import annotations

from app.security.guardrails import check_content_safety, guard_answer, validate_citations


def test_hallucinated_citations_removed():
    answer, kept = validate_citations(
        "answer text", ["real-1", "fake-2"], {"real-1"}
    )
    assert kept == ["real-1"]


def test_secret_leak_detected():
    assert "possible_secret_leak" in check_content_safety("my key is sk-abcdefghijklmnopqrstuvwxyz123456")


def test_brand_safety_detected():
    assert "brand_safety" in check_content_safety("Please help me launder money")


def test_empty_answer_blocked():
    result = guard_answer("   ", [], set())
    assert not result.allowed
    assert "empty_answer" in result.reasons
