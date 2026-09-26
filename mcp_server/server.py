"""Minimal MCP server over stdio (newline-delimited JSON-RPC 2.0).

Run it directly: ``python mcp_server/server.py``
Implements:
* ``tools/list``  — enumerate available tools
* ``tools/call``  — invoke a tool by name with JSON arguments
"""
from __future__ import annotations

import json
import re
import sys

# --------------------------------------------------------------------------- #
# Dummy enterprise data (not a priority requirement — illustrative only).
# --------------------------------------------------------------------------- #
EMPLOYEES = [
    {"id": "E1001", "name": "Alice Johnson", "department": "payments", "title": "Payments Engineer"},
    {"id": "E1002", "name": "Bob Martinez", "department": "payments", "title": "SRE Lead"},
    {"id": "E1003", "name": "Carol Ng", "department": "infrastructure", "title": "Platform Architect"},
    {"id": "E1004", "name": "David Osei", "department": "security", "title": "Security Engineer"},
    {"id": "E1005", "name": "Elena Petrova", "department": "compliance", "title": "Risk Analyst"},
]

SERVICES = [
    {"id": "svc-payments", "name": "Payments API", "owner": "payments", "status": "operational", "sla": "99.99%"},
    {"id": "svc-cards", "name": "Card Issuing", "owner": "payments", "status": "degraded", "sla": "99.9%"},
    {"id": "svc-iam", "name": "Identity & Access", "owner": "security", "status": "operational", "sla": "99.95%"},
    {"id": "svc-ledger", "name": "Core Ledger", "owner": "infrastructure", "status": "operational", "sla": "99.99%"},
]

INCIDENTS = [
    {"id": "INC-101", "title": "Payment gateway timeout", "severity": "sev1", "status": "resolved", "service": "svc-payments", "date": "2025-01-15"},
    {"id": "INC-102", "title": "Card authorization latency spike", "severity": "sev2", "status": "resolved", "service": "svc-cards", "date": "2025-02-03"},
    {"id": "INC-103", "title": "Ledger reconciliation delay", "severity": "sev2", "status": "open", "service": "svc-ledger", "date": "2025-03-11"},
    {"id": "INC-104", "title": "Payments webhook delivery failures", "severity": "sev1", "status": "resolved", "service": "svc-payments", "date": "2025-04-22"},
]

TOOLS = {
    "employee_directory": {
        "description": "Search the employee directory by name or department.",
        "handler": lambda args: _search(EMPLOYEES, args.get("query", ""), ["name", "department"]),
    },
    "service_catalog": {
        "description": "Search the internal service catalog.",
        "handler": lambda args: _search(SERVICES, args.get("query", ""), ["name", "owner", "id"]),
    },
    "incident_records": {
        "description": "Search incident records, optionally filtered by severity.",
        "handler": lambda args: _incidents(args),
    },
}


def _search(rows: list[dict], query: str, fields: list[str]) -> list[dict]:
    """Token-based search: match any meaningful query token against fields."""
    tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    if not tokens:
        return rows

    def matches(row: dict) -> bool:
        haystack = " ".join(str(row.get(f, "")).lower() for f in fields)
        return any(token in haystack for token in tokens)

    return [row for row in rows if matches(row)]


def _incidents(args: dict) -> list[dict]:
    rows = _search(INCIDENTS, args.get("query", ""), ["title", "service", "id"])
    severity = args.get("severity")
    if severity:
        rows = [r for r in rows if r["severity"] == severity]
    return rows


def _list_tools() -> dict:
    return {
        "tools": [
            {"name": name, "description": spec["description"]}
            for name, spec in TOOLS.items()
        ]
    }


def handle_request(req: dict) -> dict | None:
    """Handle a single JSON-RPC request. Returns None for notifications."""
    req_id = req.get("id")
    method = req.get("method")

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": _list_tools()}

    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        spec = TOOLS.get(name)
        if spec is None:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32602, "message": f"Unknown tool: {name}"},
            }
        result = spec["handler"](arguments or {})
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result)}]},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve() -> None:
    """Read JSON-RPC requests from stdin and write responses to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve()
