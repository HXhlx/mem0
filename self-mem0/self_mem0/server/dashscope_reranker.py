"""DashScope (qwen3-rerank) reranker for the mem0 self-hosted server.

Implements mem0's :class:`BaseReranker` interface so that
``Memory(config={..., "reranker": {...}}).search(rerank=True, ...)``
re-ranks search hits via DashScope's text-rerank endpoint::

    POST https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank

Request:
    {"model": "qwen3-rerank",
     "input": {"query": "...", "documents": ["...", "..."]},
     "parameters": {"return_documents": false, "top_n": <int>}}

Response:
    {"output": {"results": [{"index": 0, "relevance_score": 0.85}, ...]}}

The reranker reuses the same DashScope API key already configured for the
LLM/embedder (``OPENAI_API_KEY``) and does not require any new credential.
Registered into mem0's ``RerankerFactory`` by ``bootstrap.attach_reranker``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

from mem0.reranker.base import BaseReranker

log = logging.getLogger("self_mem0.dashscope_reranker")

DEFAULT_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
DEFAULT_MODEL = "qwen3-rerank"
REQUEST_TIMEOUT = 30.0


class DashScopeReranker(BaseReranker):
    """Cross-encoder reranker backed by DashScope qwen3-rerank.

    Config keys (all optional):

    * ``model``    — defaults to ``qwen3-rerank``
    * ``api_key``  — falls back to ``OPENAI_API_KEY`` env var
    * ``url``      — full endpoint URL; defaults to DashScope's text-rerank
    * ``top_k``    — default rerank top_n; ``Memory.search`` overrides per call
    """

    def __init__(self, config: Any):
        cfg = config if isinstance(config, dict) else getattr(config, "config", None) or {}
        if hasattr(config, "model_dump") and not isinstance(config, dict):
            cfg = config.model_dump()
        self.model = cfg.get("model") or DEFAULT_MODEL
        self.api_key = (
            cfg.get("api_key")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("DASHSCOPE_API_KEY")
            or ""
        ).strip()
        self.url = (cfg.get("url") or DEFAULT_URL).strip()
        self.default_top_k = cfg.get("top_k")
        if not self.api_key:
            log.warning("DashScopeReranker initialised without an api_key; calls will 401")

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = None,
    ) -> List[Dict[str, Any]]:
        """Re-order *documents* by query relevance.

        ``documents`` is the list mem0 ``Memory.search`` produced — each entry
        is a dict with a ``memory`` field (the text mem0 stored). We send those
        texts to DashScope, then map ``results[i].index`` back to the original
        document objects and overwrite ``score`` with ``relevance_score``.

        On any HTTP / parse error we fall back to returning *documents*
        truncated to ``top_k`` — degrading to vector-only ordering is always
        safer than returning an empty list to the caller.
        """
        if not documents:
            return documents

        effective_top_k = top_k if top_k is not None else (self.default_top_k or len(documents))
        effective_top_k = min(effective_top_k, len(documents))

        texts: List[str] = []
        for doc in documents:
            txt = doc.get("memory") or doc.get("text") or doc.get("data") or ""
            texts.append(str(txt))

        body = {
            "model": self.model,
            "input": {"query": query, "documents": texts},
            "parameters": {"return_documents": False, "top_n": effective_top_k},
        }

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                resp = client.post(
                    self.url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            if resp.status_code >= 400:
                log.warning("DashScope rerank HTTP %d: %s", resp.status_code, resp.text[:200])
                return documents[:effective_top_k]
            data = resp.json()
        except Exception:
            log.exception("DashScope rerank call failed; returning vector order")
            return documents[:effective_top_k]

        results = (data.get("output") or {}).get("results") or []
        if not results:
            log.warning("DashScope rerank returned no results; falling back")
            return documents[:effective_top_k]

        reranked: List[Dict[str, Any]] = []
        for entry in results:
            idx = entry.get("index")
            score = entry.get("relevance_score")
            if not isinstance(idx, int) or idx < 0 or idx >= len(documents):
                continue
            doc = dict(documents[idx])  # don't mutate caller's list
            if score is not None:
                doc["score"] = score
            reranked.append(doc)

        return reranked[:effective_top_k] if reranked else documents[:effective_top_k]
