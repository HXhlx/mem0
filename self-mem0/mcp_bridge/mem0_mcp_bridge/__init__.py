"""mem0-mcp-bridge — stdio MCP server forwarding to a self-hosted Mem0 REST API."""

from __future__ import annotations

__all__ = ["main"]


def main() -> None:
    from .__main__ import main as _main

    _main()
