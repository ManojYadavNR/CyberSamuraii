"""Handle quality gates for identity correlation."""

from __future__ import annotations

from services.discovery.attribution import account_handle_matches_seed
from services.discovery.validators import GENERIC_PATH_SEGMENTS, is_plausible_handle

GENERIC_HANDLES = GENERIC_PATH_SEGMENTS | frozenset({
    "open", "home", "index", "search", "settings", "account", "accounts", "me",
    "photos", "photo", "gallery", "album", "albums", "view", "show", "lover",
})


def normalize_profile_handle(value: str, platform: str, meta: dict) -> str:
    """Extract a meaningful handle, skipping generic URL path segments."""
    from urllib.parse import parse_qs, urlparse

    url = value if "://" in value else str(meta.get("url") or "")
    if url and "://" not in url:
        url = f"https://{url}"

    if url:
        parsed = urlparse(url)
        segments = [s for s in parsed.path.strip("/").split("/") if s]
        while segments and segments[0].lower().lstrip("@") in GENERIC_HANDLES:
            segments.pop(0)
        if segments:
            path_handle = segments[-1].lower().lstrip("@~")
            if is_plausible_handle_for_correlation(path_handle):
                return path_handle

        qs = parse_qs(parsed.query)
        for key in ("username", "user", "u", "id"):
            values = qs.get(key) or []
            if values:
                candidate = values[0].strip().lower().lstrip("@~")
                if is_plausible_handle_for_correlation(candidate):
                    return candidate

    for key in ("username", "handle"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            h = val.strip().lower().lstrip("@~")
            if is_plausible_handle_for_correlation(h):
                return h

    if ":" in value and not value.startswith("http"):
        part = value.split(":", 1)[1].lower().strip().lstrip("@~")
        if is_plausible_handle_for_correlation(part):
            return part

    if "/" in value and "://" not in value:
        tail = value.rsplit("/", 1)[-1].lower().lstrip("@~")
        if is_plausible_handle_for_correlation(tail):
            return tail

    return ""


def is_plausible_handle_for_correlation(handle: str) -> bool:
    """Basic junk-handle rejection without seed alignment."""
    h = (handle or "").strip().lower()
    if not h:
        return False
    from services.discovery.validators import is_email
    if "@" in h and is_email(h):
        return True
    if h in GENERIC_HANDLES:
        return False
    if not is_plausible_handle(h):
        return False
    if len(h) < 4 and not any(c.isdigit() for c in h):
        return False
    return True


def is_correlatable_handle(handle: str, seed_query: str = "", profile_url: str | None = None) -> bool:
    """Reject junk URL fragments; require seed alignment for username investigations."""
    h = (handle or "").strip().lower()
    if not is_plausible_handle_for_correlation(h):
        return False
    seed = (seed_query or "").strip()
    if not seed:
        return True
    if "|" in seed:
        from services.multi_input import attribution_seed_from_raw

        seed = attribution_seed_from_raw(seed)
    if "@" in seed:
        seed_low = seed.lower()
        if h == seed_low or ("@" in h and h == seed_low):
            return True
        local = seed.split("@", 1)[0].lower()
        if h == local or account_handle_matches_seed(h, local, profile_url):
            return True
        from services.discovery.attribution import email_local_matches_seed

        return email_local_matches_seed(seed, h)
    return account_handle_matches_seed(h, seed, profile_url)
