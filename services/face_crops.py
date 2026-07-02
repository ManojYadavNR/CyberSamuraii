"""Persist and serve face crop images from investigations."""

from __future__ import annotations

import os
import re
from pathlib import Path

from services.image_upload import UPLOAD_DIR

CROP_DIR = Path(os.getenv("FACE_CROP_DIR", "data/face_crops"))
_UPLOAD_ID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)


def upload_id_from_path(image_path: str) -> str | None:
    if not image_path:
        return None
    match = _UPLOAD_ID_RE.search(image_path.replace("\\", "/"))
    return match.group(1) if match else None


def crop_dir_for_upload(upload_id: str) -> Path:
    path = CROP_DIR / upload_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_face_crop(image_path: str, bbox: list[float], *, tool: str, index: int) -> str:
    import cv2

    upload_id = upload_id_from_path(image_path) or "unknown"
    out_dir = crop_dir_for_upload(upload_id)
    out_path = out_dir / f"{tool}_face{index}.jpg"

    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"failed to decode image: {image_path}")
    x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
    h, w = img.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        raise RuntimeError("invalid face bounding box")
    crop = img[y1:y2, x1:x2]
    cv2.imwrite(str(out_path), crop)
    return str(out_path.resolve())


def crop_preview_url(crop_path: str | None) -> str | None:
    if not crop_path:
        return None
    path = Path(crop_path)
    upload_id = path.parent.name
    if not upload_id or upload_id == "unknown":
        return None
    return f"/api/intel/image/crops/{upload_id}/{path.name}"


def resolve_crop_path(upload_id: str, crop_name: str) -> Path | None:
    if ".." in crop_name or "/" in crop_name or "\\" in crop_name:
        return None
    candidate = CROP_DIR / upload_id / crop_name
    if candidate.is_file():
        return candidate
    return None


def seed_preview_url(seed_image: str) -> str | None:
    upload_id = upload_id_from_path(seed_image)
    if upload_id:
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            if (UPLOAD_DIR / f"{upload_id}{ext}").is_file():
                return f"/api/intel/image/uploads/{upload_id}"
    if seed_image.startswith(("http://", "https://")):
        return seed_image
    return None
