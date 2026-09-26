"""End-to-end smoke test (no server needed).

Runs the full agent pipeline offline (mock LLM, local index) and prints the
final answer. Useful to validate the wiring before starting the servers.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.graph import run_assistant
from app.logging_config import configure_logging
from app.retrieval.indexer import index_documents


async def main() -> None:
    configure_logging()
    await index_documents()

    queries = [
        "What is the payment failure response runbook?",
        "Summarize all outage reports related to payment failures in the last year and identify recurring root causes.",
        "Who works in the payments department?",
        "Hello!",
    ]
    for q in queries:
        print("\n" + "=" * 80)
        print("Q:", q)
        final = await run_assistant(
            {"username": "admin", "role": "administrator"}, "smoke-session", q
        )
        print("INTENT:", final.get("intent"), "ROUTE:", final.get("route"))
        print("CITATIONS:", final.get("citations"))
        print("ANSWER:\n", final.get("final_answer", ""))

    from app.tools.mcp_client import get_mcp_client

    await get_mcp_client().close()


if __name__ == "__main__":
    asyncio.run(main())
