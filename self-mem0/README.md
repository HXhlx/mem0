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
├── apply.sh                    one-shot enable (docker override + bridge + plugin patch)
├── revert.sh                   undo the above
├── self_mem0/                  Python package — wired in by main.py / auth.py hooks
│   └── server/
│       ├── bootstrap.py        public API: patch_config(...), attach_routes(app)
│       ├── default_config_overrides.py   env-driven LLM/embedder/dims overrides
│       ├── sdk_compat.py       /v3/memories/* + /v1/memories/* routes for MemoryClient
│       ├── ping_route.py       /v1/ping/ stub (satisfies older SDK Project validator)
│       └── auth_token_scheme.py  Authorization: Token <key> parser
├── mcp_bridge/                 stdio MCP server forwarding to /v3/memories/* REST
│   └── mem0_mcp_bridge/        9 tools mirroring mcp.mem0.ai schema
├── plugins/
│   └── patch_mem0_plugin.sh    inject MEM0_HOST into the user-level Claude Code plugin
└── docs/
    └── self-hosted-agents.mdx  full integration guide
```

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
| `mcp_bridge/` | A new `server/mcp_bridge/` subpackage |
| `plugins/patch_mem0_plugin.sh` | Direct edits to `mem0-plugin/scripts/*.py` |

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
