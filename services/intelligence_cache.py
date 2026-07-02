"""TTL cache for reusable intelligence (OCR, embeddings, reverse search)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

_CACHE_DIR = Path(os.getenv("INTELLIGENCE_CACHE_DIR", "data/intelligence_cache"))
_DEFAULT_TTL = int(os.getenv("INTELLIGENCE_CACHE_TTL", "86400"))


def _cache_key(namespace: str, target: str) -> str:
    digest = hashlib.sha256(f"{namespace}:{target}".encode()).hexdigest()[:32]
    return digest


def _path_for(key: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{key}.json"


def get_cached(namespace: str, target: str) -> Any | None:
    key = _cache_key(namespace, target)
    path = _path_for(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        if time.time() - float(payload.get("cached_at", 0)) > _DEFAULT_TTL:
            path.unlink(missing_ok=True)
            return None
        return payload.get("data")
    except Exception:
        return None


def set_cached(namespace: str, target: str, data: Any) -> None:
    key = _cache_key(namespace, target)
    path = _path_for(key)
    path.write_text(json.dumps({
        "namespace": namespace,
        "target": target[:200],
        "cached_at": time.time(),
        "data": data,
    }))


def image_content_key(image_path: str) -> str:
    try:
        with open(image_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return hashlib.sha256(image_path.encode()).hexdigest()
