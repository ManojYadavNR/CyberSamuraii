"""Live HTTP checks — reject username hits that resolve to login walls or error pages."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import httpx

from schemas.fusion import Entity, FusionOutput
from services.account_confirmation import account_confirmed, should_skip_http_reverify
from services.discovery.validators import (
    DEFINITIVE_VERIFY_FAILURES,
    is_displayable_media_url,
    is_junk_profile_url,
    is_parking_page_html,
    is_service_error_html,
    normalize_domain,
    verify_outcome_confirmed,
)
from services.fusion_engine import apply_account_corroboration, fusion_engine


async def refine_username_fusion(fusion: FusionOutput, *, seed_query: str = "") -> FusionOutput:
    """Re-check account URLs then re-apply corroboration and scoring."""
    entities = list(fusion.deduplicated_entities or [])
    entities = await verify_account_entities(entities, seed_query=seed_query)
    entities = apply_account_corroboration(entities, seed_query=seed_query)
    entities = fusion_engine.rescore_entities(entities)
    evidence_map = fusion_engine.build_evidence_map(entities)
    global_score = fusion_engine.compute_global_fusion_score(entities)
    return fusion.model_copy(
        update={
            "deduplicated_entities": entities,
            "evidence_map": evidence_map,
            "fusion_score": global_score,
        }
    )

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
VERIFY_TIMEOUT = 10.0
MAX_CONCURRENT = 20

GENERIC_UNAVAILABLE_MARKERS = (
    "page not found",
    "404 not found",
    "account not found",
    "user not found",
    "profile not found",
    "doesn't exist",
    "does not exist",
    "no user exists",
    "this account has been suspended",
    "account suspended",
    "do not provide services in your area",
    "not provide services in your area",
    "content isn't available",
    "this content isn't available",
    "this page isn't available",
    "page isn't available",
    "no longer available",
    "the link you followed may be broken",
    "sorry, this page isn't available",
    "this page doesn't exist",
    "couldn't find this account",
    "this account doesn't exist",
    "specified member cannot be found",
    "member cannot be found",
    "something went wrong",
    "forum temporarily",
    "форум временно отключ",
)

LOGIN_WALL_MARKERS = (
    "login_form",
    "log in to continue",
    "sign in to continue",
    "you must log in",
    "log into",
    "create new account",
    "join to view",
)


def _profile_url(entity: Entity) -> str | None:
    meta = entity.metadata or {}
    url = meta.get("url") or entity.value
    if not url:
        return None
    u = str(url).strip()
    return u if "://" in u else f"https://{u}"


def is_profile_page_available(html: str, url: str, *, status_code: int = 200) -> tuple[bool, str]:
    """Return (available, reason)."""
    if is_junk_profile_url(url):
        return False, "junk_profile_url"
    if status_code >= 400:
        return False, f"http_{status_code}"

    low = (html or "").lower()
    if is_service_error_html(html):
        return False, "service_error_page"
    if is_parking_page_html(html):
        return False, "parking_page"
    host = normalize_domain(url) or (urlparse(url).netloc or "").lower().replace("www.", "")

    for marker in GENERIC_UNAVAILABLE_MARKERS:
        if marker in low:
            return False, "not_found"

    login_hits = sum(1 for m in LOGIN_WALL_MARKERS if m in low)
    if login_hits >= 2 or ("login" in low and "password" in low):
        return False, "login_wall"
    if 'id="splash-screen"' in low:
        return False, "login_wall"
    og_profile = re.search(
        r'property=["\']og:type["\']\s+content=["\']profile["\']',
        html or "",
        flags=re.IGNORECASE,
    )
    og_url = re.search(r'property=["\']og:url["\']\s+content=["\']([^"\']+)["\']', html or "", flags=re.IGNORECASE)
    if login_hits >= 1 and not og_profile:
        vanity = re.search(r'"(?:userVanity|username|screen_name)"\s*:\s*"([^"]+)"', html or "")
        if not vanity and (not og_url or og_url.group(1).rstrip("/").count("/") <= 3):
            return False, "login_wall"

    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html or "", flags=re.IGNORECASE)
    if title_match:
        title = title_match.group(1).lower()
        if any(m in title for m in ("page not found", "not found", "error", "unavailable")):
            return False, "error_title"

    if len(low.strip()) < 200 and login_hits >= 1 and not og_profile:
        return False, "empty_response"

    return True, "ok"


async def _verify_one(
    client: httpx.AsyncClient,
    url: str,
    *,
    seed_query: str = "",
) -> tuple[bool | None, str, bool | None]:
    url = re.sub(r"\x1b\[[0-9;]*m", "", url).strip()
    if not url.startswith(("http://", "https://")):
        return None, "invalid_url", None
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        return None, f"fetch_error:{type(exc).__name__}", None

    ok, reason = is_profile_page_available(response.text, str(response.url), status_code=response.status_code)
    content_seed: bool | None = None
    if ok and seed_query and reason != "login_wall":
        from services.discovery.attribution import context_references_seed, url_references_seed

        if context_references_seed(response.text[:80000], seed_query=seed_query):
            content_seed = True
        elif url_references_seed(str(response.url), seed_query):
            # URL path contains handle — existence check only, not identity proof.
            content_seed = False
        else:
            ok = False
            reason = "no_seed_reference"
            content_seed = False
    return verify_outcome_confirmed(ok, reason), reason, content_seed


async def verify_account_entities(entities: list[Entity], *, seed_query: str = "") -> list[Entity]:
    """HTTP-check account URLs; stamp live_profile_verified on metadata."""
    from services.correlation.handle_quality import is_correlatable_handle, normalize_profile_handle

    account_urls: list[tuple[int, str]] = []
    junk_indices: set[int] = set()
    results: dict[int, tuple[bool | None, str, bool | None]] = {}

    for idx, entity in enumerate(entities):
        if entity.type != "account":
            continue
        url = _profile_url(entity)
        if not url:
            continue
        if is_junk_profile_url(url):
            junk_indices.add(idx)
            continue
        meta = entity.metadata or {}
        if should_skip_http_reverify(meta):
            reason = str(meta.get("live_verify_reason") or meta.get("status") or "tool_live_scan")
            seed_ok = meta.get("status") in {"maigret_claimed", "registered"}
            results[idx] = (True, reason, True if seed_ok else None)
            continue
        account_urls.append((idx, url))

    for idx in junk_indices:
        results[idx] = (False, "junk_profile_url", False)
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    if account_urls:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=VERIFY_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            async def check(idx: int, url: str) -> None:
                async with sem:
                    results[idx] = await _verify_one(client, url, seed_query=seed_query)

            await asyncio.gather(*(check(idx, url) for idx, url in account_urls))

    out: list[Entity] = []
    for idx, entity in enumerate(entities):
        if idx not in results:
            out.append(entity)
            continue
        available, reason, content_seed = results[idx]
        meta = dict(entity.metadata or {})
        meta["live_verify_reason"] = reason
        if content_seed is not None:
            meta["content_seed_verified"] = content_seed
        if available is True and seed_query and "@" not in seed_query.strip():
            platform = str(meta.get("platform") or "")
            handle = normalize_profile_handle(url if (url := str(meta.get("url") or entity.value)) else entity.value, platform, meta)
            if handle and not is_correlatable_handle(handle, seed_query, url if url.startswith("http") else None):
                available = False
                reason = "handle_mismatch"
                meta["live_verify_reason"] = reason
        if available is True:
            meta["live_profile_verified"] = True
        elif available is False:
            meta["live_profile_verified"] = False
            if reason in DEFINITIVE_VERIFY_FAILURES or reason.startswith("http_404") or reason == "handle_mismatch":
                meta["verified"] = False
                meta["status"] = "unavailable"
                meta["corroboration_status"] = "unavailable"
        else:
            meta["live_profile_verified"] = None
            if reason == "login_wall":
                meta["status"] = "login_walled"
        out.append(entity.model_copy(update={"metadata": meta}))
    return out
