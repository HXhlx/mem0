"""self_mem0 bootstrap — wires the adapter into the mem0 server FastAPI app.

Called by ``server/main.py`` at two well-defined points via a single import +
two function calls:

.. code-block:: python

    # near the top of server/main.py
    try:
        from self_mem0.server import bootstrap as _self_mem0
    except ImportError:
        _self_mem0 = None

    # ... after DEFAULT_CONFIG is defined, before initialize_state(...)
    if _self_mem0: _self_mem0.patch_config(DEFAULT_CONFIG)

    # ... after app = FastAPI(...) and after the include_router(...) block
    if _self_mem0: _self_mem0.attach_routes(app)

Both calls are no-ops when the env vars / sdk_compat router aren't needed,
and the whole module is conditional on the import succeeding, so removing
``self-mem0/`` from sys.path leaves the server behaving exactly as upstream.

We deliberately do NOT auto-run on import: ``server/main.py`` is mid-module
when our hook fires, so importing ``main`` back from here would deadlock.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger("self_mem0.bootstrap")


def patch_config(default_config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply env-driven LLM/embedder/pgvector overrides to *default_config*.

    Idempotent — safe to call multiple times. Mutates in place and also
    returns the dict for use in chained assignments.
    Also registers any custom reranker providers (``dashscope``) with mem0's
    ``RerankerFactory`` so the upstream ``Memory(config={...})`` constructor
    recognises the name when it parses ``DEFAULT_CONFIG['reranker']``.
    Also installs monkey-patches for the SDK behaviours we want to standardise
    across all callers (Memory.get_all default top_k, OpenAIEmbedding long-text
    chunking) — ports of remote VM commits 8e0b81ce and b465cbea Part A.
    """
    from . import default_config_overrides, embed_chunking, memory_defaults

    _register_custom_rerankers()
    try:
        memory_defaults.install_higher_default_top_k()
    except Exception:
        log.exception("self_mem0: get_all top_k patch failed; continuing with upstream default of 20")
    try:
        embed_chunking.install_long_text_chunking()
    except Exception:
        log.exception("self_mem0: long-text chunking patch failed; DashScope may reject >8192-token texts")

    try:
        return default_config_overrides.patch(default_config)
    except Exception:
        log.exception("self_mem0: DEFAULT_CONFIG patch failed; continuing with upstream defaults")
        return default_config


def _register_custom_rerankers() -> None:
    """Inject our DashScope reranker into mem0's RerankerFactory.

    mem0's ``RerankerFactory.provider_to_class`` is a class-level dict mapping
    provider names → (importable class path, config class). Adding a key here
    makes ``Memory(config={"reranker": {"provider": "dashscope", ...}})`` work
    without modifying any upstream mem0 file.

    Safe to call multiple times — registration is idempotent.
    """
    try:
        from mem0.configs.rerankers.base import BaseRerankerConfig
        from mem0.utils.factory import RerankerFactory
    except Exception:
        log.warning("self_mem0: mem0.utils.factory.RerankerFactory not importable; reranker disabled")
        return

    # Register dashscope provider → DashScopeReranker
    RerankerFactory.provider_to_class.setdefault(
        "dashscope",
        ("self_mem0.server.dashscope_reranker.DashScopeReranker", BaseRerankerConfig),
    )
    log.info("self_mem0: dashscope reranker registered in RerankerFactory")


def attach_routes(app) -> None:
    """Register the SDK-compat router and ``/v1/ping/`` stub on *app*.

    Call once, after ``main.py`` has built the FastAPI app and included its
    own routers — guarantees our overrides take precedence on path conflicts
    (there aren't any today, but the ordering is intentional).
    """
    from . import ping_route, sdk_compat

    try:
        app.include_router(sdk_compat.router)
        app.add_api_route(
            "/v1/ping/",
            ping_route.make_ping_handler(),
            methods=["GET"],
            include_in_schema=False,
        )
        log.info("self_mem0: sdk_compat router + /v1/ping/ attached")
    except Exception:
        log.exception("self_mem0: route attachment failed; server will run without SDK compat")
