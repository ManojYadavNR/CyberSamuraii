"""Extract structured intelligence from OCR text."""

from __future__ import annotations

import re

from services.discovery.validators import extract_emails_from_text, extract_urls_from_text, is_plausible_handle
from services.discovery.attribution import extract_phones_from_text

NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b")
USERNAME_RE = re.compile(r"@([\w][\w.-]{1,30})")
COMPANY_RE = re.compile(
    r"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)*\s+(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Co\.?|GmbH|PLC))\b",
    re.IGNORECASE,
)
EVENT_KEYWORDS = (
    "hackathon",
    "conference",
    "summit",
    "meetup",
    "workshop",
    "seminar",
    "expo",
    "festival",
    "symposium",
    "bootcamp",
)


def parse_ocr_entities(text: str) -> dict[str, list[str]]:
    """Return categorized strings extracted from visible text."""
    if not text or not text.strip():
        return {}

    out: dict[str, list[str]] = {
        "emails": [],
        "phones": [],
        "urls": [],
        "usernames": [],
        "names": [],
        "companies": [],
        "events": [],
        "visible_text": [],
    }

    def _add(key: str, val: str) -> None:
        val = val.strip()
        if val and val not in out[key]:
            out[key].append(val)

    _add("visible_text", text[:5000])

    for email in extract_emails_from_text(text):
        _add("emails", email)
    for phone in extract_phones_from_text(text):
        _add("phones", phone)
    for url in extract_urls_from_text(text):
        _add("urls", url)
    for match in USERNAME_RE.findall(text):
        if is_plausible_handle(match):
            _add("usernames", match.lower())
    for match in NAME_RE.findall(text):
        if len(match.split()) >= 2:
            _add("names", match)
    for match in COMPANY_RE.findall(text):
        _add("companies", match.strip())
    lower = text.lower()
    for line in text.splitlines():
        line_lower = line.lower().strip()
        if not line_lower:
            continue
        if any(kw in line_lower for kw in EVENT_KEYWORDS):
            _add("events", line.strip()[:200])
    if any(kw in lower for kw in EVENT_KEYWORDS):
        for kw in EVENT_KEYWORDS:
            if kw in lower:
                idx = lower.find(kw)
                snippet = text[max(0, idx - 40) : idx + len(kw) + 40].strip()
                _add("events", snippet[:200])

    return out
