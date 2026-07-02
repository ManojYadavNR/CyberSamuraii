"""Tests for lossless copilot packs and chunked context assembly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.copilot_context import (
    PACK_VERSION,
    build_investigation_index,
    build_raw_investigation_pack,
    expand_oversized_chunks,
    get_raw_full,
    iter_investigation_chunks,
    pack_single_pass_context,
    select_chunk_ids,
)
from services.copilot_store import ensure_copilot_pack, load_copilot_pack, save_copilot_pack


@pytest.fixture
def sample_result() -> dict:
    return {
        "query": "testuser",
        "feature": "username_intel",
        "extra_field_only_in_result": {"nested": True},
        "tool_results": [
            {
                "tool": "google_dorking",
                "success": True,
                "data": [{"title": "Hackathon", "url": "https://example.com/h"}],
                "raw_output": '{"hits": 1}',
            },
            {
                "tool": "samurai",
                "success": True,
                "data": [{"platform": "instagram", "username": "testuser"}],
            },
        ],
        "fusion": {"fusion_score": 0.82, "deduplicated_entities": []},
        "evidence_extraction": {
            "google_search_intel": {"hits": [{"title": "College"}]},
            "samurai_social_intel": {"instagram": {"bio": "hello"}},
        },
    }


def test_build_pack_stores_verbatim_raw_full(sample_result: dict) -> None:
    pack = build_raw_investigation_pack(sample_result, investigation_id="inv-1", query="testuser")
    raw = get_raw_full(pack)
    assert pack["pack_version"] == PACK_VERSION
    assert pack["investigation_id"] == "inv-1"
    assert raw["extra_field_only_in_result"]["nested"] is True
    assert raw["tool_results"][0]["raw_output"] == '{"hits": 1}'
    assert raw["evidence_extraction"]["samurai_social_intel"]["instagram"]["bio"] == "hello"


def test_chunks_cover_every_tool_and_section(sample_result: dict) -> None:
    pack = build_raw_investigation_pack(sample_result, investigation_id="inv-2")
    chunks = iter_investigation_chunks(get_raw_full(pack))
    labels = {c["label"] for c in chunks}
    assert "google_dorking" in labels
    assert "samurai" in labels
    assert "fusion" in labels
    assert "evidence_extraction" in labels
    index = build_investigation_index(chunks)
    assert index["chunk_count"] == len(chunks)


def test_expand_splits_large_tool_data_array() -> None:
    big = {
        "tool": "maigret",
        "success": True,
        "data": [{"site": f"s{i}", "url": f"https://example.com/{i}"} for i in range(50)],
        "raw_output": "x" * 2000,
    }
    chunk = {"chunk_id": "tool:maigret:0", "label": "maigret", "kind": "tool_result", "payload": big}
    expanded = expand_oversized_chunks([chunk], max_chars=500, items_per_part=10)
    assert len(expanded) >= 2
    assert len(expanded) < 50
    all_items = []
    for part in expanded:
        payload = part["payload"]
        if isinstance(payload.get("data"), list):
            all_items.extend(payload["data"])
    assert len(all_items) == 50


def test_greeting_detection() -> None:
    from services.copilot_context import is_greeting

    assert is_greeting("hi")
    assert is_greeting("hlo")
    assert is_greeting("Hello!")
    assert not is_greeting("what did samurai find on instagram")


def test_chunks_for_message_focused_samurai(sample_result: dict) -> None:
    from services.copilot_context import chunks_for_message

    chunks = expand_oversized_chunks(
        iter_investigation_chunks(sample_result),
        max_chars=12000,
    )
    active, scope = chunks_for_message("What did Samurai find on Instagram?", chunks)
    assert scope == "focused"
    labels = {c["label"] for c in active}
    assert "samurai" in labels
    assert len(active) < len(chunks)


def test_select_chunk_ids_for_samurai_question(sample_result: dict) -> None:
    chunks = iter_investigation_chunks(sample_result)
    ids = select_chunk_ids("What did Samurai find on Instagram?", chunks)
    assert ids is not None
    matched_labels = {c["label"] for c in chunks if c["chunk_id"] in ids}
    assert "samurai" in matched_labels


def test_single_pass_context_includes_all_chunks(sample_result: dict) -> None:
    chunks = iter_investigation_chunks(sample_result)
    text = pack_single_pass_context(chunks, query="testuser")
    parsed = json.loads(text)
    assert parsed["coverage"] == "complete_single_pass"
    assert len(parsed["chunks"]) == len(chunks)


def test_save_and_load_copilot_pack(tmp_path: Path, sample_result: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_DATA_DIR", str(tmp_path))
    import services.copilot_store as store

    monkeypatch.setattr(store, "COPILOT_DIR", tmp_path)

    pack = ensure_copilot_pack("inv-3", sample_result, query="testuser")
    assert pack["query"] == "testuser"

    loaded = load_copilot_pack("inv-3")
    assert loaded is not None
    assert get_raw_full(loaded)["tool_results"][1]["tool"] == "samurai"

    pack["chat_history"] = [{"role": "user", "content": "hi"}]
    save_copilot_pack(pack)
    reloaded = load_copilot_pack("inv-3")
    assert reloaded["chat_history"][0]["content"] == "hi"
