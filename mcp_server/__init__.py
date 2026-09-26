"""Simple Model Context Protocol (MCP) server exposing dummy enterprise data.

This is a minimal, dependency-free implementation of the MCP stdio transport
(newline-delimited JSON-RPC 2.0) implementing ``tools/list`` and ``tools/call``.
It demonstrates the MCP integration pattern without pulling the full SDK;
a production deployment would swap in the official ``mcp`` SDK server.
"""
