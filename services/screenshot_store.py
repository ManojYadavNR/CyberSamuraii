"""Persist page screenshots for investigation previews."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "data/screenshots"))
MAX_SCREENSHOT_BYTES = int(os.getenv("SCREENSHOT_MAX_BYTES", str(5 * 1024 * 1024)))


def ensure_screenshot_dir() -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return SCREENSHOT_DIR


def _safe_id(raw: str) -> str:
    cleaned = re.sub(r"[^\w.-]", "", raw)
    return cleaned[:64] or str(uuid.uuid4())


def cache_key_for_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def preview_url_for(screenshot_id: str) -> str:
    return f"/api/intel/screenshots/{screenshot_id}"


def resolve_screenshot_path(screenshot_id: str) -> Path | None:
    ensure_screenshot_dir()
    safe = _safe_id(screenshot_id)
    for ext in (".png", ".jpg", ".webp"):
        candidate = SCREENSHOT_DIR / f"{safe}{ext}"
        if candidate.is_file():
            return candidate
    return None


def load_cached_screenshot(url: str) -> str | None:
    """Return preview URL if we already captured this page."""
    key = cache_key_for_url(url)
    if resolve_screenshot_path(key):
        return preview_url_for(key)
    return None


def save_screenshot(content: bytes, *, url: str | None = None, screenshot_id: str | None = None) -> dict[str, str]:
    if not content:
        raise ValueError("empty screenshot")
    if len(content) > MAX_SCREENSHOT_BYTES:
        raise ValueError("screenshot too large")

    ensure_screenshot_dir()
    sid = _safe_id(screenshot_id or cache_key_for_url(url or str(uuid.uuid4())))
    path = SCREENSHOT_DIR / f"{sid}.png"
    path.write_bytes(content)
    return {
        "screenshot_id": sid,
        "screenshot_path": str(path.resolve()),
        "preview_url": preview_url_for(sid),
        "source_url": url or "",
    }
