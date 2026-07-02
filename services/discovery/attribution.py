"""Link contacts (email/phone) to the seed — blocks cross-person contamination."""

from __future__ import annotations

import re
from typing import Any

from services.discovery.validators import is_email, is_phone, is_plausible_phone
from services.username import normalize_username

PHONE_RE = re.compile(r"\+?[\d][\d\s\-().]{6,18}[\d]")


def split_handle_to_display_name(handle: str) -> str | None:
    """Turn a CamelCase handle into a spaced display name for name-based web search."""
    raw = handle.strip()
    if not raw or "@" in raw or re.search(r"\s", raw):
        return raw or None
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    parts = [p for p in spaced.split() if p]
    if len(parts) < 2:
        return None
    return " ".join(parts)


def person_name_variants(seed_query: str) -> set[str]:
    """Display-name forms derived from a username handle (e.g. JohnDoe42 → John Doe 42)."""
    variants: set[str] = set()
    for part in seed_query.split("|"):
        part = part.strip()
        if not part or "@" in part:
            continue
        name = split_handle_to_display_name(part)
        if not name:
            continue
        variants.add(name)
        variants.add(name.lower())
        variants.add(re.sub(r"\s+", " ", name).strip())
    return {v for v in variants if len(v) >= 4}


def seed_handle_variants(seed_query: str) -> set[str]:
    """Normalized handle tokens used for URL/snippet matching."""
    original = seed_query.strip()
    parts = [p.strip() for p in original.split("|") if p.strip() and "@" not in p]
    if not parts:
        parts = [original] if original and "@" not in original else [p for p in original.split("|") if p.strip()]
    variants: set[str] = set()
    for part in parts or [original]:
        norm, _ = normalize_username(part)
        if norm:
            variants.add(norm)
        compact = re.sub(r"[^\w]", "", part.lower())
        if compact:
            variants.add(compact)
        if part:
            variants.add(part.lower())
    return {v for v in variants if len(v) >= 2}


def url_references_seed(url: str, seed_query: str) -> bool:
    if not url or not seed_query.strip():
        return False
    from services.google_dorking.filters import handle_from_profile_url

    handle = handle_from_profile_url(url)
    if handle:
        h, _ = normalize_username(handle)
        seed_norm, _ = normalize_username(seed_query)
        if h and (h == seed_norm or h in seed_handle_variants(seed_query)):
            return True

    blob = url.lower().replace("-", "").replace("_", "")
    for variant in seed_handle_variants(seed_query):
        compact = variant.replace("-", "").replace("_", "")
        if len(compact) < 4:
            continue
        if re.search(rf"(?:^|[/.@]){re.escape(compact)}(?:[/.@]|$)", blob):
            return True
        if len(compact) >= 8 and compact in blob:
            return True
    return False


def is_garbage_serp_bundle(title: str, snippet: str = "") -> bool:
    """Reject DDG-style titles that concatenate unrelated results from multiple sites."""
    title = title or ""
    if len(title) < 120:
        return False
    low = title.lower()
    domain_tokens = re.findall(r"\b(?:\w+\.){1,2}(?:com|org|net|io|co)\b", low)
    if len(set(domain_tokens)) >= 2:
        return True
    compact = low.replace(" ", "")
    if re.search(r"\w+(?:com|org)\w+(?:com|org)", compact):
        return True
    return False


def profile_handle_conflicts_seed(url: str, seed_query: str) -> bool:
    """True when URL is a social profile belonging to a clearly different handle."""
    if not url or not seed_query.strip():
        return False
    from urllib.parse import urlparse

    from services.google_dorking.filters import handle_from_profile_url, is_social_post_url
    from services.platform_registry import PROFILE_PATH_SKIP, is_priority_social_host, normalize_platform_host

    if url_references_seed(url, seed_query):
        return False
    if is_social_post_url(url):
        return False

    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = normalize_platform_host(parsed.netloc)
    path = parsed.path.strip("/")
    segments = [s for s in path.split("/") if s]
    if not segments:
        return False

    handle = handle_from_profile_url(url)
    if not handle or account_handle_matches_seed(handle, seed_query, url):
        return False

    if is_priority_social_host(host) and len(segments) == 1:
        if segments[0].lower() in PROFILE_PATH_SKIP:
            return False
        return True
    if path.startswith("@") and len(segments) == 1:
        return True
    return False


def context_references_seed(*parts: str | None, seed_query: str) -> bool:
    """True when text contains the seed handle or derived display name."""
    blob = " ".join(p for p in parts if p).lower()
    if not blob:
        return False
    blob_compact = re.sub(r"[^\w]", "", blob)
    for variant in seed_handle_variants(seed_query):
        compact_variant = variant.replace("-", "").replace("_", "")
        if variant in blob:
            return True
        if len(compact_variant) >= 5 and compact_variant in blob_compact:
            return True
    for name in person_name_variants(seed_query):
        if name.lower() in blob:
            return True
        name_compact = re.sub(r"[^\w]", "", name.lower())
        if len(name_compact) >= 6 and name_compact in blob_compact:
            return True
    return False


_NUMERIC_FB_PHOTO_RE = re.compile(r"/photos/(?:a\.\d+/\d+|\d+)/?$", re.I)
_NUMERIC_FB_POST_RE = re.compile(r"/posts/\d+/?$", re.I)
_OPAQUE_SOCIAL_POST_RE = re.compile(
    r"/(?:p|reel|reels|stories|tv)/[a-z0-9_-]{5,}/?$",
    re.I,
)


def _path_slug_compact(url: str) -> str:
    from urllib.parse import urlparse

    try:
        path = urlparse(url if "://" in url else f"https://{url}").path.lower()
    except Exception:
        return ""
    return re.sub(r"[^\w]", "", path)


def social_post_url_references_seed(url: str, seed_query: str) -> bool | None:
    """
    For social posts with human-readable URL slugs, require the seed in the path.
    Returns None when the URL is opaque (numeric photo IDs, Instagram p-codes) so
    snippet/title attribution may still apply.
    """
    from services.google_dorking.filters import is_social_post_url

    if not is_social_post_url(url):
        return None

    path = (url or "").lower()
    if (
        _NUMERIC_FB_PHOTO_RE.search(path)
        or _NUMERIC_FB_POST_RE.search(path)
        or _OPAQUE_SOCIAL_POST_RE.search(path)
    ):
        return None

    slug = _path_slug_compact(url)
    if len(slug) < 12:
        return None

    for variant in seed_handle_variants(seed_query):
        compact = re.sub(r"[^\w]", "", variant.lower())
        if len(compact) >= 4 and compact in slug:
            return True
    for name in person_name_variants(seed_query):
        name_compact = re.sub(r"[^\w]", "", name.lower())
        if len(name_compact) >= 6 and name_compact in slug:
            return True

    if re.search(r"congratulations-to-|/posts/[^/]+|/photos/[^/]+", path):
        return False
    return None


def dork_hit_attributed(
    *,
    url: str,
    title: str = "",
    snippet: str = "",
    seed_query: str,
    dork_query: str = "",
    dork_category: str = "",
) -> bool:
    """Hit belongs to seed when handle is in URL path or seed appears in title/snippet."""
    from services.google_dorking.filters import handle_from_profile_url, is_junk_dork_url, is_social_post_url
    from services.platform_registry import is_priority_social_host

    if is_junk_dork_url(url):
        return False
    if is_garbage_serp_bundle(title, snippet):
        return False
    if profile_handle_conflicts_seed(url, seed_query):
        return False

    if is_social_post_url(url):
        slug_check = social_post_url_references_seed(url, seed_query)
        if slug_check is False:
            return False
        if slug_check is True:
            return True
        if context_references_seed(title, snippet, seed_query=seed_query):
            return True
        if url_references_seed(url, seed_query):
            return True
        return False

    if context_references_seed(title, snippet, seed_query=seed_query):
        return True
    if url_references_seed(url, seed_query):
        return True
    if is_priority_social_host(url) and is_social_post_url(url):
        return context_references_seed(title, snippet, seed_query=seed_query)
    handle = handle_from_profile_url(url)
    if handle and account_handle_matches_seed(handle, seed_query, url):
        return True
    return False


def email_local_matches_seed(email: str, seed_query: str) -> bool:
    if not is_email(email):
        return False
    local = email.split("@", 1)[0].lower()
    seed_norm, _ = normalize_username(seed_query)
    if not seed_norm:
        return False
    seed_lower = seed_norm.lower()
    if local == seed_lower:
        return True
    # Reject partial overlaps (e.g. manojyadav vs manojyadavnr, manojy5951 vs manojyadavnr).
    shorter, longer = (local, seed_lower) if len(local) <= len(seed_lower) else (seed_lower, local)
    if shorter in longer and len(shorter) >= max(8, int(len(longer) * 0.88)):
        return True
    return False


def email_attributed_to_username(
    email: str,
    seed_query: str,
    *,
    source_url: str | None = None,
    title: str = "",
    snippet: str = "",
) -> bool:
    """Email belongs to the seed user when found on their page or local-part matches handle."""
    if not is_email(email):
        return False

    on_seed_page = bool(source_url and url_references_seed(source_url, seed_query))
    in_seed_context = context_references_seed(title, snippet, seed_query=seed_query)
    if not on_seed_page and not in_seed_context:
        return False

    if email_local_matches_seed(email, seed_query):
        return True
    return False


def phone_attributed_to_username(
    phone: str,
    seed_query: str,
    *,
    source_url: str | None = None,
    title: str = "",
    snippet: str = "",
) -> bool:
    if not is_phone(phone):
        return False
    if source_url and url_references_seed(source_url, seed_query):
        return True
    return context_references_seed(title, snippet, phone, seed_query=seed_query)


def extract_phones_from_text(text: str) -> list[str]:
    found = PHONE_RE.findall(text or "")
    out: list[str] = []
    seen: set[str] = set()
    for raw in found:
        candidate = raw.strip()
        if not is_plausible_phone(candidate):
            continue
        digits = re.sub(r"[^\d+]", "", candidate)
        if digits not in seen:
            seen.add(digits)
            out.append(candidate)
    return out


def account_handle_matches_seed(handle: str, seed_query: str, profile_url: str | None = None) -> bool:
    """True when platform account handle or URL matches the investigated username."""
    seed_norm, _ = normalize_username(seed_query)
    if not seed_norm:
        return False
    if handle:
        h, _ = normalize_username(handle)
        if h and (h == seed_norm or h in seed_handle_variants(seed_query)):
            return True
    if profile_url and url_references_seed(profile_url, seed_query):
        return True
    return False


def is_image_seed_query(seed_query: str) -> bool:
    """True when investigation started from an uploaded image or image URL."""
    if not seed_query.strip():
        return False
    from services.image_intelligence.path_utils import is_local_path
    from services.query_detector import detect_query_type

    if is_local_path(seed_query):
        return True
    return detect_query_type(seed_query) == "image"


def entity_image_attributed(meta: dict[str, Any] | None) -> bool:
    """Entity discovered from image analysis or reverse image search."""
    if not meta:
        return False
    if meta.get("image_attributed") or meta.get("reverse_image_match"):
        return True
    if meta.get("intel_engine") == "image_intelligence" and meta.get("field") in (
        "emails", "phones", "usernames", "urls",
    ):
        return True
    if meta.get("intel_group") == "reverse_image_search":
        return True
    return False


def email_linked_to_seed(
    email: str,
    seed_query: str,
    *,
    profile_url: str | None = None,
    username_attributed: bool = False,
    handle: str | None = None,
    entity_meta: dict[str, Any] | None = None,
) -> bool:
    """Whether an email should trigger holehe / appear on the identity profile."""
    if username_attributed:
        return email_local_matches_seed(email, seed_query)
    meta = entity_meta or {}
    if entity_image_attributed(meta) and is_email(email):
        return True
    if is_image_seed_query(seed_query) and meta.get("field") == "emails":
        return is_email(email)
    if handle and account_handle_matches_seed(handle, seed_query, profile_url):
        return is_email(email)
    if email_attributed_to_username(email, seed_query, source_url=profile_url):
        return True
    if profile_url and url_references_seed(profile_url, seed_query):
        return email_local_matches_seed(email, seed_query) or account_handle_matches_seed(handle or "", seed_query, profile_url)
    return email_local_matches_seed(email, seed_query)
