"""Tests for face knowledge base."""

from __future__ import annotations

import numpy as np

from services.face_intelligence.kb import face_kb


def test_face_kb_store_and_search(tmp_path, monkeypatch):
    monkeypatch.setenv("FACE_KB_DIR", str(tmp_path / "face_kb"))
    emb = np.random.randn(512).astype(np.float32)
    rid = face_kb.store(embedding=emb, source="insightface", platform="github.com", image_url="https://github.com/u")
    assert rid

    hits = face_kb.search(emb, min_similarity=0.99)
    assert len(hits) >= 1
    assert hits[0]["record_id"] == rid


def test_face_kb_rejects_small_embedding(tmp_path, monkeypatch):
    monkeypatch.setenv("FACE_KB_DIR", str(tmp_path / "face_kb2"))
    rid = face_kb.store(embedding=[0.1, 0.2], source="test")
    assert rid == ""
