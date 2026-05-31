# mem0-mcp-bridge

A tiny stdio MCP server that exposes the same tools as the hosted
`mcp.mem0.ai` endpoint, but forwards every call to a self-hosted Mem0
REST API (default `http://localhost:8888`).

Use this to plug `mem0-plugin` (Claude Code / OpenCode) into a self-hosted
Mem0 server without modifying the plugin's MCP transport.

## Quick start

```bash
# 1. From this repo
pip install -e server/mcp_bridge

# 2. Register with Claude Code
claude mcp add --scope user --transport stdio mem0 \
  --env MEM0_API_KEY=$ADMIN_API_KEY \
  --env MEM0_HOST=http://localhost:8888 \
  -- mem0-mcp-bridge

# 3. Or via .mcp.json
{
  "mcpServers": {
    "mem0": {
      "command": "mem0-mcp-bridge",
      "env": {
        "MEM0_API_KEY": "${MEM0_API_KEY}",
        "MEM0_HOST": "http://localhost:8888"
      }
    }
  }
}
```

## Tools exposed

| Tool | REST endpoint |
|---|---|
| `add_memory` | `POST /v3/memories/add/` |
| `search_memories` | `POST /v3/memories/search/` |
| `get_memories` | `POST /v3/memories/` |
| `get_memory` | `GET /v1/memories/{id}/` |
| `update_memory` | `PUT /v1/memories/{id}/` |
| `delete_memory` | `DELETE /v1/memories/{id}/` |
| `delete_all_memories` | `DELETE /v1/memories/` |
| `list_entities` | `GET /v1/entities/` |
| `delete_entities` | `DELETE /v2/entities/{type}/{name}/` |

Authentication: `Authorization: Token <MEM0_API_KEY>` on every request.
