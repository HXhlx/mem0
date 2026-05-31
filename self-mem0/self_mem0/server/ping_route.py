"""``GET /v1/ping/`` — health stub for the Mem0 SDK MemoryClient.

Mounted by ``bootstrap.attach_routes`` onto the existing FastAPI app.

mem0ai ``MemoryClient`` (and the older ``mem0ai 2.0.x`` shipped with Hermes)
calls ``Project._validate_org_project`` inside the client constructor, which
``raise ValueError`` when ``org_id`` / ``project_id`` are missing. The hosted
platform answers ``/v1/ping/`` with real tenant identifiers; self-hosted has
no multi-tenant concept, so we return synthetic constants. Any later SDK call
that echoes them back as query params is still routed to the same single-tenant
backend.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends


def make_ping_handler():
    """Return the ping handler bound to the live ``verify_auth`` dependency.

    Built as a factory so callers (``bootstrap``) can wire the handler in
    after ``server/auth.py`` has finished importing.
    """
    from auth import verify_auth

    def ping(_auth=Depends(verify_auth)) -> Dict[str, Any]:
        return {
            "status": "ok",
            "org_id": "self-hosted",
            "project_id": "default",
            "user_email": None,
        }

    return ping
