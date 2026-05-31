"""self_mem0 — self-hosted Mem0 server adapter package.

Loaded by mem0 ``server/main.py`` and ``server/auth.py`` via opt-in
``try/except`` import hooks. Provides:

* SDK-path compatibility for ``MemoryClient`` (Python/TS) → ``server/`` REST
* ``Authorization: Token <key>`` parsing for ``MemoryClient`` SDK
* ``/v1/ping/`` health stub satisfying old SDK ``Project._validate_org_project``
* Env-driven ``DEFAULT_CONFIG`` overrides (custom LLM/embedder base URL, dims)
* Stdio MCP bridge (separate package under ``mcp_bridge/``)

Designed to be optional: when ``self_mem0`` isn't on ``sys.path``, the server
runs exactly as upstream ships it.
"""
__version__ = "0.1.0"
