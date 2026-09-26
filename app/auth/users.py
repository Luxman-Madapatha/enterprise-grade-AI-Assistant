"""Hardcoded users and roles (Option A from the assignment).

In a production system this would be replaced with Keycloak / an IdP. The
hardcoded table keeps the POC self-contained while still enforcing RBAC end to
end. Passwords are intentionally trivial for the demo; they would never be
stored in plain text in production.
"""
from __future__ import annotations

from app.models.schemas import Role, User

# username -> (password, full_name, role)
_USER_TABLE: dict[str, tuple[str, str, Role]] = {
    "viewer": ("viewer123", "Viewer User", Role.VIEWER),
    "analyst": ("analyst123", "Analyst User", Role.ANALYST),
    "admin": ("admin123", "Administrator", Role.ADMINISTRATOR),
}


def get_user(username: str) -> User | None:
    row = _USER_TABLE.get(username)
    if row is None:
        return None
    return User(username=username, full_name=row[1], role=row[2])


def authenticate(username: str, password: str) -> User | None:
    row = _USER_TABLE.get(username)
    if row is None:
        return None
    if row[0] != password:
        return None
    return User(username=username, full_name=row[1], role=row[2])


def list_users() -> list[User]:
    return [get_user(u) for u in _USER_TABLE]  # type: ignore[misc]
