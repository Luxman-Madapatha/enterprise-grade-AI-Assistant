"""MCP client — speaks the minimal MCP stdio protocol to ``mcp_server/server.py``.

The server runs as a child process; the client multiplexes JSON-RPC requests
over its stdin/stdout. Because the agent never touches the filesystem or the
network directly here, MCP failures are contained and reported gracefully.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.auth.rbac import TOOL_MCP_EMPLOYEE, TOOL_MCP_INCIDENT, TOOL_MCP_SERVICE
from app.config import PROJECT_ROOT, settings
from app.logging_config import get_logger
from app.tools.base import BaseTool

logger = get_logger(__name__)

SERVER_PATH = PROJECT_ROOT / "mcp_server" / "server.py"


class MCPClient:
    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}

    async def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return
        async with self._lock:
            if self._proc is not None and self._proc.returncode is None:
                return
            self._proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(SERVER_PATH),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._reader_task = asyncio.create_task(self._reader())
            logger.info("mcp_server_started", pid=self._proc.pid)

    async def _reader(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            fut = self._pending.pop(msg.get("id"), None)
            if fut and not fut.done():
                fut.set_result(msg)

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        await self._ensure_started()
        assert self._proc is not None and self._proc.stdin is not None

        self._next_id += 1
        req_id = self._next_id
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        self._proc.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

        try:
            resp = await asyncio.wait_for(fut, timeout=settings.tool_timeout_seconds)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError("MCP server did not respond in time")
        if "error" in resp:
            raise RuntimeError(resp["error"].get("message", "MCP error"))
        content = resp.get("result", {}).get("content", [])
        text = "".join(
            c.get("text", "") for c in content if c.get("type") == "text"
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    async def close(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            await self._proc.wait()
        self._proc = None


_mcp_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


class _MCPBaseTool(BaseTool):
    mcp_tool_name: str = ""

    async def execute(self, params: dict[str, Any]) -> Any:
        return await get_mcp_client().call(self.mcp_tool_name, params)


class EmployeeDirectoryTool(_MCPBaseTool):
    name = TOOL_MCP_EMPLOYEE
    mcp_tool_name = "employee_directory"
    description = "Search the employee directory via MCP."


class ServiceCatalogTool(_MCPBaseTool):
    name = TOOL_MCP_SERVICE
    mcp_tool_name = "service_catalog"
    description = "Search the internal service catalog via MCP."


class IncidentRecordsTool(_MCPBaseTool):
    name = TOOL_MCP_INCIDENT
    mcp_tool_name = "incident_records"
    description = "Search incident records via MCP."
