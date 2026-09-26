"""Tests for token issuing and verification."""
from __future__ import annotations

from app.auth.tokens import issue_token, verify_token
from app.models.schemas import Role, User


def test_roundtrip():
    user = User(username="alice", full_name="Alice", role=Role.ANALYST)
    token = issue_token(user)
    verified = verify_token(token)
    assert verified is not None
    assert verified.username == "alice"
    assert verified.role == Role.ANALYST


def test_tampered_token_rejected():
    user = User(username="alice", full_name="Alice", role=Role.ANALYST)
    token = issue_token(user)
    encoded, signature = token.split(".", 1)
    forged = f"{encoded}.{'0' * len(signature)}"
    assert verify_token(forged) is None


def test_garbage_rejected():
    assert verify_token("not-a-token") is None
