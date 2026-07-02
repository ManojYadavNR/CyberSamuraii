"""Derive image search context from parallel tool outputs."""

from __future__ import annotations

import re

from schemas.common import ToolResult
from services.json_utils import embedding_nonempty, normalize_embedding

LOGO_CATEGORIES = frozenset({"logo", "company logo", "product packaging", "event banner"})
PERSON_CATEGORIES = frozenset({"person", "id badge", "police uniform", "military uniform"})
FACE_FIELDS = frozenset({"face_embedding", "face_detection", "face_count"})


def build_image_search_context(tool_results: list[ToolResult] | None) -> dict:
    ocr_parts: list[str] = []
    face_count = 0
    clip_scores: list[tuple[str, float]] = []
    face_crop_path: str | None = None
    best_face_conf = 0.0

    for tr in tool_results or []:
        if not tr.success or not tr.data:
            continue
        for item in tr.data:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("visible_text") or "").strip()
            if text:
                ocr_parts.append(text)
            if item.get("platform") == "ocr_text" and item.get("text"):
                ocr_parts.append(str(item["text"]))

            field = str(item.get("field") or "")
            category = str(item.get("category") or "")
            if field in FACE_FIELDS or category == "face":
                face_count += 1
                conf = float(item.get("confidence") or 0)
                crop = item.get("crop_path")
                if crop and conf >= best_face_conf:
                    best_face_conf = conf
                    face_crop_path = str(crop)
            if item.get("faces_detected") is not None:
                try:
                    face_count = max(face_count, int(item["faces_detected"]))
                except (TypeError, ValueError):
                    pass

            label = str(item.get("label") or item.get("value") or "")
            conf = float(item.get("confidence") or item.get("score") or 0)
            if tr.tool == "clip" and label:
                clip_scores.append((label.lower(), conf))

    ocr_text = re.sub(r"\s+", " ", " ".join(ocr_parts)).strip()[:300]

    image_category = ""
    if clip_scores:
        clip_scores.sort(key=lambda x: -x[1])
        image_category = clip_scores[0][0]

    is_logo = image_category in LOGO_CATEGORIES or (
        face_count == 0 and any(c in image_category for c in ("logo", "banner", "packaging"))
    )
    is_person_photo = face_count > 0 or image_category in PERSON_CATEGORIES

    primary_face_embedding: list[float] | None = None
    best_emb_conf = 0.0
    for tr in tool_results or []:
        if not tr.success:
            continue
        for item in tr.data or []:
            if not isinstance(item, dict):
                continue
            emb = item.get("embedding_vector")
            conf = float(item.get("confidence") or item.get("face_quality_score") or 0)
            if embedding_nonempty(emb) and conf >= best_emb_conf:
                best_emb_conf = conf
                primary_face_embedding = normalize_embedding(emb)

    return {
        "ocr_text": ocr_text,
        "face_count": face_count,
        "image_category": image_category,
        "is_logo": is_logo,
        "is_person_photo": is_person_photo,
        "face_crop_path": face_crop_path,
        "primary_face_embedding": primary_face_embedding,
    }
