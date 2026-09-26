"""Application configuration loaded from environment / .env file.

All credentials and tunable thresholds live here so the rest of the code
never touches ``os.environ`` directly.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Central settings object."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- General ----
    app_name: str = "Enterprise AI Assistant"
    environment: str = "dev"
    log_level: str = "INFO"

    # ---- LLM ----
    llm_provider: str = "openai"  # "openai" | "mock"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    llm_temperature: float = 0.0

    # ---- Pinecone ----
    use_pinecone: bool = False
    pinecone_api_key: str | None = None
    pinecone_index_name: str = "enterprise-assistant"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # ---- LangSmith ----
    langsmith_api_key: str | None = None
    langsmith_project: str = "enterprise-ai-assistant"
    langsmith_tracing_v2: bool = True

    # ---- Auth ----
    auth_secret: str = "change-me-to-a-long-random-string"
    token_expiry_minutes: int = 60

    # ---- Rate limiting (token bucket) ----
    rate_limit_enabled: bool = True
    rate_limit_capacity: int = 30
    rate_limit_refill_per_second: float = 1.0

    # ---- Retrieval ----
    top_k: int = 8
    chunk_size: int = 800
    chunk_overlap: int = 100
    hybrid_dense_weight: float = 0.5
    rrf_k: int = 60

    # ---- Tools ----
    tool_timeout_seconds: float = 15.0

    # ---- Paths ----
    data_dir: str = str(PROJECT_ROOT / "data")
    documents_dir: str = str(PROJECT_ROOT / "data" / "documents")
    local_index_path: str = str(PROJECT_ROOT / "data" / "local_index.json")

    @property
    def llm_available(self) -> bool:
        """A real LLM is only available when an API key is present."""
        return bool(self.openai_api_key)

    @property
    def pinecone_available(self) -> bool:
        return self.use_pinecone and bool(self.pinecone_api_key)

    @property
    def langsmith_available(self) -> bool:
        return bool(self.langsmith_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
