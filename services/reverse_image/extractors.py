"""Extract intelligence from reverse image match pages."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from services.discovery.validators import extract_urls_from_text, is_plausible_handle, normalize_domain
from services.google_dorking.filters import handle_from_profile_url


def extract_platform(url: str) -> str | None:
    return normalize_domain(url)


def extract_profile_urls(url: str, title: str = "", snippet: str = "") -> list[str]:
    from services.reverse_image.filters import is_junk_url, is_real_profile_url

    urls = {url}
    urls.update(extract_urls_from_text(f"{title} {snippet}"))
    profiles: list[str] = []
    for u in urls:
        if is_junk_url(u) or not is_real_profile_url(u):
            continue
        if handle_from_profile_url(u) or urlparse(u).path.strip("/"):
            profiles.append(u)
    return profiles


def extract_usernames_from_url(url: str) -> list[str]:
    handle = handle_from_profile_url(url)
    if handle and is_plausible_handle(handle):
        return [handle.lower()]
    path = urlparse(url if "://" in url else f"https://{url}").path.strip("/")
    if not path:
        return []
    segment = path.split("/")[0].split("?")[0]
    if is_plausible_handle(segment):
        return [segment.lower()]
    return []


_GENERIC_ORG_BLOCKLIST = frozenset({
    "profile", "avatar", "visual search", "bing images", "search images",
    "your free avatar", "free download", "microsoft bing", "gravatar",
    "profile picture", "link in bio", "try visual search",
})


def extract_organizations(text: str) -> list[str]:
    orgs: list[str] = []
    for match in re.findall(r"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,3})\b", text):
        low = match.strip().lower()
        if len(match) < 4 or low in _GENERIC_ORG_BLOCKLIST:
            continue
        if any(b in low for b in _GENERIC_ORG_BLOCKLIST):
            continue
        if match not in orgs:
            orgs.append(match)
    return orgs[:3]
