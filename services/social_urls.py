"""Normalize social post URLs for safe external navigation."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

# SERP sometimes returns photos/a.congratulations-to-... instead of photos/congratulations-to-...
_FB_BAD_ALBUM_SLUG_RE = re.compile(r"/photos/a\.([a-zA-Z][\w-]+)", re.I)


def fix_facebook_post_url(url: str) -> str:
    """Repair malformed Facebook photo/post paths that redirect to login."""
    if not url or "facebook.com" not in url.lower():
        return url
    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    path = _FB_BAD_ALBUM_SLUG_RE.sub(r"/photos/\1", parsed.path)
    host = parsed.netloc or "www.facebook.com"
    if not host.startswith("www.") and host.endswith("facebook.com"):
        host = f"www.{host}"
    return urlunparse((parsed.scheme or "https", host, path, parsed.params, parsed.query, ""))


def external_visit_url(url: str | None) -> str | None:
    """Best-effort URL for opening the original page in a browser tab."""
    if not url:
        return None
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        return None
    return fix_facebook_post_url(cleaned)
