"""Persist copilot raw packs and chat history per investigation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.copilot_context import PACK_VERSION, build_raw_investigation_pack, get_raw_full
from services.json_utils import to_json_safe

COPILOT_DIR = Path(os.getenv("COPILOT_DATA_DIR", "data/copilot"))


def _path(investigation_id: str) -> Path:
    return COPILOT_DIR / f"{investigation_id}.json"


def _case_path(case_id: str) -> Path:
    return COPILOT_DIR / f"case_{case_id}.json"


def save_copilot_pack(pack: dict[str, Any]) -> None:
    inv_id = str(pack.get("investigation_id") or "")
    if not inv_id:
        return
    COPILOT_DIR.mkdir(parents=True, exist_ok=True)
    _path(inv_id).write_text(json.dumps(to_json_safe(pack), ensure_ascii=False))


def load_copilot_pack(investigation_id: str) -> dict[str, Any] | None:
    path = _path(investigation_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _pack_needs_rebuild(existing: dict[str, Any] | None, result: dict[str, Any]) -> bool:
    if not existing:
        return True
    if existing.get("pack_version", 1) < PACK_VERSION:
        return True
    if not get_raw_full(existing) and result:
        return True
    return False


def ensure_copilot_pack(
    investigation_id: str,
    result: dict[str, Any],
    *,
    query: str = "",
) -> dict[str, Any]:
    existing = load_copilot_pack(investigation_id)
    if existing and not _pack_needs_rebuild(existing, result):
        return existing

    prior_history = (existing or {}).get("chat_history") or []
    prior_digests = (existing or {}).get("chunk_digests") or {}
    prior_brief = (existing or {}).get("investigation_brief")
    pack = build_raw_investigation_pack(result, investigation_id=investigation_id, query=query)
    if prior_history:
        pack["chat_history"] = prior_history
    if prior_digests and get_raw_full(existing) == get_raw_full(pack):
        pack["chunk_digests"] = prior_digests
    if prior_brief and isinstance(prior_brief, dict):
        pack["investigation_brief"] = prior_brief
    save_copilot_pack(pack)
    return pack


def update_chunk_digests(investigation_id: str, new_digests: dict[str, str]) -> None:
    pack = load_copilot_pack(investigation_id)
    if not pack or not new_digests:
        return
    merged = dict(pack.get("chunk_digests") or {})
    merged.update(new_digests)
    pack["chunk_digests"] = merged
    save_copilot_pack(pack)


def append_chat_turn(investigation_id: str, role: str, content: str) -> None:
    pack = load_copilot_pack(investigation_id)
    if not pack:
        return
    history = list(pack.get("chat_history") or [])
    history.append({"role": role, "content": content})
    pack["chat_history"] = history[-24:]
    save_copilot_pack(pack)


def load_case_copilot_pack(case_id: str) -> dict[str, Any] | None:
    path = _case_path(case_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_case_copilot_pack(pack: dict[str, Any]) -> None:
    case_id = str(pack.get("case_id") or "")
    if not case_id:
        return
    COPILOT_DIR.mkdir(parents=True, exist_ok=True)
    _case_path(case_id).write_text(json.dumps(to_json_safe(pack), ensure_ascii=False))


def append_case_chat_turn(case_id: str, role: str, content: str) -> None:
    """Persist chat history at case scope (shared across all investigations in the case)."""
    if not case_id:
        return
    pack = load_case_copilot_pack(case_id) or {
        "case_id": case_id,
        "pack_version": PACK_VERSION,
        "chat_history": [],
    }
    history = list(pack.get("chat_history") or [])
    history.append({"role": role, "content": content})
    pack["chat_history"] = history[-40:]
    save_case_copilot_pack(pack)
