"""Lightweight HMAC-signed bearer tokens.

Dependency-free (stdlib only) token issuing/verification. Tokens encode the
username + role and are signed with the configured secret so the frontend can
authenticate each request without keeping server-side sessions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.config import settings
from app.models.schemas import User


def _sign(payload: str) -> str:
    return hmac.new(
        settings.auth_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def issue_token(user: User) -> str:
    now = int(time.time())
    body = {
        "sub": user.username,
        "role": user.role.value,
        "name": user.full_name,
        "iat": now,
        "exp": now + settings.token_expiry_minutes * 60,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(body).encode("utf-8")
    ).decode("utf-8")
    signature = _sign(encoded)
    return f"{encoded}.{signature}"


def verify_token(token: str) -> User | None:
    try:
        encoded, signature = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(_sign(encoded), signature):
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(encoded.encode("utf-8")))
    except (ValueError, json.JSONDecodeError):
        return None
    if body.get("exp", 0) < int(time.time()):
        return None
    return User(
        username=body["sub"],
        full_name=body.get("name", body["sub"]),
        role=body["role"],
    )
