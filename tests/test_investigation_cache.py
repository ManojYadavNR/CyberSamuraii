"""Tests for investigation file cache."""

from services.investigation_cache import load_investigation_record, save_investigation_record


def test_save_and_load_investigation_record(tmp_path, monkeypatch):
    monkeypatch.setenv("INVESTIGATION_CACHE_DIR", str(tmp_path))
    from importlib import reload
    import services.investigation_cache as mod
    reload(mod)

    record = {
        "id": "abc-123",
        "query": "test.png",
        "query_type": "image",
        "status": "running",
    }
    mod.save_investigation_record(record)
    loaded = mod.load_investigation_record("abc-123")
    assert loaded is not None
    assert loaded["status"] == "running"
    assert loaded["query"] == "test.png"
