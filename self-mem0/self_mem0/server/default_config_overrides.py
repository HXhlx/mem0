"""Env-driven overrides for ``server/main.py``'s ``DEFAULT_CONFIG``.

Applied by :func:`bootstrap.patch_default_config` *before* the FastAPI app
calls ``initialize_state(DEFAULT_CONFIG)``. This lets the existing server
read additional env vars that upstream main.py ignores:

==========================  ===============================================
Env var                     Effect
==========================  ===============================================
``OPENAI_BASE_URL``         Routes LLM calls through a custom OpenAI-
                            compatible endpoint (e.g. DashScope, vLLM).
``EMBEDDER_API_KEY``        Separates the embedder key from the LLM key.
``EMBEDDER_BASE_URL``       Separate base URL for the embedder.
``EMBEDDING_DIMS``          Forces the pgvector column width to match the
                            embedder's actual output (1536 for DashScope
                            text-embedding-v4, 1024 for bge-large, etc.).
``RERANKER_PROVIDER``       Enable a reranker for ``Memory.search(rerank=True)``.
                            Set to ``dashscope`` to use our DashScope qwen3-
                            rerank adapter, or any provider mem0 already knows
                            (``cohere``, ``llm_reranker``, etc.).
``RERANKER_MODEL``          Model name passed to the reranker (e.g.
                            ``qwen3-rerank``).
``RERANKER_API_KEY``        Reranker key; defaults to ``OPENAI_API_KEY`` for
                            DashScope so the same DashScope account works
                            without a second secret.
``RERANKER_URL``            Optional override of the reranker endpoint.
==========================  ===============================================

Each override is only applied when its env var is set, so an upstream
installation without any of them keeps its current behaviour.
"""

from __future__ import annotations

import os
from typing import Any, Dict


def patch(default_config: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate *default_config* in place with env-driven overrides.

    Returns the same dict for convenience so callers can write
    ``main.DEFAULT_CONFIG = patch(main.DEFAULT_CONFIG)``.
    """
    openai_base_url = os.environ.get("OPENAI_BASE_URL")
    embedder_api_key = os.environ.get("EMBEDDER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    embedder_base_url = os.environ.get("EMBEDDER_BASE_URL") or openai_base_url
    embedding_dims = os.environ.get("EMBEDDING_DIMS")

    llm_cfg = default_config.get("llm", {}).get("config", {})
    if openai_base_url:
        llm_cfg["openai_base_url"] = openai_base_url

    embedder_cfg = default_config.get("embedder", {}).get("config", {})
    if embedder_api_key:
        embedder_cfg["api_key"] = embedder_api_key
    if embedder_base_url:
        embedder_cfg["openai_base_url"] = embedder_base_url
    if embedding_dims:
        embedder_cfg["embedding_dims"] = int(embedding_dims)

    vector_cfg = default_config.get("vector_store", {}).get("config", {})
    if embedding_dims:
        vector_cfg["embedding_model_dims"] = int(embedding_dims)

    # Reranker: only inject when RERANKER_PROVIDER is set, so unconfigured
    # installs keep their current (no-reranker) behaviour.
    reranker_provider = (os.environ.get("RERANKER_PROVIDER") or "").strip()
    if reranker_provider:
        reranker_cfg: Dict[str, Any] = {}
        if (model := os.environ.get("RERANKER_MODEL")):
            reranker_cfg["model"] = model
        # DashScope reuses OPENAI_API_KEY by default; explicit RERANKER_API_KEY wins
        api_key = os.environ.get("RERANKER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            reranker_cfg["api_key"] = api_key
        if (url := os.environ.get("RERANKER_URL")):
            reranker_cfg["url"] = url
        default_config["reranker"] = {
            "provider": reranker_provider,
            "config": reranker_cfg,
        }

    return default_config
