"""Embed long text by chunking — port of remote commit ``b465cbea`` Part A.

DashScope ``text-embedding-v4`` hard-rejects inputs over 8192 tokens. The
remote VM patches mem0's ``OpenAIEmbedding.embed`` directly to chunk long
text, embed each chunk, average the vectors, and re-normalise to unit
length. We achieve the same via monkey-patch from ``bootstrap.patch_config``,
so the upstream file stays unmodified.

Cutoff: ``_EMBED_MAX_CHARS=6000`` characters (~3000 tokens, conservatively
under the 8192 limit even for English-heavy text). The original mem0 code
also calls ``text.replace("\\n", " ")`` before sending, which we preserve.

Behaviour:

* Texts ≤ ``_EMBED_MAX_CHARS`` → original ``embed`` path (single API call).
* Longer → split into N chunks → N embeddings → mean → L2-normalise.
* Idempotent — re-applying the patch is a no-op.
"""

from __future__ import annotations

import logging
from typing import Any, List

log = logging.getLogger("self_mem0.embed_chunking")

# 1 token ≈ 2 Chinese chars / 4 English chars; 6000 chars ≈ 1500–3000 tokens,
# safely under DashScope's 8192-token hard limit even for English text.
_EMBED_MAX_CHARS = 6000


def install_long_text_chunking(max_chars: int = _EMBED_MAX_CHARS) -> None:
    try:
        from mem0.embeddings.openai import OpenAIEmbedding
    except Exception:
        log.warning("mem0.embeddings.openai.OpenAIEmbedding not importable; skipping chunk patch")
        return

    if getattr(OpenAIEmbedding, "_self_mem0_chunked", False):
        return

    original_embed = OpenAIEmbedding.embed

    def _embed_long(self: Any, text: str, memory_action: str) -> List[float]:
        """Chunk → embed each → mean → L2-normalise."""
        chunks = [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
        embeddings: List[List[float]] = [
            original_embed(self, chunk, memory_action) for chunk in chunks
        ]
        if not embeddings:
            return []
        dims = len(embeddings[0])
        avg = [sum(e[d] for e in embeddings) / len(embeddings) for d in range(dims)]
        # Cosine similarity expects unit-length vectors; re-normalise after averaging.
        norm = sum(x * x for x in avg) ** 0.5
        if norm > 0:
            avg = [x / norm for x in avg]
        return avg

    def patched_embed(self: Any, text: str, memory_action: str = "add") -> List[float]:
        text = (text or "").replace("\n", " ")
        if len(text) <= max_chars:
            return original_embed(self, text, memory_action)
        return _embed_long(self, text, memory_action)

    patched_embed.__wrapped__ = original_embed  # type: ignore[attr-defined]
    OpenAIEmbedding.embed = patched_embed  # type: ignore[assignment]
    OpenAIEmbedding._self_mem0_chunked = True  # type: ignore[attr-defined]
    log.info("self_mem0: OpenAIEmbedding.embed will chunk text > %d chars", max_chars)
