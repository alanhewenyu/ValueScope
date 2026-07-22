# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Stdio entrypoint for the ValueScope MCP server.

Production serves streamable HTTP (mounted at /mcp in backend.main); this
wrapper exposes the same FastMCP instance over stdio for clients and
registries that run MCP servers as subprocesses (e.g. Glama's build test,
`mcp-proxy -- python -m backend.mcp_stdio`, or local Claude Desktop use
without the HTTP endpoint).
"""

from backend.mcp_server import mcp

if __name__ == "__main__":
    mcp.run()  # stdio transport
