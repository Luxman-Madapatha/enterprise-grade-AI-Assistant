"""Embedding abstraction.

Two implementations:

* ``OpenAIEmbeddingModel`` — real embeddings when ``OPENAI_API_KEY`` is set.
* ``LocalHashingEmbeddings`` — deterministic hashing vectorizer so the whole
  stack runs with zero external credentials (used for the POC/demo).
"""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class EmbeddingModel(ABC):
    """Contract for a dense embedding provider."""

    name: str = "embedding"
    dim: int = 512

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts (async)."""

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]


class LocalHashingEmbeddings(EmbeddingModel):
    """Hashing-based bag-of-(word+bigram) vectors. Deterministic & offline.

    Not semantically as rich as a transformer model, but perfectly adequate to
    demonstrate the full dense+sparse hybrid pipeline locally.
    """

    name = "local-hashing"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    @staticmethod
    def _tokens(text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        bigrams = [
            f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)
        ]
        return tokens + bigrams

    def vectorize(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.vectorize(t) for t in texts]


class OpenAIEmbeddingModel(EmbeddingModel):
    name = "openai"

    def __init__(self) -> None:
        from langchain_openai import OpenAIEmbeddings

        self._embeddings = OpenAIEmbeddings(model=settings.embedding_model)
        # text-embedding-3-small -> 1536, ada-002 -> 1536. We read dim lazily.
        self.dim = 1536

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return await self._embeddings.aembed_documents(texts)


_embedding_model: EmbeddingModel | None = None


def get_embedding_model() -> EmbeddingModel:
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    if settings.llm_available:
        try:
            _embedding_model = OpenAIEmbeddingModel()
            logger.info("embedding_model", name=_embedding_model.name)
            return _embedding_model
        except Exception as exc:  # pragma: no cover - depends on env
            logger.warning("openai_embedding_init_failed", error=str(exc))
    _embedding_model = LocalHashingEmbeddings()
    logger.info("embedding_model", name=_embedding_model.name)
    return _embedding_model
