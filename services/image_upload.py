"""Persist uploaded investigation images for server-side analysis."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

UPLOAD_DIR = Path(os.getenv("IMAGE_UPLOAD_DIR", "data/uploads"))
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_UPLOAD_BYTES = int(os.getenv("IMAGE_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))


def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def _safe_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return ext if ext in ALLOWED_EXTENSIONS else ".jpg"


def save_upload(content: bytes, filename: str) -> dict[str, str]:
    if not content:
        raise ValueError("empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"file exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit")

    ensure_upload_dir()
    image_id = str(uuid.uuid4())
    ext = _safe_extension(filename)
    stored_name = f"{image_id}{ext}"
    path = UPLOAD_DIR / stored_name
    path.write_bytes(content)

    return {
        "image_id": image_id,
        "image_path": str(path.resolve()),
        "stored_name": stored_name,
        "filename": Path(filename).name or stored_name,
        "preview_url": f"/api/intel/image/uploads/{image_id}",
    }


def resolve_upload_path(image_id: str) -> Path | None:
    ensure_upload_dir()
    for ext in ALLOWED_EXTENSIONS:
        candidate = UPLOAD_DIR / f"{image_id}{ext}"
        if candidate.is_file():
            return candidate
    return None
