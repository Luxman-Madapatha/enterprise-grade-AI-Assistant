"""Document loading and chunking.

Sample documents use a small markdown frontmatter block for metadata:

    ---
    department: payments
    document_type: incident
    access_level: internal
    created_date: 2025-01-01
    title: Payment gateway outage
    ---
    # body ...
"""
from __future__ import annotations

import re
from pathlib import Path

from app.config import settings
from app.logging_config import get_logger
from app.retrieval.vector_store import DocumentChunk

logger = get_logger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<body>.*?)\n---\s*\n?", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (metadata, body) parsed from an optional frontmatter block."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text.strip()
    metadata: dict[str, str] = {}
    for line in match.group("body").splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, text[match.end():].strip()


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap

    # Split on sentence-ish boundaries first.
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " ").strip())
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= chunk_size:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            # Keep overlap from the tail of the previous chunk.
            words = current.split()
            tail = " ".join(words[-max(1, overlap // 6):]) if current else ""
            current = (tail + " " + sentence).strip() if tail else sentence
    if current:
        chunks.append(current)
    return chunks


def load_documents(directory: str | None = None) -> list[DocumentChunk]:
    directory = directory or settings.documents_dir
    root = Path(directory)
    if not root.exists():
        logger.warning("documents_dir_missing", directory=str(root))
        return []

    chunks: list[DocumentChunk] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("document_read_failed", path=str(path), error=str(exc))
            continue

        metadata, body = parse_frontmatter(raw)
        metadata.setdefault("source_file", path.name)
        metadata.setdefault("department", "general")
        metadata.setdefault("document_type", "unknown")
        metadata.setdefault("access_level", "internal")

        for i, chunk in enumerate(chunk_text(body)):
            chunk_id = f"{path.stem}-{i}"
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    text=chunk,
                    metadata={**metadata, "chunk_index": i},
                )
            )
    logger.info("documents_loaded", files=len(chunks), chunks=len(chunks))
    return chunks
