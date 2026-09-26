"""Re-index documents from the command line.

Usage: python scripts/index_documents.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.logging_config import configure_logging
from app.retrieval.indexer import index_documents


async def main() -> None:
    configure_logging()
    count = await index_documents()
    print(f"Indexed {count} chunks.")


if __name__ == "__main__":
    asyncio.run(main())
