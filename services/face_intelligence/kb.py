"""Face knowledge base — store embeddings and match across investigations."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from services.json_utils import embedding_nonempty, normalize_embedding

logger = logging.getLogger(__name__)

_KB_DIR = Path(os.getenv("FACE_KB_DIR", "data/face_kb"))
_INDEX_PATH = _KB_DIR / "index.json"
_EMB_DIR = _KB_DIR / "embeddings"
_MATCH_THRESHOLD = float(os.getenv("FACE_KB_MATCH_THRESHOLD", "0.62"))


def _ensure_dirs() -> None:
    _KB_DIR.mkdir(parents=True, exist_ok=True)
    _EMB_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> list[dict[str, Any]]:
    _ensure_dirs()
    if not _INDEX_PATH.exists():
        return []
    try:
        return json.loads(_INDEX_PATH.read_text())
    except Exception:
        return []


def _save_index(records: list[dict[str, Any]]) -> None:
    _ensure_dirs()
    _INDEX_PATH.write_text(json.dumps(records, indent=0))


def _cosine_similarity(a, b) -> float:
    import numpy as np

    va = np.asarray(a, dtype=np.float32).flatten()
    vb = np.asarray(b, dtype=np.float32).flatten()
    if va.size != vb.size or va.size == 0:
        return 0.0
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom < 1e-9:
        return 0.0
    return float(np.dot(va, vb) / denom)


class FaceKnowledgeBase:
    """File-backed face embedding store — grows smarter after every investigation."""

    def store(
        self,
        *,
        embedding: list[float] | Any,
        source: str,
        platform: str = "",
        entity_id: str | None = None,
        image_url: str = "",
        image_path: str = "",
        investigation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        import numpy as np

        _ensure_dirs()
        record_id = str(uuid4())
        arr = np.asarray(embedding, dtype=np.float32).flatten()
        if arr.size < 32:
            return ""
        emb_path = _EMB_DIR / f"{record_id}.npy"
        np.save(emb_path, arr)
        record = {
            "record_id": record_id,
            "source": source,
            "platform": platform,
            "entity_id": entity_id,
            "image_url": image_url,
            "image_path": image_path,
            "investigation_id": investigation_id,
            "embedding_dim": int(arr.size),
            "embedding_file": emb_path.name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "metadata": metadata or {},
        }
        records = _load_index()
        records.append(record)
        if len(records) > 5000:
            records = records[-5000:]
        _save_index(records)
        return record_id

    def search(
        self,
        embedding: list[float] | Any,
        *,
        limit: int = 10,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        import numpy as np

        threshold = min_similarity if min_similarity is not None else _MATCH_THRESHOLD
        query = np.asarray(embedding, dtype=np.float32).flatten()
        if query.size < 32:
            return []

        hits: list[dict[str, Any]] = []
        for rec in _load_index():
            emb_file = _EMB_DIR / rec.get("embedding_file", "")
            if not emb_file.exists():
                continue
            try:
                stored = np.load(emb_file)
                sim = _cosine_similarity(query, stored)
                if sim >= threshold:
                    hits.append({**rec, "similarity": round(sim, 4)})
            except Exception:
                continue
        hits.sort(key=lambda h: -h["similarity"])
        return hits[:limit]

    def count(self) -> int:
        return len(_load_index())


face_kb = FaceKnowledgeBase()


def store_findings_in_kb(
    findings: list[Any],
    *,
    investigation_id: str | None = None,
    seed_image: str = "",
) -> int:
    """Persist face embeddings from image findings into the knowledge base."""
    stored = 0
    for finding in findings:
        if getattr(finding, "field", None) != "face_embedding":
            continue
        evidence = getattr(finding, "evidence", {}) or {}
        raw_emb = evidence.get("embedding_vector")
        if not embedding_nonempty(raw_emb):
            continue
        rid = face_kb.store(
            embedding=normalize_embedding(raw_emb),
            source=getattr(finding, "source_tool", "unknown"),
            platform=str(evidence.get("platform") or ""),
            image_url=str(evidence.get("url") or ""),
            image_path=str(evidence.get("file") or seed_image),
            investigation_id=investigation_id,
            metadata={
                "embedding_signature": evidence.get("embedding_signature"),
                "face_index": evidence.get("face_index"),
            },
        )
        if rid:
            stored += 1
    return stored
