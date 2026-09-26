"""Output guardrails.

Guards against the four failure classes required by the assignment:

* unsafe tool execution      -> handled in tool wrappers (RBAC + validation)
* unauthorized access        -> handled in tool wrappers (RBAC)
* hallucinated citations     -> every cited chunk id must exist in retrieval
* invalid responses          -> content checks (empty, leakage, brand safety)

The brand-safety check is deliberately small; plug in a moderation endpoint in
production. ``BRAND`` is used as the fictional company context ("commercial
bank" per the assignment).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.logging_config import get_logger

logger = get_logger(__name__)

BRAND = "Madapatha Commercial Bank"

_API_KEY_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|-----BEGIN\s+(RSA|EC|OPENSSH|PRIVATE)\s+KEY)"
)
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

_BRAND_SAFETY_TERMS = {
    "guarantee a profit",
    "guaranteed returns",
    "defraud",
    "launder money",
    "money laundering",
    "insider trading",
    "steal customer funds",
    "phishing",
}


@dataclass
class GuardrailResult:
    allowed: bool = True
    reasons: list[str] = field(default_factory=list)
    sanitized_answer: str = ""

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reasons": self.reasons,
        }


def validate_citations(
    answer: str, citations: list[str], valid_ids: set[str]
) -> tuple[str, list[str]]:
    """Keep only citations that actually point at retrieved chunks."""
    kept = [c for c in citations if c in valid_ids]
    removed = set(citations) - set(kept)
    if removed:
        logger.warning("hallucinated_citations_removed", removed=sorted(removed))
    return answer, kept


def check_content_safety(answer: str) -> list[str]:
    """Return a list of violations (empty means safe)."""
    reasons: list[str] = []
    lowered = answer.lower()

    if _API_KEY_PATTERN.search(answer):
        reasons.append("possible_secret_leak")
    if _SSN_PATTERN.search(answer):
        reasons.append("possible_pii_leak")
    for term in _BRAND_SAFETY_TERMS:
        if term in lowered:
            reasons.append("brand_safety")
            break
    return reasons


def guard_answer(
    answer: str,
    citations: list[str],
    valid_chunk_ids: set[str],
) -> GuardrailResult:
    result = GuardrailResult()

    if not answer or not answer.strip():
        result.allowed = False
        result.reasons.append("empty_answer")
        return result

    if len(answer) > 20000:
        result.allowed = False
        result.reasons.append("answer_too_long")
        return result

    answer, citations = validate_citations(answer, citations, valid_chunk_ids)
    result.sanitized_answer = answer

    for reason in check_content_safety(answer):
        result.reasons.append(reason)

    if result.reasons:
        result.allowed = False
        logger.warning("guardrail_blocked", reasons=result.reasons)

    return result
