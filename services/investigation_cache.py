"""File-backed investigation cache for recovery after WebSocket drops or server reload."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.json_utils import to_json_safe

CACHE_DIR = Path(os.getenv("INVESTIGATION_CACHE_DIR", "data/investigations"))
# Running records older than this are treated as dead (UI must not poll forever).
STALE_RUNNING_SEC = float(os.getenv("INVESTIGATION_STALE_RUNNING_SEC", "120"))


def save_investigation_record(record: dict[str, Any]) -> None:
    inv_id = str(record.get("id") or "")
    if not inv_id:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    record = dict(record)
    record.setdefault("started_at", now)
    record["updated_at"] = now
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


def _record_age_sec(record: dict[str, Any]) -> float:
    for key in ("updated_at", "started_at"):
        raw = record.get(key)
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return max(0.0, time.time() - ts.timestamp())
        except Exception:
            continue
    # Fall back to file mtime.
    inv_id = str(record.get("id") or "")
    path = CACHE_DIR / f"{inv_id}.json"
    if path.is_file():
        return max(0.0, time.time() - path.stat().st_mtime)
    return 0.0


def expire_stale_running_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    """If a record is stuck in running past STALE_RUNNING_SEC, mark it error and persist."""
    if not record or record.get("status") != "running":
        return record
    age = _record_age_sec(record)
    if age < STALE_RUNNING_SEC:
        return record
    expired = {
        **record,
        "status": "error",
        "error": (
            f"Investigation timed out after {age:.0f}s without completing. "
            "Please run the search again."
        ),
        "stale_expired": True,
    }
    save_investigation_record(expired)
    return expired


def expire_all_stale_running(*, force: bool = False) -> int:
    """Mark stale (or all, if force) running investigations as error. Returns count expired."""
    if not CACHE_DIR.is_dir():
        return 0
    count = 0
    for path in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("status") != "running":
            continue
        if force:
            data = {
                **data,
                "status": "error",
                "error": "Investigation interrupted (server restart). Please run the search again.",
                "stale_expired": True,
            }
            save_investigation_record(data)
            count += 1
            continue
        before = data.get("status")
        data = expire_stale_running_record(data)
        if data and data.get("status") != before:
            count += 1
    return count
