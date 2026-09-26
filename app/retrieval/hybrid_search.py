"""Hybrid search: dense + sparse retrieval fused with Reciprocal Rank Fusion.

RRF is simple, robust to score-scale differences, and requires no training.
Both legs run concurrently via ``asyncio.gather`` so retrieval latency is
bounded by the slowest leg, not their sum.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.config import settings
from app.logging_config import get_logger
from app.retrieval.embeddings import get_embedding_model
from app.retrieval.vector_store import SearchResult, get_vector_store

logger = get_logger(__name__)


def reciprocal_rank_fusion(
    dense: list[SearchResult],
    sparse: list[SearchResult],
    k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> list[SearchResult]:
    scores: dict[str, float] = {}
    meta: dict[str, SearchResult] = {}

    for rank, res in enumerate(dense):
        scores[res.chunk_id] = scores.get(res.chunk_id, 0.0) + dense_weight / (k + rank + 1)
        meta[res.chunk_id] = res
    for rank, res in enumerate(sparse):
        scores[res.chunk_id] = scores.get(res.chunk_id, 0.0) + sparse_weight / (k + rank + 1)
        meta.setdefault(res.chunk_id, res)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    fused: list[SearchResult] = []
    for chunk_id, score in ranked:
        res = meta[chunk_id]
        fused.append(
            SearchResult(
                chunk_id=chunk_id,
                text=res.text,
                metadata=res.metadata,
                score=score,
                source="hybrid",
            )
        )
    return fused


class HybridSearchEngine:
    def __init__(self) -> None:
        self.store = get_vector_store()
        self.embeddings = get_embedding_model()

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        flt: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> list[SearchResult]:
        top_k = top_k or settings.top_k
        query_vector = await self.embeddings.embed_query(query)

        dense, sparse = await asyncio.gather(
            self.store.dense_search(query_vector, top_k * 2, flt, namespace),
            self.store.sparse_search(query, top_k * 2, flt, namespace),
            return_exceptions=True,
        )
        if isinstance(dense, Exception):
            logger.warning("dense_search_failed", error=str(dense))
            dense = []
        if isinstance(sparse, Exception):
            logger.warning("sparse_search_failed", error=str(sparse))
            sparse = []

        fused = reciprocal_rank_fusion(
            dense,
            sparse,
            k=settings.rrf_k,
            dense_weight=settings.hybrid_dense_weight,
            sparse_weight=1.0 - settings.hybrid_dense_weight,
        )
        logger.info(
            "hybrid_search",
            query=query[:80],
            dense_hits=len(dense),
            sparse_hits=len(sparse),
            fused_hits=len(fused[:top_k]),
        )
        return fused[:top_k]


hybrid_search = HybridSearchEngine()
