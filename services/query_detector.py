"""Detect investigation query type from user input."""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", re.IGNORECASE)
PHONE_RE = re.compile(r"^\+?[\d\s\-().]{7,20}$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", re.IGNORECASE)
IMAGE_RE = re.compile(r"^https?://.+\.(jpg|jpeg|png|gif|webp)(\?.*)?$", re.IGNORECASE)


def detect_query_type(query: str) -> str:
    q = query.strip()
    if EMAIL_RE.match(q):
        return "email"
    if PHONE_RE.match(q):
        return "phone"
    if IMAGE_RE.match(q) or q.startswith(("http://", "https://")) and any(
        ext in q.lower() for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp")
    ):
        return "image"
    if DOMAIN_RE.match(q) and "@" not in q:
        return "domain"
    if q.replace(".", "").replace(":", "").isdigit() or "/" in q and any(c.isdigit() for c in q):
        return "infra"
    return "username"
