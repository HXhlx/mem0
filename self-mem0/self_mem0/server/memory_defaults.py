"""Install higher default ``top_k`` for ``Memory.get_all``.

Ports remote commit ``8e0b81ce``:
    fix: GET /memories with filters now respects limit parameter

Upstream mem0 ``Memory.get_all`` defaults ``top_k=20``, silently truncating
results for any caller that does not pass an explicit limit. The native
``GET /memories`` route in ``server/main.py`` is one such caller, and the
remote VM patches it to forward a 1000 limit. We achieve the same effect
across **all** callers by monkey-patching the default itself, without
modifying upstream files.

Behaviour:

* Existing explicit ``top_k=...`` calls (including our sdk_compat layer)
  pass through unchanged — the wrapper only injects the new default when
  the caller omits the argument.
* Idempotent — re-applying the patch is a no-op (guarded by attribute).
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("self_mem0.memory_defaults")

DEFAULT_TOP_K = 1000


def install_higher_default_top_k(new_default: int = DEFAULT_TOP_K) -> None:
    try:
        from mem0.memory.main import Memory
    except Exception:
        log.warning("mem0.memory.main.Memory not importable; skipping get_all default patch")
        return

    if getattr(Memory, "_self_mem0_top_k_patched", False):
        return

    original = Memory.get_all

    def patched(self: Any, *, filters: Any = None, top_k: int = new_default, **kwargs: Any) -> Any:
        return original(self, filters=filters, top_k=top_k, **kwargs)

    patched.__wrapped__ = original  # type: ignore[attr-defined]
    Memory.get_all = patched  # type: ignore[assignment]
    Memory._self_mem0_top_k_patched = True  # type: ignore[attr-defined]
    log.info("self_mem0: Memory.get_all default top_k → %d", new_default)
