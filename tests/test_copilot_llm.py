"""Tests for Qwen copilot orchestration with streaming."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.copilot import answer_copilot_async, stream_copilot_events


async def _fake_stream(*_a, **_k):
    for token in ["GitHub ", "via ", "sherlock."]:
        yield token


@pytest.mark.asyncio
async def test_greeting_uses_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DATA_DIR", str(tmp_path))
    import services.copilot_store as store

    monkeypatch.setattr(store, "COPILOT_DIR", tmp_path)

    result = {
        "query": "alice",
        "tool_results": [{"tool": "sherlock", "success": True, "data": []}],
        "fusion": {"fusion_score": 0.5},
        "correlation": {"clusters": []},
    }
    context = {"investigation_id": "inv-hi", "query": "alice", "result": result}

    with patch("services.copilot.ollama_available", new=AsyncMock(return_value=True)):
        with patch(
            "services.copilot.chat_with_qwen",
            new=AsyncMock(return_value="Hello! Ready to help with alice."),
        ) as chat:
            out = await answer_copilot_async("hi", context)

    assert out["data"]["mode"] == "llm"
    chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_casual_uses_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DATA_DIR", str(tmp_path))
    import services.copilot_store as store

    monkeypatch.setattr(store, "COPILOT_DIR", tmp_path)

    result = {
        "query": "alice",
        "tool_results": [{"tool": "sherlock", "success": True, "data": [{"site": "GitHub"}]}],
        "fusion": {"fusion_score": 0.5},
        "correlation": {"clusters": []},
    }
    context = {"investigation_id": "inv-casual", "query": "alice", "result": result}

    with patch("services.copilot.ollama_available", new=AsyncMock(return_value=True)):
        with patch("services.copilot.chat_with_qwen", new=AsyncMock(return_value="All good here.")) as chat:
            out = await answer_copilot_async("hey whats up", context)

    assert out["data"]["mode"] == "llm"
    chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_case_always_uses_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DATA_DIR", str(tmp_path))
    import services.copilot_store as store

    monkeypatch.setattr(store, "COPILOT_DIR", tmp_path)

    result = {
        "query": "alice",
        "tool_results": [
            {
                "tool": "sherlock",
                "success": True,
                "data": [{"site": "GitHub", "handle": "alice", "url": "https://github.com/alice"}],
            }
        ],
        "fusion": {"fusion_score": 0.5},
        "correlation": {"clusters": []},
    }
    context = {"investigation_id": "inv-brief", "query": "alice", "result": result}

    with patch("services.copilot.ollama_available", new=AsyncMock(return_value=True)):
        with patch(
            "services.copilot.chat_with_qwen",
            new=AsyncMock(return_value="GitHub profile found for alice."),
        ) as chat:
            out = await answer_copilot_async("show linked accounts", context)

    assert out["data"]["mode"] == "llm"
    chat.assert_awaited_once()
    assert "GitHub" in out["answer"]


@pytest.mark.asyncio
async def test_stream_yields_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DATA_DIR", str(tmp_path))
    import services.copilot_store as store

    monkeypatch.setattr(store, "COPILOT_DIR", tmp_path)

    result = {
        "query": "alice",
        "tool_results": [{"tool": "sherlock", "success": True, "data": [{"site": "GitHub"}]}],
        "fusion": {"fusion_score": 0.5},
        "correlation": {"clusters": []},
    }
    context = {"investigation_id": "inv-stream", "query": "alice", "result": result}

    with patch("services.copilot.ollama_available", new=AsyncMock(return_value=True)):
        with patch("services.copilot.stream_chat_with_qwen", side_effect=_fake_stream):
            events = []
            async for event in stream_copilot_events("accounts?", context):
                events.append(event)

    tokens = "".join(e.get("token", "") for e in events if "token" in e)
    assert "GitHub" in tokens
    assert any(e.get("done") for e in events)


@pytest.mark.asyncio
async def test_offline_reports_ollama_required():
    context = {
        "query": "bob",
        "result": {
            "query": "bob",
            "tool_results": [],
            "fusion": {"fusion_score": 0.1},
            "correlation": {"clusters": []},
        },
    }
    with patch("services.copilot.ollama_available", new=AsyncMock(return_value=False)):
        out = await answer_copilot_async("explain correlation cluster risk", context)
    assert out["engine"] == "offline"
    assert "Ollama" in out["answer"]
