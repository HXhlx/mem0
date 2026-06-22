# self-mem0 — minimal self-hosted adapter for mem0

A non-invasive layer that lets `mem0/server/` (FastAPI + pgvector) serve the
**mem0 SDK** (`MemoryClient`), the **mem0-plugin** (Claude Code / OpenCode),
**OpenClaw**, and **Hermes** without modifying their code.

> Total cost on the mem0 tree: **12 lines** spread across `server/main.py`
> (6) and `server/auth.py` (6) — all wrapped in `try/except ImportError` so
> the server runs unchanged when this directory isn't on `PYTHONPATH`.
> Everything else lives here and is invisible to `git pull`.

## Layout

```
self-mem0/
├── apply.sh                    one-shot enable (docker override + mem0-mcp + plugin patch)
├── revert.sh                   undo the above
├── self_mem0/                  Python package — wired in by main.py / auth.py hooks
│   └── server/
│       ├── bootstrap.py        public API: patch_config(...), attach_routes(app)
│       ├── default_config_overrides.py   env-driven LLM/embedder/dims overrides
│       ├── sdk_compat.py       /v3/memories/* + /v1/memories/* routes for MemoryClient
│       ├── ping_route.py       /v1/ping/ stub (satisfies older SDK Project validator)
│       └── auth_token_scheme.py  Authorization: Token <key> parser
├── plugins/
│   ├── patch_mem0_plugin.sh    inject MEM0_HOST into the user-level Claude Code plugin
│   └── redirect_mcp.sh         point the plugin's MCP config at the local SSE server
└── docs/
    └── self-hosted-agents.mdx  full integration guide
```

The MCP server itself lives in the sibling `../mem0-mcp/` package — a
self-hosted fork of the archived `mem0ai/mem0-mcp`. It uses
`MemoryClient(host=$MEM0_HOST)` to talk to this REST surface, so the
`sdk_compat` router above is what makes it work unchanged against the
self-hosted server.

## What the hooks look like

`server/main.py` — 6 lines, all conditional:

```python
try:                                                              # +3
    from self_mem0.server import bootstrap as _self_mem0          #
except ImportError:                                               #
    _self_mem0 = None                                             #
# ...
if _self_mem0: _self_mem0.patch_config(DEFAULT_CONFIG)            # +2
# ...
if _self_mem0: _self_mem0.attach_routes(app)                      # +1
```

`server/auth.py` — 6 lines inside `verify_auth`, all conditional:

```python
try:                                                              # +6
    from self_mem0.server.auth_token_scheme import MISS, try_token_auth
    _result = try_token_auth(request, db)
    if _result is not MISS:
        return _result
except ImportError:
    pass
```

These hooks are no-ops without `self-mem0/` on `PYTHONPATH`, so upstream
`git pull` keeps working even if the surrounding lines change.

## Quick start

```bash
# 1. Enable everything (idempotent)
./self-mem0/apply.sh

# 2. Restart the server with the override compose file
cd server
docker compose -f docker-compose.yaml -f docker-compose.override.yaml up -d

# 3. Add to your shell profile
export MEM0_HOST="http://localhost:8888"
export MEM0_API_KEY="<ADMIN_API_KEY from server/.env>"

# 4. Verify
curl -s "$MEM0_HOST/v1/ping/" -H "Authorization: Token $MEM0_API_KEY"
```

## What each piece does

| Piece | Replaces what would otherwise live in mem0 source |
|---|---|
| `bootstrap.py` | The inline `DEFAULT_CONFIG` env reads + `include_router(sdk_compat)` + `/v1/ping/` route in `main.py` |
| `sdk_compat.py` | A new router under `server/routers/` |
| `auth_token_scheme.py` | Inline `Authorization: Token <key>` parsing inside `verify_auth` |
| `ping_route.py` | The `@app.get("/v1/ping/")` handler |
| `default_config_overrides.py` | The `_llm_config` / `_embedder_config` / `_pgvector_config` env reads |
| `../mem0-mcp/` (sibling) | The standalone mem0-mcp MCP server (replaces the former in-tree `mcp_bridge/`) |
| `plugins/patch_mem0_plugin.sh` | Direct edits to `mem0-plugin/scripts/*.py` |
| `plugins/redirect_mcp.sh` | Rewrite the plugin's `.mcp.json` to point at the local SSE server |

## Upgrade story

| Upstream change | Effect |
|---|---|
| `git pull` on mem0 | Hooks survive unless main.py/auth.py are heavily refactored. If they are, `git diff` makes the 12-line conflict obvious. |
| mem0-plugin upgrades (`~/.claude/plugins/cache/mem0-plugins/mem0/<new-ver>/`) | Re-run `plugins/patch_mem0_plugin.sh`; it auto-targets the latest version dir and is idempotent. |
| Local `self-mem0/` improvements | Nothing to do in mem0 — just edit files here. |

## Why this design

The previous approach put 24 in-place edits across `server/`, `mem0-plugin/`,
`openclaw/`, and `docs/`. Most of those edits were either wasted (the plugins
load from `~/.claude/plugins/` and `~/.openclaw/`, not from this repo) or
guaranteed to conflict on the next `git pull`. This package keeps every
behaviour change in one directory that mem0 will never touch, and reduces the
in-tree footprint to 12 lines that read like obvious hook points.

See `docs/self-hosted-agents.mdx` for the full integration story.

## Codex / Claude Code 插件本地配置

要使用自托管的 Mem0 服务替代托管平台，请参考：

- `SETUP_LOCAL.md` — 快速开始指南
- `examples/codex-mcp.local.json` — Codex MCP 配置模板
- `examples/claude-mcp.local.json` — Claude Code MCP 配置模板
