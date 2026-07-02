"""Tests for batched reduce and prewarm helpers."""

from __future__ import annotations

from services.copilot_llm import _batch_text_parts


def test_batch_text_parts_splits_without_dropping() -> None:
    parts = [f"chunk-{i}:" + ("x" * 500) for i in range(20)]
    batches = _batch_text_parts(parts, max_chars=2000)
    merged = "".join(batches)
    for i in range(20):
        assert f"chunk-{i}:" in merged
    assert len(batches) > 1
