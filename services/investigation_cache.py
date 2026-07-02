"""File-backed investigation cache for recovery after WebSocket drops or server reload."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.json_utils import to_json_safe

CACHE_DIR = Path(os.getenv("INVESTIGATION_CACHE_DIR", "data/investigations"))


def save_investigation_record(record: dict[str, Any]) -> None:
    inv_id = str(record.get("id") or "")
    if not inv_id:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{inv_id}.json"
    path.write_text(json.dumps(to_json_safe(record)))


def load_investigation_record(investigation_id: str) -> dict[str, Any] | None:
    path = CACHE_DIR / f"{investigation_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None
