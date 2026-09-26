"""Shared Pydantic schemas."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Role(str, Enum):
    """User roles used for Role Based Access Control."""

    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMINISTRATOR = "administrator"


class User(BaseModel):
    username: str
    full_name: str
    role: Role


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=64)


class ChatEvent(BaseModel):
    """One streamed event pushed to the client (SSE)."""

    type: str  # agent_state | node | tool_call | retrieval | memory | validation | final | error
    payload: dict[str, Any]
    timestamp: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    llm_available: bool
    pinecone_available: bool
    langsmith_available: bool
    index_size: int
