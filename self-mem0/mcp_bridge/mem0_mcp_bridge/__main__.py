"""Entry point: stdio MCP server bridging to a self-hosted Mem0 REST API."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

log = logging.getLogger("mem0-mcp-bridge")


# ---------------------------------------------------------------------------
# Configuration — env vars only, no .env file parsing here
# ---------------------------------------------------------------------------

DEFAULT_HOST = "https://api.mem0.ai"
REQUEST_TIMEOUT = 30.0


def _host() -> str:
    return (os.environ.get("MEM0_HOST") or DEFAULT_HOST).rstrip("/")


def _api_key() -> str:
    key = os.environ.get("MEM0_API_KEY", "").strip()
    if not key:
        raise RuntimeError("MEM0_API_KEY is required")
    return key


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Token {_api_key()}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Tool descriptions — schema mirrors hosted mcp.mem0.ai
# ---------------------------------------------------------------------------

_IDENTIFIER_FIELDS = {
    "user_id": {"type": "string", "description": "User namespace; required for most calls."},
    "agent_id": {"type": "string", "description": "Agent namespace (optional)."},
    "run_id": {"type": "string", "description": "Run/session namespace (optional)."},
    "app_id": {"type": "string", "description": "Application/project namespace (stored as metadata)."},
}


def _tools() -> list[Tool]:
    return [
        Tool(
            name="add_memory",
            description="Store one or more messages as a memory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["role", "content"],
                        },
                    },
                    **_IDENTIFIER_FIELDS,
                    "metadata": {"type": "object"},
                    "infer": {"type": "boolean"},
                },
                "required": ["messages"],
            },
        ),
        Tool(
            name="search_memories",
            description="Search memories by semantic query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "filters": {"type": "object"},
                    "top_k": {"type": "integer", "default": 10},
                    "threshold": {"type": "number"},
                    "rerank": {"type": "boolean",
                               "description": "Re-rank vector hits with the configured cross-encoder (DashScope qwen3-rerank by default)."},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_memories",
            description="List memories matching optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filters": {"type": "object"},
                    "page": {"type": "integer"},
                    "page_size": {"type": "integer"},
                },
            },
        ),
        Tool(
            name="get_memory",
            description="Fetch a single memory by ID.",
            inputSchema={
                "type": "object",
                "properties": {"memory_id": {"type": "string"}},
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="update_memory",
            description="Update a memory's text and/or metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "text": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="delete_memory",
            description="Delete a single memory by ID.",
            inputSchema={
                "type": "object",
                "properties": {"memory_id": {"type": "string"}},
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="delete_all_memories",
            description="Delete every memory in the given namespace.",
            inputSchema={
                "type": "object",
                "properties": _IDENTIFIER_FIELDS,
            },
        ),
        Tool(
            name="list_entities",
            description="List entities (users / agents / runs) extracted from memories.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="delete_entities",
            description="Delete an entity and all of its memories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string"},
                    "entity_name": {"type": "string"},
                },
                "required": ["entity_type", "entity_name"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


async def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    url = f"{_host()}{path}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.request(
            method,
            url,
            headers=_auth_headers(),
            json=json_body,
            params=params,
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {path} → HTTP {resp.status_code}: {resp.text[:300]}")
    if not resp.content:
        return {"ok": True}
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


# ---------------------------------------------------------------------------
# Tool dispatchers
# ---------------------------------------------------------------------------


def _strip_none(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


async def _dispatch(name: str, args: Dict[str, Any]) -> Any:
    a = args or {}
    if name == "add_memory":
        body = _strip_none(
            {
                "messages": a.get("messages") or [],
                "user_id": a.get("user_id"),
                "agent_id": a.get("agent_id"),
                "run_id": a.get("run_id"),
                "app_id": a.get("app_id"),
                "metadata": a.get("metadata"),
                "infer": a.get("infer"),
            }
        )
        return await _request("POST", "/v3/memories/add/", json_body=body)

    if name == "search_memories":
        body = _strip_none(
            {
                "query": a.get("query") or "",
                "filters": a.get("filters"),
                "top_k": a.get("top_k"),
                "threshold": a.get("threshold"),
                "rerank": a.get("rerank"),
            }
        )
        return await _request("POST", "/v3/memories/search/", json_body=body)

    if name == "get_memories":
        body = _strip_none(
            {
                "filters": a.get("filters"),
                "page": a.get("page"),
                "page_size": a.get("page_size"),
            }
        )
        return await _request("POST", "/v3/memories/", json_body=body or {})

    if name == "get_memory":
        return await _request("GET", f"/v1/memories/{a['memory_id']}/")

    if name == "update_memory":
        body = _strip_none({"text": a.get("text"), "metadata": a.get("metadata")})
        return await _request("PUT", f"/v1/memories/{a['memory_id']}/", json_body=body)

    if name == "delete_memory":
        return await _request("DELETE", f"/v1/memories/{a['memory_id']}/")

    if name == "delete_all_memories":
        params = _strip_none(
            {
                "user_id": a.get("user_id"),
                "agent_id": a.get("agent_id"),
                "run_id": a.get("run_id"),
            }
        )
        return await _request("DELETE", "/v1/memories/", params=params)

    if name == "list_entities":
        return await _request("GET", "/v1/entities/")

    if name == "delete_entities":
        return await _request(
            "DELETE",
            f"/v2/entities/{a['entity_type']}/{a['entity_name']}/",
        )

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Server wiring
# ---------------------------------------------------------------------------

server = Server("mem0-mcp-bridge")


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return _tools()


@server.call_tool()
async def _call_tool(name: str, arguments: Dict[str, Any]) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as exc:
        log.exception("Tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]


async def _amain() -> None:
    logging.basicConfig(level=os.environ.get("MEM0_MCP_LOG_LEVEL", "INFO"), stream=sys.stderr)
    log.info("mem0-mcp-bridge → %s", _host())
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    import asyncio

    asyncio.run(_amain())


if __name__ == "__main__":
    main()
