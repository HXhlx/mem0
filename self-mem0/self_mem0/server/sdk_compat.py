"""
SDK compatibility router — maps MemoryClient (Python/TS) paths to existing handlers.

The Mem0 SDK clients (``MemoryClient``) call versioned paths like
``/v3/memories/add/`` and ``/v1/memories/{id}/`` while the self-hosted server
exposes unversioned routes (``/memories``, ``/search``, etc.).  This router
bridges the gap so that ``MemoryClient(api_key=..., host="http://localhost:8888")``
works out-of-the-box against the self-hosted server.

All routes delegate to the same underlying ``Memory`` instance and business
logic — no duplication.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_auth
from errors import upstream_error
from server_state import get_memory_instance

router = APIRouter(include_in_schema=False)

# ---------------------------------------------------------------------------
# Shared schemas (mirror what the SDK sends)
# ---------------------------------------------------------------------------


class _Message(BaseModel):
    role: str
    content: str


class _SdkMemoryCreate(BaseModel):
    """Body shape sent by ``POST /v3/memories/add/``."""

    messages: List[_Message]
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    app_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    infer: Optional[bool] = None
    memory_type: Optional[str] = None
    prompt: Optional[str] = None


class _SdkMemoryUpdate(BaseModel):
    """Body shape sent by ``PUT /v1/memories/{id}/``."""

    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class _SdkSearchRequest(BaseModel):
    """Body shape sent by ``POST /v3/memories/search/``."""

    query: str
    filters: Optional[Dict[str, Any]] = None
    top_k: Optional[int] = None
    threshold: Optional[float] = None
    rerank: Optional[bool] = None


class _SdkListRequest(BaseModel):
    """Body shape sent by ``POST /v3/memories/`` (get_all)."""

    filters: Optional[Dict[str, Any]] = None
    page: Optional[int] = None
    page_size: Optional[int] = None


# Default cap for list calls without filters; mirrors the SDK's default page size
_DEFAULT_LIST_TOP_K = 1000

# Upstream retry — port of remote VM commit b465cbea Part B.
# DashScope / OpenAI-compatible providers occasionally return 502 / rate-limit
# bursts under load (e.g. the P3 stress test surfaced ``provider_rate_limited``
# on 2/19 batches). Retry the offending Memory.add / Memory.search call three
# times with exponential backoff (2s → 4s → 8s) before propagating the failure.
_UPSTREAM_MAX_RETRIES = 3
_UPSTREAM_RETRY_DELAY = 2.0  # seconds; doubles each retry


def _call_upstream_with_retry(label: str, func, *args, **kwargs):
    """Run ``func(*args, **kwargs)`` with bounded retry on transient errors.

    The mem0 SDK does not classify its own errors, so we treat *any* exception
    raised by the wrapped call as potentially transient and retry. Honest
    failures (bad input, missing config) will still fail every attempt and the
    final exception is re-raised so the outer FastAPI handler maps it to
    ``upstream_error()``.
    """
    import logging
    import time

    log = logging.getLogger("self_mem0.sdk_compat")
    last_exc: Optional[Exception] = None
    for attempt in range(_UPSTREAM_MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — SDK doesn't classify
            last_exc = exc
            if attempt == _UPSTREAM_MAX_RETRIES - 1:
                break
            delay = _UPSTREAM_RETRY_DELAY * (2 ** attempt)
            log.warning(
                "%s attempt %d/%d failed (%s); retrying in %.1fs",
                label, attempt + 1, _UPSTREAM_MAX_RETRIES, exc, delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


_SERVER_FILTER_KEYS = {"user_id", "agent_id", "run_id"}
#: app_id is stored inside metadata by _add_memory_impl, so when callers ask
#: to filter by it we treat it as a metadata.app_id post-filter.
_METADATA_PROMOTED_KEYS = {"app_id"}


def _split_clause(clause: Dict[str, Any]):
    """Split a single flat clause like ``{"user_id":"x","metadata":{"type":"y"}}``
    into ``(server_filters, post_filters)`` for the OSS path.

    * Keys in ``_SERVER_FILTER_KEYS`` go to ``Memory.get_all(filters=...)``
      (which the OSS pgvector path understands natively).
    * ``app_id`` and any ``metadata.<sub>`` keys go to a post-filter dict
      applied client-side on the returned payloads, since ``Memory.get_all``
      does not support metadata sub-key filtering.
    * Unknown top-level keys are silently dropped (same behaviour as before).
    """
    server: Dict[str, Any] = {}
    post: Dict[str, Any] = {}
    for k, v in clause.items():
        if k in _SERVER_FILTER_KEYS:
            server[k] = v
        elif k in _METADATA_PROMOTED_KEYS:
            post[k] = v
        elif k == "metadata" and isinstance(v, dict):
            # platform-style {"metadata": {"type": "x", ...}} → flatten subkeys
            for sub_k, sub_v in v.items():
                post[sub_k] = sub_v
    return server, post


def _flatten_platform_filters(filters: Dict[str, Any]):
    """Normalise platform-style filters into the OSS execution plan.

    Returns a tuple ``(branches, post_filters)``:

    * ``branches`` — list of server-filter dicts to ``Memory.get_all`` over.
      A list of one dict means a simple AND; multiple dicts means OR-union.
    * ``post_filters`` — dict of metadata-style filters to apply client-side
      after the OSS call (since pgvector ``get_all`` does not understand
      metadata sub-keys, ``app_id``, or nested logical operators).

    Supported shapes (cover everything the three plugins actually send):

    * ``{}`` / ``None`` → ``([{}], {})`` (full table scan)
    * Flat dict like ``{"user_id":"x"}`` → ``([{"user_id":"x"}], {})``
    * ``{"AND":[{...},{...}]}`` (mem0-plugin, OpenClaw) → flattened to one
      server dict; metadata sub-keys lift into post_filters.
    * ``{"OR":[{"user_id":"a"},{"user_id":"b"}]}`` (global_search) → one
      server-filter dict per branch; callers union and dedupe by id.
    * Anything more complex (nested AND-of-AND, mixed AND+OR) is left to the
      flat path and may yield empty results — explicit empty is safer than
      silently wrong.
    """
    if not isinstance(filters, dict) or not filters:
        return [{}], {}

    # OR at top level — produce one server branch per OR clause
    or_clauses = filters.get("OR")
    if isinstance(or_clauses, list) and len(filters) == 1:
        branches: list = []
        merged_post: Dict[str, Any] = {}
        for raw_clause in or_clauses:
            if isinstance(raw_clause, dict):
                s, p = _split_clause(raw_clause)
                branches.append(s)
                merged_post.update(p)  # per-branch post-filters are rare; merge
        return (branches or [{}]), merged_post

    # AND at top level — flatten into a single server dict
    and_clauses = filters.get("AND")
    if isinstance(and_clauses, list) and len(filters) == 1:
        merged_clause: Dict[str, Any] = {}
        for raw_clause in and_clauses:
            if isinstance(raw_clause, dict):
                merged_clause.update(raw_clause)
        server, post = _split_clause(merged_clause)
        return [server], post

    # Flat dict — split directly
    server, post = _split_clause(filters)
    return [server], post


def _matches_post_filters(payload: Dict[str, Any], post_filters: Dict[str, Any]) -> bool:
    """Apply metadata post-filters to a single result payload."""
    if not post_filters:
        return True
    md = payload.get("metadata") or {}
    for k, v in post_filters.items():
        # Allow records without metadata.app_id to pass through when post_filter
        # requires app_id — this preserves backward compatibility for memories
        # created before app_id was introduced.
        actual = md.get(k)
        if actual is None and v is not None:
            continue
        if actual != v:
            return False
    return True


def _run_branches(branches, post_filters, runner):
    """Execute *runner(server_filters)* once per branch, dedupe by id, post-filter.

    ``runner`` returns either a ``{"results": [...]}`` dict or a bare list.
    Used by both _list_memories_impl and _search_impl so OR-union and
    metadata post-filtering share one code path.
    """
    seen: set = set()
    merged: list = []
    for server_filters in branches:
        raw = runner(server_filters)
        items = raw.get("results", []) if isinstance(raw, dict) else (raw or [])
        for item in items:
            if not isinstance(item, dict):
                continue
            if not _matches_post_filters(item, post_filters):
                continue
            mid = item.get("id")
            if mid is not None:
                if mid in seen:
                    continue
                seen.add(mid)
            merged.append(item)
    return merged


# ---------------------------------------------------------------------------
# Helper — serialize a vector-store row the same way main.py does
# ---------------------------------------------------------------------------

_RESERVED_PAYLOAD_KEYS = {"data", "user_id", "agent_id", "run_id", "hash", "created_at", "updated_at"}


def _serialize_memory(row: Any) -> Dict[str, Any]:
    payload = getattr(row, "payload", None) or {}
    return {
        "id": getattr(row, "id", None),
        "memory": payload.get("data"),
        "user_id": payload.get("user_id"),
        "agent_id": payload.get("agent_id"),
        "run_id": payload.get("run_id"),
        "hash": payload.get("hash"),
        "metadata": {k: v for k, v in payload.items() if k not in _RESERVED_PAYLOAD_KEYS},
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Add memories — POST /v3/memories/add/  and  POST /v1/memories/
# ---------------------------------------------------------------------------


def _add_memory_impl(memory_create: _SdkMemoryCreate, _auth=Depends(verify_auth)):
    if not any([memory_create.user_id, memory_create.agent_id, memory_create.run_id, memory_create.app_id]):
        raise HTTPException(
            status_code=400,
            detail="At least one identifier (user_id, agent_id, run_id, app_id) is required.",
        )

    # OSS Memory.add() doesn't accept app_id; preserve it inside metadata so
    # downstream filters/listings still see the project namespace.
    raw = {k: v for k, v in memory_create.model_dump().items() if v is not None and k != "messages"}
    app_id = raw.pop("app_id", None)
    if app_id is not None:
        metadata = dict(raw.get("metadata") or {})
        metadata.setdefault("app_id", app_id)
        raw["metadata"] = metadata
    try:
        return _call_upstream_with_retry(
            "Memory.add",
            get_memory_instance().add,
            messages=[m.model_dump() for m in memory_create.messages],
            **raw,
        )
    except Exception:
        raise upstream_error()


@router.post("/v3/memories/add/")
def v3_add_memory(memory_create: _SdkMemoryCreate, _auth=Depends(verify_auth)):
    return _add_memory_impl(memory_create, _auth)


@router.post("/v1/memories/")
def v1_add_memory(memory_create: _SdkMemoryCreate, _auth=Depends(verify_auth)):
    return _add_memory_impl(memory_create, _auth)


# ---------------------------------------------------------------------------
# List memories — POST /v3/memories/  and  POST /v2/memories/
# ---------------------------------------------------------------------------


def _list_memories_impl(body: _SdkListRequest, _auth=Depends(verify_auth)):
    """List memories with optional filters and a ``count`` for paging callers.

    The plugin's ``on_session_start.sh`` issues this with ``page_size=1`` purely
    to read ``count`` — so we always include it. When filters are supplied we
    delegate to ``Memory.get_all`` once per OR branch and post-filter for
    metadata sub-keys. Without filters we read directly from the vector store.
    """
    branches, post_filters = _flatten_platform_filters(body.filters or {})
    server_filters_active = any(branches) and any(b for b in branches)
    try:
        # When post_filters are present, we must fetch the full bucket first
        # and then apply client-side metadata filtering. Using page_size as
        # top_k would truncate the upstream result before post-filters have a
        # chance to select matching rows (e.g. top_k=5 might return 5 rows
        # all with app_id=Ext, leaving 0 rows after app_id=mem0ai-mem0 filter).
        fetch_top_k = _DEFAULT_LIST_TOP_K if post_filters else (
            body.page_size if body.page_size and body.page_size > 0 else _DEFAULT_LIST_TOP_K
        )
        page_size = body.page_size if body.page_size and body.page_size > 0 else None

        if server_filters_active or post_filters:
            mem = get_memory_instance()

            def runner(server_filters):
                if server_filters:
                    return mem.get_all(filters=server_filters, top_k=fetch_top_k)
                # branch with empty server filters → full scan via vector_store
                raw = mem.vector_store.list(top_k=fetch_top_k)
                rows = raw[0] if raw and isinstance(raw, list) and isinstance(raw[0], list) else raw or []
                return {"results": [_serialize_memory(row) for row in rows]}

            results = _run_branches(branches, post_filters, runner)
        else:
            top_k = body.page_size if body.page_size and body.page_size > 0 else _DEFAULT_LIST_TOP_K
            raw = get_memory_instance().vector_store.list(top_k=top_k)
            rows = raw[0] if raw and isinstance(raw, list) and isinstance(raw[0], list) else raw or []
            results = [_serialize_memory(row) for row in rows]
        # Always return total count (pre-pagination) so callers like the
        # session-start hook can read the bucket size even when page_size=1.
        total_count = len(results)
        if page_size is not None:
            results = results[:page_size]
        return {"results": results, "count": total_count}
    except Exception:
        raise upstream_error()


@router.post("/v3/memories/")
def v3_list_memories(body: _SdkListRequest, _auth=Depends(verify_auth)):
    return _list_memories_impl(body, _auth)


@router.get("/v3/memories/")
def v3_list_memories_get(
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    app_id: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    _auth=Depends(verify_auth),
):
    """GET alias for ``/v3/memories/`` — accepts identifiers as query params."""
    filters: Dict[str, Any] = {
        k: v
        for k, v in {
            "user_id": user_id,
            "agent_id": agent_id,
            "run_id": run_id,
            "app_id": app_id,
        }.items()
        if v is not None
    }
    return _list_memories_impl(
        _SdkListRequest(filters=filters or None, page=page, page_size=page_size),
        _auth,
    )


@router.post("/v2/memories/")
def v2_list_memories(body: _SdkListRequest, _auth=Depends(verify_auth)):
    return _list_memories_impl(body, _auth)


# ---------------------------------------------------------------------------
# Search — POST /v3/memories/search/  and  POST /v2/memories/search/
# ---------------------------------------------------------------------------


def _search_impl(search_req: _SdkSearchRequest, _auth=Depends(verify_auth)):
    try:
        branches, post_filters = _flatten_platform_filters(search_req.filters or {})
        requested_top_k = search_req.top_k or 10
        # When post_filters are present, inflate top_k so post-filtering still
        # yields enough results. A 5× multiplier is a reasonable heuristic;
        # Memory.search is fast (vector similarity), and the post-filter
        # reduces the set afterward.
        effective_top_k = requested_top_k * 5 if post_filters else requested_top_k
        params: Dict[str, Any] = {"top_k": effective_top_k}
        if search_req.threshold is not None:
            params["threshold"] = search_req.threshold
        if search_req.rerank is not None:
            params["rerank"] = search_req.rerank

        mem = get_memory_instance()

        def runner(server_filters):
            # Memory.search requires at least one of user_id/agent_id/run_id
            # in filters. If post_filters consumed all keys (e.g. only app_id),
            # server_filters may be empty — fall back to a full-scan list +
            # post-filter instead of raising ValueError.
            if not server_filters:
                raw_rows = mem.vector_store.list(top_k=effective_top_k)
                rows = raw_rows[0] if raw_rows and isinstance(raw_rows, list) and isinstance(raw_rows[0], list) else raw_rows or []
                return {"results": [_serialize_memory(row) for row in rows]}
            return _call_upstream_with_retry(
                "Memory.search",
                mem.search,
                query=search_req.query,
                filters=server_filters,
                **params,
            )

        # Single branch with no post-filters and non-empty server_filters
        # → preserve native shape so callers that assume the mem0 search
        # response shape see no behavioural change.
        if len(branches) == 1 and not post_filters and branches[0]:
            result = runner(branches[0])
            # Truncate to requested top_k if we inflated it
            if isinstance(result, dict) and "results" in result:
                result["results"] = result["results"][:requested_top_k]
            return result

        results = _run_branches(branches, post_filters, runner)
        return {"results": results[:requested_top_k]}
    except Exception:
        raise upstream_error()


@router.post("/v3/memories/search/")
def v3_search(search_req: _SdkSearchRequest, _auth=Depends(verify_auth)):
    return _search_impl(search_req, _auth)


@router.post("/v2/memories/search/")
def v2_search(search_req: _SdkSearchRequest, _auth=Depends(verify_auth)):
    return _search_impl(search_req, _auth)


# ---------------------------------------------------------------------------
# Single memory CRUD — /v1/memories/{id}/
# ---------------------------------------------------------------------------


@router.get("/v1/memories/{memory_id}/")
def v1_get_memory(memory_id: str, _auth=Depends(verify_auth)):
    try:
        return get_memory_instance().get(memory_id)
    except Exception:
        raise upstream_error()


@router.put("/v1/memories/{memory_id}/")
def v1_update_memory(memory_id: str, body: _SdkMemoryUpdate, _auth=Depends(verify_auth)):
    if body.text is None and body.metadata is None:
        raise HTTPException(status_code=400, detail="At least one of text or metadata must be provided.")
    try:
        return get_memory_instance().update(memory_id=memory_id, data=body.text or "", metadata=body.metadata)
    except Exception:
        raise upstream_error()


@router.delete("/v1/memories/{memory_id}/")
def v1_delete_memory(memory_id: str, _auth=Depends(verify_auth)):
    try:
        get_memory_instance().delete(memory_id=memory_id)
        return {"message": "Memory deleted successfully"}
    except Exception:
        raise upstream_error()


# ---------------------------------------------------------------------------
# History — GET /v1/memories/{id}/history/
# ---------------------------------------------------------------------------


@router.get("/v1/memories/{memory_id}/history/")
def v1_memory_history(memory_id: str, _auth=Depends(verify_auth)):
    try:
        return get_memory_instance().history(memory_id=memory_id)
    except Exception:
        raise upstream_error()


# ---------------------------------------------------------------------------
# Delete all — DELETE /v1/memories/
# ---------------------------------------------------------------------------


@router.delete("/v1/memories/")
def v1_delete_all(
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    _auth=Depends(verify_auth),
):
    if not any([user_id, agent_id, run_id]):
        raise HTTPException(status_code=400, detail="At least one identifier is required.")
    try:
        params = {
            k: v for k, v in {"user_id": user_id, "agent_id": agent_id, "run_id": run_id}.items() if v is not None
        }
        # mem0's Memory.delete_all internally calls vector_store.list(filters=...)
        # which caps at ~100 rows per call, so a single invocation only removes
        # up to 100 memories. Loop until the bucket is empty so callers can
        # actually delete large user buckets in one HTTP request.
        mem = get_memory_instance()
        total_deleted = 0
        for iteration in range(_DELETE_ALL_MAX_ITERS):
            before = _count_user_bucket(mem, params)
            if before == 0:
                break
            mem.delete_all(**params)
            after = _count_user_bucket(mem, params)
            deleted_this_iter = max(0, before - after)
            total_deleted += deleted_this_iter
            # If a call removed nothing the bucket has rows we can't see via
            # vector_store.list() — stop to avoid an infinite loop.
            if deleted_this_iter == 0:
                break
        return {
            "message": "All relevant memories deleted",
            "deleted": total_deleted,
            "iterations": iteration + 1,
        }
    except Exception:
        raise upstream_error()


_DELETE_ALL_MAX_ITERS = 50  # cap: 50 * ~100 rows/iter = 5000 rows / request


def _count_user_bucket(mem, params: Dict[str, Any]) -> int:
    """Quick row count for one of the entity filters; tolerant to backend quirks."""
    try:
        data = mem.get_all(filters=params, top_k=_DEFAULT_LIST_TOP_K)
        if isinstance(data, dict):
            return len(data.get("results", []))
        return len(data or [])
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Entities — /v1/entities/  and  /v2/entities/{type}/{name}/
# ---------------------------------------------------------------------------


@router.get("/v1/entities/")
def v1_list_entities(_auth=Depends(verify_auth)):
    """List entities in the same ``{"results": [...]}`` shape the SDK expects."""
    from routers.entities import Entity, TYPE_TO_FIELD

    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"total_memories": 0, "created_at": None, "updated_at": None}
    )

    def _parse_ts(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    # Re-use the same payload scanner from the entities router
    from routers.entities import _iter_payloads

    for payload in _iter_payloads():
        created = _parse_ts(payload.get("created_at"))
        updated = _parse_ts(payload.get("updated_at")) or created
        for entity_type, field in TYPE_TO_FIELD.items():
            value = payload.get(field)
            if not value:
                continue
            bucket = buckets[(entity_type, str(value))]
            bucket["total_memories"] += 1
            if created and (bucket["created_at"] is None or created < bucket["created_at"]):
                bucket["created_at"] = created
            if updated and (bucket["updated_at"] is None or updated > bucket["updated_at"]):
                bucket["updated_at"] = updated

    results = [
        Entity(id=entity_id, type=entity_type, **data)
        for (entity_type, entity_id), data in sorted(buckets.items(), key=lambda item: (item[0][0], item[0][1]))
    ]
    return {"results": [r.model_dump() for r in results]}


@router.delete("/v2/entities/{entity_type}/{entity_name}/")
def v2_delete_entity(entity_type: str, entity_name: str, _auth=Depends(verify_auth)):
    from routers.entities import TYPE_TO_FIELD

    field = TYPE_TO_FIELD.get(entity_type)
    if field is None:
        raise HTTPException(status_code=400, detail=f"Unknown entity type: {entity_type}")
    try:
        get_memory_instance().delete_all(**{field: entity_name})
    except Exception:
        raise upstream_error()
    return {"message": "Entity deleted"}


# ---------------------------------------------------------------------------
# Events (OpenClaw PlatformBackend) — stubs
# ---------------------------------------------------------------------------


@router.get("/v1/events/")
def v1_list_events(_auth=Depends(verify_auth)):
    """No-op: the self-hosted server does not track events."""
    return {"results": []}


@router.get("/v1/event/{event_id}/")
def v1_get_event(event_id: str, _auth=Depends(verify_auth)):
    raise HTTPException(status_code=404, detail="Events are not supported on the self-hosted server.")
