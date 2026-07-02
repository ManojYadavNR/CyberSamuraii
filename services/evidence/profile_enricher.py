"""Parallel deep enrichment for every verified discovered account — no platform priority."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from schemas.fusion import Entity
from services.correlation.handle_quality import is_correlatable_handle, normalize_profile_handle
from services.discovery.attribution import account_handle_matches_seed, url_references_seed
from services.account_confirmation import account_confirmed
from services.evidence.maigret_parser import parse_maigret_payload
from services.evidence.platform_deep import _merge_payload, deep_fetch_profile, is_enrichable_profile_url
from services.google_dorking.filters import is_junk_dork_url

ENRICH_TIMEOUT = 22.0
MAX_CONCURRENT = 24

# Strip person-level intel copied from unrelated deep scrapes.
_PERSON_INTEL_KEYS = frozenset({
    "achievements", "schools", "highlights", "social_posts", "recent_posts",
})


def _profile_url(entity: Entity) -> str | None:
    meta = entity.metadata or {}
    url = meta.get("url") or entity.value
    if not url:
        return None
    u = str(url)
    return u if "://" in u else f"https://{u}"


def _entity_handle(entity: Entity, url: str) -> str:
    meta = entity.metadata or {}
    platform = str(meta.get("platform") or "")
    return normalize_profile_handle(url, platform, meta)


def _sanitize_enrichment_payload(payload: dict[str, Any], url: str, *, seed_query: str = "") -> dict[str, Any]:
    """Drop global SERP bleed unless this scrape was an expansion anchor."""
    if payload.get("expansion_anchor") or payload.get("confirmed_anchor_type"):
        return payload
    cleaned = dict(payload)
    for key in _PERSON_INTEL_KEYS:
        cleaned.pop(key, None)
    return cleaned


def _entity_matches_seed(entity: Entity, url: str, seed_query: str) -> bool:
    if not seed_query:
        return True
    seed = seed_query.strip()
    meta = entity.metadata or {}
    if "@" in seed:
        seed_email = seed.lower()
        entity_email = str(meta.get("email") or "").lower()
        if entity_email == seed_email:
            return True
        if meta.get("registered") and entity_email == seed_email:
            return True
        if meta.get("url") or meta.get("profile_url"):
            if meta.get("username") or meta.get("linked_from_gravatar"):
                return True
            if url and not url.rstrip("/").endswith(seed_email):
                return True
    if url_references_seed(url, seed_query):
        return True
    handle = _entity_handle(entity, url)
    if handle and account_handle_matches_seed(handle, seed_query, url):
        return True
    meta = entity.metadata or {}
    for key in ("username", "handle"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip() and account_handle_matches_seed(val.strip(), seed_query, url):
            return True
    if ":" in entity.value and not entity.value.startswith("http"):
        part = entity.value.split(":", 1)[1].strip()
        if part and account_handle_matches_seed(part, seed_query, url):
            return True
    return False


def _tool_bootstrap_payload(entity: Entity) -> dict[str, Any]:
    """Seed deep scrape with data already returned by Maigret/Social Analyzer."""
    meta = dict(entity.metadata or {})
    out: dict[str, Any] = dict(parse_maigret_payload(meta))
    skip_keys = _PERSON_INTEL_KEYS if not meta.get("correlation_intel_merged") else frozenset()
    for key in (
        "display_name", "bio", "location", "website", "email", "avatar_url",
        "username", "handle", "organization", "organizations", "aliases",
        "recent_posts", "highlights", "projects", "schools", "emails", "videos",
        "media_video", "profile_images", "post_images", "public_metadata", "visual_assets",
    ):
        if key in skip_keys:
            continue
        val = meta.get(key)
        if val is not None and val != "" and key not in out:
            out[key] = val
    return out


def _is_verified_for_enrichment(entity: Entity, *, seed_query: str = "") -> bool:
    meta = entity.metadata or {}
    if meta.get("investigation_lead") or meta.get("status") == "rate_limited":
        return False
    if meta.get("check_type") == "dataset_lookup" and not meta.get("verified"):
        return False
    if not account_confirmed(meta, set(entity.sources)):
        return False
    if seed_query and "@" not in seed_query.strip():
        url = _profile_url(entity) or ""
        platform = str(meta.get("platform") or "")
        handle = normalize_profile_handle(url or entity.value, platform, meta)
        if handle and not is_correlatable_handle(handle, seed_query, url or None):
            return False
    return True


def collect_enrichment_targets(entities: list[Entity], *, seed_query: str = "") -> list[tuple[str, str, float]]:
    """(url, entity_id, priority) — equal treatment for all verified platforms."""
    seen: set[str] = set()
    out: list[tuple[str, str, float]] = []

    def add(url: str, entity_id: str, entity: Entity) -> None:
        u = url.strip()
        if not u.startswith("http") or u in seen or is_junk_dork_url(u):
            return
        if not is_enrichable_profile_url(u):
            return
        if seed_query and not _entity_matches_seed(entity, u, seed_query):
            return
        seen.add(u)
        out.append((u, entity_id, 1.0))

    for entity in entities:
        if entity.type == "account" and _is_verified_for_enrichment(entity, seed_query=seed_query):
            url = _profile_url(entity)
            if not url:
                continue
            if seed_query and not _entity_matches_seed(entity, url, seed_query):
                continue
            add(url, entity.entity_id, entity)

        if entity.type == "document":
            meta = entity.metadata or {}
            if meta.get("check_type") != "google_dork":
                continue
            url = str(meta.get("url") or entity.value)
            if seed_query and url_references_seed(url, seed_query):
                add(url, entity.entity_id, entity)

    return out


async def enrich_account_profiles(
    entities: list[Entity],
    *,
    seed_query: str = "",
) -> dict[str, dict[str, Any]]:
    """Deep-fetch all verified seed-matching profiles in parallel."""
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    results: dict[str, dict[str, Any]] = {}
    entity_by_id = {e.entity_id: e for e in entities}
    targets = collect_enrichment_targets(entities, seed_query=seed_query)

    async def enrich_one(url: str, entity_id: str) -> None:
        entity = entity_by_id.get(entity_id)
        if not entity:
            return
        handle = _entity_handle(entity, url)
        async with sem:
            try:
                payload = await asyncio.wait_for(
                    deep_fetch_profile(url, expected_handle=handle or None, seed_query=seed_query),
                    timeout=ENRICH_TIMEOUT,
                )
                bootstrap = _tool_bootstrap_payload(entity)
                payload = _merge_payload(bootstrap, payload or {})
                payload = _sanitize_enrichment_payload(payload, url, seed_query=seed_query)
                if payload:
                    payload["url"] = url
                    domain = normalize_domain(url) or urlparse(url).netloc
                    payload.setdefault("platform", domain)
                    payload["enrichment_source"] = payload.get("enrichment_source") or f"{domain}_parallel"
                    results[entity_id] = payload
            except (asyncio.TimeoutError, Exception):
                return

    await asyncio.gather(*(enrich_one(url, eid) for url, eid, _ in targets))
    await _bootstrap_missing_avatars(entities, results, seed_query=seed_query)
    return results


async def _bootstrap_missing_avatars(
    entities: list[Entity],
    results: dict[str, dict[str, Any]],
    *,
    seed_query: str = "",
) -> None:
    """Lightweight og:image fetch for verified profiles still missing a photo."""
    from services.discovery.validators import is_plausible_profile_photo
    from services.evidence.platform_deep import _fetch_og_thumbnail

    sem = asyncio.Semaphore(12)

    async def _one(entity: Entity) -> None:
        if not _is_verified_for_enrichment(entity, seed_query=seed_query):
            return
        merged = {**(entity.metadata or {}), **results.get(entity.entity_id, {})}
        existing = merged.get("avatar_url") or merged.get("profile_image")
        if isinstance(existing, str) and existing.startswith("http"):
            return
        url = _profile_url(entity)
        if not url or not is_enrichable_profile_url(url):
            return
        if seed_query and not _entity_matches_seed(entity, url, seed_query):
            return
        async with sem:
            try:
                og = await asyncio.wait_for(_fetch_og_thumbnail(url), timeout=10.0)
            except Exception:
                return
        if not og or not is_plausible_profile_photo(og):
            return
        payload = dict(results.get(entity.entity_id) or {})
        payload["avatar_url"] = og
        payload["url"] = url
        payload.setdefault("platform", normalize_domain(url) or urlparse(url).netloc)
        payload["enrichment_source"] = payload.get("enrichment_source") or "og_image_bootstrap"
        results[entity.entity_id] = payload

    await asyncio.gather(*[_one(e) for e in entities if e.type == "account"], return_exceptions=True)
