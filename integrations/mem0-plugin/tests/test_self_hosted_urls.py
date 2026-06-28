import importlib


def test_search_url_uses_hosted_default(monkeypatch):
    monkeypatch.delenv("MEM0_HOST", raising=False)
    import _search

    module = importlib.reload(_search)

    assert module.API_URL == "https://api.mem0.ai"
    assert module.SEARCH_URL == "https://api.mem0.ai/v3/memories/search/"


def test_search_url_uses_mem0_host(monkeypatch):
    monkeypatch.setenv("MEM0_HOST", "http://localhost:8888/")
    import _search

    module = importlib.reload(_search)

    assert module.API_URL == "http://localhost:8888"
    assert module.SEARCH_URL == "http://localhost:8888/v3/memories/search/"


def test_hook_api_url_uses_mem0_host(monkeypatch):
    monkeypatch.setenv("MEM0_HOST", "http://localhost:8888/")
    import auto_capture
    import auto_import
    import capture_compact_summary
    import capture_session_summary
    import import_competing_tools
    import on_pre_compact
    import session_timeline

    modules = [
        auto_capture,
        auto_import,
        capture_compact_summary,
        capture_session_summary,
        import_competing_tools,
        on_pre_compact,
        session_timeline,
    ]

    for module in modules:
        assert importlib.reload(module).API_URL == "http://localhost:8888"
