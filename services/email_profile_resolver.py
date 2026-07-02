"""Resolve public profile URLs for email registrations and Gravatar-linked accounts."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from services.discovery.validators import normalize_domain

# Holehe / Gravatar domain → profile URL template ({username} required).
PROFILE_URL_TEMPLATES: dict[str, str] = {
    "twitter.com": "https://twitter.com/{username}",
    "x.com": "https://x.com/{username}",
    "spotify.com": "https://open.spotify.com/user/{username}",
    "firefox.com": "https://www.mozilla.org/en-US/firefox/accounts/",
    "office365.com": "https://outlook.live.com/",
    "eventbrite.com": "https://www.eventbrite.com/u/{username}",
    "plurk.com": "https://www.plurk.com/{username}",
    "github.com": "https://github.com/{username}",
    "gitlab.com": "https://gitlab.com/{username}",
    "instagram.com": "https://www.instagram.com/{username}/",
    "facebook.com": "https://www.facebook.com/{username}",
    "linkedin.com": "https://www.linkedin.com/in/{username}",
    "reddit.com": "https://www.reddit.com/user/{username}",
    "youtube.com": "https://www.youtube.com/@{username}",
    "tiktok.com": "https://www.tiktok.com/@{username}",
    "pinterest.com": "https://www.pinterest.com/{username}/",
    "gravatar.com": "https://gravatar.com/{username}",
    "en.gravatar.com": "https://gravatar.com/{username}",
    "medium.com": "https://medium.com/@{username}",
    "twitch.tv": "https://www.twitch.tv/{username}",
}

_PLATFORM_ALIASES: dict[str, str] = {
    "twitter": "twitter.com",
    "x": "x.com",
    "spotify": "spotify.com",
    "firefox": "firefox.com",
    "office365": "office365.com",
    "eventbrite": "eventbrite.com",
    "plurk": "plurk.com",
    "gravatar": "gravatar.com",
}


def _normalize_platform_key(platform: str) -> str:
    raw = (platform or "").strip().lower()
    if not raw:
        return ""
    if raw in _PLATFORM_ALIASES:
        return _PLATFORM_ALIASES[raw]
    if "." not in raw:
        return f"{raw}.com"
    return normalize_domain(raw) or raw


def build_profile_url(platform: str, username: str | None) -> str | None:
    """Build a canonical public profile URL when a username/handle is known."""
    user = (username or "").strip().lstrip("@")
    if not user or user.lower() in {"none", "null", "unknown"}:
        return None
    if "@" in user:
        return None
    key = _normalize_platform_key(platform)
    template = PROFILE_URL_TEMPLATES.get(key)
    if not template or "{username}" not in template:
        return None
    return template.format(username=user)


def _extract_gravatar_handle(profile: dict[str, Any]) -> str | None:
    for key in ("profile_url", "profileUrl"):
        raw = profile.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        path = urlparse(raw).path.strip("/")
        if path and path.lower() not in {"profile", "avatar"}:
            return path.split("/")[-1]
    about = str(profile.get("about") or profile.get("aboutMe") or profile.get("bio") or "")
    match = re.search(r"gravatar\.com/([\w.-]+)", about, re.I)
    if match:
        return match.group(1)
    return None


def index_gravatar_accounts(public_profiles: list[dict[str, Any]]) -> dict[str, str]:
    """Map normalized platform host → username from Gravatar linked accounts."""
    out: dict[str, str] = {}
    for profile in public_profiles:
        if not isinstance(profile, dict):
            continue
        handle = _extract_gravatar_handle(profile)
        if handle:
            out.setdefault("gravatar.com", handle)
        for acct in profile.get("accounts") or []:
            if not isinstance(acct, dict):
                continue
            domain = _normalize_platform_key(str(acct.get("domain") or ""))
            username = acct.get("username") or acct.get("display")
            if domain and isinstance(username, str) and username.strip():
                out.setdefault(domain, username.strip().lstrip("@"))
    return out


def username_candidates_from_email(email: str) -> list[str]:
    """Conservative handle guesses from the email local part."""
    local = email.split("@", 1)[0].strip().lower()
    if not local or len(local) < 3:
        return []
    compact = re.sub(r"[^a-z0-9]", "", local)
    candidates = [local]
    if compact and compact != local:
        candidates.append(compact)
    # Strip trailing digits when long enough (manjeshshetty1 → manjeshshetty)
    trimmed = re.sub(r"\d+$", "", compact)
    if trimmed and len(trimmed) >= 5 and trimmed not in candidates:
        candidates.append(trimmed)
    return candidates[:4]


def resolve_registration_profile(
    platform: str,
    *,
    email: str,
    gravatar_index: dict[str, str],
) -> tuple[str | None, str | None]:
    """Return (username, profile_url) for a holehe registration."""
    key = _normalize_platform_key(platform)
    username = gravatar_index.get(key) or gravatar_index.get("gravatar.com")
    if not username:
        for guess in username_candidates_from_email(email):
            if len(guess) >= 5:
                username = guess
                break
    url = build_profile_url(platform, username)
    return username, url


def enrich_confirmed_findings(
    confirmed: list[dict[str, Any]],
    *,
    email: str,
    public_profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach usernames and profile URLs to email registrations without changing types."""
    gravatar_index = index_gravatar_accounts(public_profiles)
    enriched: list[dict[str, Any]] = []
    for item in confirmed:
        row = dict(item)
        ftype = row.get("type")
        platform = str(row.get("platform") or "")
        if ftype == "linked_account":
            username = row.get("username")
            url = build_profile_url(platform, str(username) if username else None)
            if url:
                row["profile_url"] = url
                row["url"] = url
        elif ftype == "account_registration" and platform:
            username, url = resolve_registration_profile(platform, email=email, gravatar_index=gravatar_index)
            if username:
                row["username"] = username
            if url:
                row["profile_url"] = url
                row["url"] = url
        enriched.append(row)
    return enriched


def enrich_public_profiles(public_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize Gravatar fields for downstream fusion/evidence."""
    out: list[dict[str, Any]] = []
    for profile in public_profiles:
        if not isinstance(profile, dict):
            continue
        row = dict(profile)
        about = row.get("about") or row.get("aboutMe")
        if about and not row.get("bio"):
            row["bio"] = about
        if row.get("avatar_url") and not row.get("profile_image"):
            row["profile_image"] = row["avatar_url"]
        for acct in row.get("accounts") or []:
            if not isinstance(acct, dict):
                continue
            domain = acct.get("domain")
            username = acct.get("username") or acct.get("display")
            url = build_profile_url(str(domain or ""), str(username) if username else None)
            if url:
                acct["profile_url"] = url
                acct["url"] = url
        out.append(row)
    return out
