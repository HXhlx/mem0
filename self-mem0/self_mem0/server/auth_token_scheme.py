"""``Authorization: Token <key>`` parser for the Mem0 SDK.

Imported by ``server/auth.py`` via a try/except hook *after* the standard
Bearer / X-API-Key checks have run. Returns:

* a :class:`User` — when ``Token <key>`` matched a per-user API key
* ``None``         — when ``Token <key>`` matched ``ADMIN_API_KEY``
* the sentinel ``MISS`` — when the request does not use the Token scheme
  (caller should continue with the normal 401 / AUTH_DISABLED fallthrough)

The sentinel keeps the call site a single line and avoids leaking the
"not-applicable" case as a falsy ``None`` (which would be ambiguous with
the admin-key success case).
"""

from __future__ import annotations

import os
import secrets
from typing import Any

#: Returned when the request does not use the Token scheme at all.
MISS: Any = object()

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "").strip()


def try_token_auth(request, db) -> Any:
    """Parse ``Authorization: Token <key>`` from *request*.

    Returns :data:`MISS` when the header is absent or uses a different scheme,
    so the caller can fall through to its existing 401 / AUTH_DISABLED logic.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("token "):
        return MISS

    token_value = auth_header[len("token "):].strip()
    if not token_value:
        return MISS

    # Local import: server/auth.py is still being module-loaded when this
    # function is first defined; resolving at call time avoids the cycle.
    from auth import _mark_auth_type, _resolve_user_from_api_key

    if ADMIN_API_KEY and secrets.compare_digest(token_value, ADMIN_API_KEY):
        _mark_auth_type(request, "admin_api_key")
        return None

    _mark_auth_type(request, "api_key_token_scheme")
    return _resolve_user_from_api_key(token_value, db)
