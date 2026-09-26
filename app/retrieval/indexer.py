"""Document indexing pipeline.

Chunks documents -> embeds them -> upserts into the configured vector store.
Called at startup (lazily, when the index is empty) and by the admin reindex
endpoint.
"""
from __future__ import annotations

import asyncio

from app.logging_config import get_logger
from app.retrieval.document_loader import load_documents
from app.retrieval.embeddings import get_embedding_model
from app.retrieval.vector_store import get_vector_store

logger = get_logger(__name__)

_indexing_lock = asyncio.Lock()


async def index_documents(directory: str | None = None) -> int:
    """Index all documents in ``directory`` (default: configured docs dir)."""
    async with _indexing_lock:
        chunks = load_documents(directory)
        if not chunks:
            logger.warning("no_documents_to_index")
            return 0

        embeddings = get_embedding_model()
        vectors = await embeddings.embed_texts([c.text for c in chunks])

        store = get_vector_store()
        await store.upsert(chunks, vectors, namespace="default")
        logger.info("indexed_documents", chunks=len(chunks), backend=type(store).__name__)
        return len(chunks)


async def ensure_indexed() -> None:
    """Index sample documents on first boot if the store is empty."""
    store = get_vector_store()
    if store.count() == 0:
        count = await index_documents()
        logger.info("auto_index_complete", chunks=count)
    else:
        logger.info("index_already_populated", chunks=store.count())
