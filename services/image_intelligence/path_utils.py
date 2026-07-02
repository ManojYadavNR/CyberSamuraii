"""Shared path / URL helpers for image investigations."""

from __future__ import annotations

import os
import re


_LOCAL_MARKERS = (
    "/home/",
    "/tmp/",
    "/var/",
    "data/uploads",
    "\\users\\",
    "c:\\",
)


def is_local_path(value: str) -> bool:
    if not value:
        return True
    low = value.strip().lower().replace("\\", "/")
    if low.startswith("file:"):
        return True
    if not (low.startswith("/") or re.match(r"^[a-z]:/", low)):
        return False
    return any(m in low for m in _LOCAL_MARKERS) or "/uploads/" in low or "/tmp/" in low


def is_public_url(value: str) -> bool:
    low = value.strip().lower()
    return low.startswith("http://") or low.startswith("https://")


def display_target_label(query: str, *, face_detected: bool = False) -> str:
    if is_local_path(query):
        base = os.path.basename(query.replace("\\", "/"))
        if face_detected:
            return f"Person in uploaded photo ({base})"
        return f"Uploaded image ({base})"
    return query


def public_only(values: list[str]) -> list[str]:
    return [v for v in values if v and is_public_url(v) and not is_local_path(v)]
