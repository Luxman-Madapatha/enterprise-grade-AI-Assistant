"""Vector-store abstraction.

Two backends share one interface:

* ``LocalVectorStore`` — in-memory numpy dense index + BM25 sparse index with
  namespace partitions and metadata filtering. Persists to JSON. Used when
  Pinecone credentials are absent so the POC runs anywhere.
* ``PineconeVectorStore`` — managed dense index (namespaces, metadata filters).
  Sparse ranking is performed by a locally-maintained BM25 mirror built from
  the same documents, then fused with Pinecone dense scores via RRF.
"""
from __future__ import annotations

import asyncio
import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class DocumentChunk:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "metadata": self.metadata}


@dataclass
class SearchResult:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    score: float
    source: str  # "dense" | "sparse" | "hybrid"

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "metadata": self.metadata,
            "score": round(self.score, 5),
            "source": self.source,
        }


def _matches_filter(metadata: dict[str, Any], flt: dict[str, Any] | None) -> bool:
    if not flt:
        return True
    for key, value in flt.items():
        if isinstance(value, dict):  # simple $in support
            if metadata.get(key) not in value.get("$in", []):
                return False
        elif metadata.get(key) != value:
            return False
    return True


class VectorStore(ABC):
    @abstractmethod
    async def upsert(
        self,
        chunks: list[DocumentChunk],
        vectors: list[list[float]] | None = None,
        namespace: str = "default",
    ) -> None:
        ...

    @abstractmethod
    async def dense_search(
        self,
        query_vector: list[float],
        top_k: int,
        flt: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> list[SearchResult]:
        ...

    @abstractmethod
    async def sparse_search(
        self,
        query_text: str,
        top_k: int,
        flt: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> list[SearchResult]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...

    @abstractmethod
    async def clear(self) -> None:
        ...


# --------------------------------------------------------------------------- #
# Local backend
# --------------------------------------------------------------------------- #
class _Partition:
    def __init__(self) -> None:
        self.chunks: list[DocumentChunk] = []
        self.matrix: np.ndarray | None = None
        self.bm25: BM25Okapi | None = None

    def tokenized(self) -> list[list[str]]:
        import re

        return [re.findall(r"[a-z0-9]+", c.text.lower()) for c in self.chunks]

    def rebuild_sparse(self) -> None:
        if self.chunks:
            self.bm25 = BM25Okapi(self.tokenized())
        else:
            self.bm25 = None


class LocalVectorStore(VectorStore):
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or settings.local_index_path)
        self._partitions: dict[str, _Partition] = {}
        self._lock = threading.Lock()
        self._load()

    # -- persistence -------------------------------------------------------- #
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("local_index_load_failed", error=str(exc))
            return
        for ns, payload in data.get("namespaces", {}).items():
            part = _Partition()
            for row in payload["chunks"]:
                part.chunks.append(
                    DocumentChunk(id=row["id"], text=row["text"], metadata=row["metadata"])
                )
            vectors = payload.get("vectors")
            if vectors:
                part.matrix = np.asarray(vectors, dtype=np.float32)
            part.rebuild_sparse()
            self._partitions[ns] = part
        logger.info("local_index_loaded", namespaces=list(self._partitions.keys()))

    def save(self) -> None:
        data: dict[str, Any] = {"namespaces": {}}
        for ns, part in self._partitions.items():
            data["namespaces"][ns] = {
                "chunks": [c.as_dict() for c in part.chunks],
                "vectors": part.matrix.tolist() if part.matrix is not None else [],
            }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data), encoding="utf-8")

    # -- interface ---------------------------------------------------------- #
    def _partition(self, namespace: str, create: bool = False) -> _Partition:
        with self._lock:
            if namespace not in self._partitions:
                if create:
                    self._partitions[namespace] = _Partition()
                else:
                    return _Partition()
            return self._partitions[namespace]

    async def upsert(
        self,
        chunks: list[DocumentChunk],
        vectors: list[list[float]] | None = None,
        namespace: str = "default",
    ) -> None:
        await asyncio.to_thread(self._upsert_sync, chunks, vectors, namespace)

    def _upsert_sync(
        self,
        chunks: list[DocumentChunk],
        vectors: list[list[float]] | None,
        namespace: str,
    ) -> None:
        part = self._partition(namespace, create=True)
        existing = {c.id for c in part.chunks}
        vec_list = vectors if vectors is not None else [None] * len(chunks)
        new_items = [
            (c, v) for c, v in zip(chunks, vec_list) if c.id not in existing
        ]
        if not new_items:
            return
        for c, v in new_items:
            part.chunks.append(c)
            if v is not None:
                row = np.asarray([v], dtype=np.float32)
                if part.matrix is None:
                    part.matrix = row
                else:
                    part.matrix = np.vstack([part.matrix, row])
        part.rebuild_sparse()
        self.save()

    def _dense_sync(
        self, query_vector: list[float], top_k: int, flt: dict | None, namespace: str
    ) -> list[SearchResult]:
        part = self._partition(namespace)
        if part.matrix is None or not part.chunks:
            return []
        q = np.asarray(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
        scores = part.matrix @ q / (np.linalg.norm(part.matrix, axis=1) + 1e-9)
        results: list[SearchResult] = []
        for i in np.argsort(-scores):
            if _matches_filter(part.chunks[i].metadata, flt):
                results.append(
                    SearchResult(
                        chunk_id=part.chunks[i].id,
                        text=part.chunks[i].text,
                        metadata=part.chunks[i].metadata,
                        score=float(scores[i]),
                        source="dense",
                    )
                )
            if len(results) >= top_k:
                break
        return results

    def _sparse_sync(
        self, query_text: str, top_k: int, flt: dict | None, namespace: str
    ) -> list[SearchResult]:
        import re

        part = self._partition(namespace)
        if part.bm25 is None or not part.chunks:
            return []
        query_tokens = re.findall(r"[a-z0-9]+", query_text.lower())
        if not query_tokens:
            return []
        scores = part.bm25.get_scores(query_tokens)
        results: list[SearchResult] = []
        for i in np.argsort(-np.asarray(scores)):
            if _matches_filter(part.chunks[i].metadata, flt):
                results.append(
                    SearchResult(
                        chunk_id=part.chunks[i].id,
                        text=part.chunks[i].text,
                        metadata=part.chunks[i].metadata,
                        score=float(scores[i]),
                        source="sparse",
                    )
                )
            if len(results) >= top_k:
                break
        return results

    async def dense_search(self, query_vector, top_k, flt=None, namespace="default"):
        return await asyncio.to_thread(self._dense_sync, query_vector, top_k, flt, namespace)

    async def sparse_search(self, query_text, top_k, flt=None, namespace="default"):
        return await asyncio.to_thread(self._sparse_sync, query_text, top_k, flt, namespace)

    def count(self) -> int:
        with self._lock:
            return sum(len(p.chunks) for p in self._partitions.values())

    async def clear(self) -> None:
        with self._lock:
            self._partitions.clear()
        if self.path.exists():
            self.path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Pinecone backend
# --------------------------------------------------------------------------- #
class PineconeVectorStore(VectorStore):
    def __init__(self) -> None:
        from pinecone import Pinecone

        self._pc = Pinecone(api_key=settings.pinecone_api_key)
        self._index = self._pc.Index(settings.pinecone_index_name)
        # Local BM25 mirror for the sparse leg of hybrid search.
        self._bm25: dict[str, BM25Okapi] = {}
        self._bm25_chunks: dict[str, dict[str, str]] = {}
        self._total = 0

    async def _embed_chunk(self, text: str) -> list[float]:
        from app.retrieval.embeddings import get_embedding_model

        return (await get_embedding_model().embed_texts([text]))[0]

    async def upsert(
        self,
        chunks: list[DocumentChunk],
        vectors: list[list[float]] | None = None,
        namespace: str = "default",
    ) -> None:
        if vectors is None:
            vectors = [await self._embed_chunk(c.text) for c in chunks]
        records = [
            {"id": c.id, "values": v, "metadata": c.metadata}
            for c, v in zip(chunks, vectors)
        ]
        await asyncio.to_thread(
            self._index.upsert, vectors=records, namespace=namespace
        )
        self._rebuild_bm25_mirror(chunks, namespace)
        self._total += len(chunks)

    def _rebuild_bm25_mirror(
        self, chunks: list[DocumentChunk], namespace: str
    ) -> None:
        import re

        texts = self._bm25_chunks.setdefault(namespace, {})
        for c in chunks:
            texts[c.id] = c.text
        corpus = [re.findall(r"[a-z0-9]+", t.lower()) for t in texts.values()]
        if corpus:
            self._bm25[namespace] = BM25Okapi(corpus)

    async def dense_search(self, query_vector, top_k, flt=None, namespace="default"):
        def _query():
            return self._index.query(
                vector=query_vector,
                top_k=top_k,
                filter=flt or {},
                namespace=namespace,
                include_metadata=True,
            )

        resp = await asyncio.to_thread(_query)
        return [
            SearchResult(
                chunk_id=m["id"],
                text="",
                metadata=m.get("metadata", {}),
                score=float(m.get("score", 0.0)),
                source="dense",
            )
            for m in resp.get("matches", [])
        ]

    async def sparse_search(self, query_text, top_k, flt=None, namespace="default"):
        import re

        bm25 = self._bm25.get(namespace)
        texts = self._bm25_chunks.get(namespace, {})
        if bm25 is None or not texts:
            return []
        query_tokens = re.findall(r"[a-z0-9]+", query_text.lower())
        if not query_tokens:
            return []
        scores = bm25.get_scores(query_tokens)
        ids = list(texts.keys())
        results: list[SearchResult] = []
        for i in np.argsort(-np.asarray(scores)):
            if len(results) >= top_k:
                break
            chunk_id = ids[i]
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    text=texts[chunk_id],
                    metadata={},
                    score=float(scores[i]),
                    source="sparse",
                )
            )
        return results

    def count(self) -> int:
        return self._total

    async def clear(self) -> None:
        await asyncio.to_thread(self._index.delete, delete_all=True, namespace="default")
        self._total = 0
        self._bm25.clear()
        self._bm25_chunks.clear()


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is not None:
        return _vector_store
    if settings.pinecone_available:
        try:
            _vector_store = PineconeVectorStore()
            logger.info("vector_store", backend="pinecone")
            return _vector_store
        except Exception as exc:  # pragma: no cover - depends on env
            logger.warning("pinecone_init_failed_falling_back", error=str(exc))
    _vector_store = LocalVectorStore()
    logger.info("vector_store", backend="local")
    return _vector_store
