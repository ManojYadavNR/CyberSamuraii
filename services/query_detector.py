"""Detect investigation query type from user input."""

from __future__ import annotations

import os
import re

from services.multi_input import parse_investigation_input

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", re.IGNORECASE)
PHONE_RE = re.compile(r"^\+?[\d\s\-().]{7,20}$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", re.IGNORECASE)
IMAGE_RE = re.compile(r"^https?://.+\.(jpg|jpeg|png|gif|webp)(\?.*)?$", re.IGNORECASE)
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def detect_query_type(query: str) -> str:
    parsed = parse_investigation_input(query)
    low = query.strip().lower()
    if low.startswith("http://") or low.startswith("https://"):
        if "instagram.com/p/" in low or "instagram.com/reel/" in low:
            return "url"
    return parsed.primary_type
