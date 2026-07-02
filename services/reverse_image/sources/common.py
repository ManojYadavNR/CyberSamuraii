"""Shared helpers for ddgs-based reverse image sources."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from schemas.reverse_image import ReverseImageMatch
from services.reverse_image.extractors import extract_organizations, extract_platform, extract_profile_urls
from services.reverse_image.filters import confidence_from_hash, is_junk_url, is_real_profile_url
from services.reverse_image.matcher import classify_match_type


async def ddgs_text_search(dork: str, *, num: int = 8) -> list[dict[str, Any]]:
    from services.google_dorking.ddgs_client import search_ddgs_web

    return await search_ddgs_web(dork, num=num)


async def ddgs_image_search(query: str, *, num: int = 8) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        try:
            from ddgs import DDGS
        except ImportError:
            return []
        items: list[dict[str, Any]] = []
        try:
            for hit in DDGS().images(query, max_results=max(1, min(num, 12))):
                if not isinstance(hit, dict):
                    continue
                url = str(hit.get("image") or hit.get("url") or hit.get("thumbnail") or "").strip()
                if not url or is_junk_url(url):
                    continue
                items.append({
                    "title": str(hit.get("title") or ""),
                    "url": url,
                    "page_url": str(hit.get("url") or hit.get("source") or ""),
                    "snippet": str(hit.get("source") or ""),
                    "display_link": urlparse(url).netloc.replace("www.", ""),
                    "dork_query": query,
                })
        except Exception:
            return []
        return items

    return await asyncio.to_thread(_run)


async def _verify_hit_hash(seed_path: str, url: str) -> float:
    from services.reverse_image.filters import verify_match_hash

    return await verify_match_hash(seed_path, url)


def hits_to_matches(
    hits: list[dict[str, Any]],
    *,
    source: str,
    seed_image: str,
    seed_url: str | None,
    hash_similarity: float = 0.0,
    verified_hashes: dict[str, float] | None = None,
) -> list[ReverseImageMatch]:
    matches: list[ReverseImageMatch] = []
    verified_hashes = verified_hashes or {}

    for hit in hits:
        url = str(hit.get("url") or hit.get("page_url") or "").strip()
        if not url or is_junk_url(url):
            continue
        page_url = str(hit.get("page_url") or url)
        if is_junk_url(page_url):
            continue

        title = str(hit.get("title") or "")
        snippet = str(hit.get("snippet") or "")
        platform = extract_platform(url) or str(hit.get("display_link") or "")
        profiles = [u for u in extract_profile_urls(url, title, snippet) if is_real_profile_url(u)]

        hit_hash = verified_hashes.get(url) or verified_hashes.get(page_url) or hash_similarity
        orgs = extract_organizations(f"{title} {snippet}") if hit_hash >= 0.8 else []

        match_type = classify_match_type(
            url_a=seed_url or seed_image,
            url_b=url,
            hash_similarity=hit_hash,
            title=title,
            snippet=snippet,
            platform=platform,
        )

        if hit_hash >= 0.72:
            confidence = confidence_from_hash(hit_hash)
        elif profiles:
            confidence = 0.55
        else:
            confidence = 0.0

        if confidence < 0.55:
            continue

        matches.append(ReverseImageMatch(
            match_id=str(uuid4()),
            source=source,
            match_type=match_type,
            match_url=url,
            page_url=page_url,
            title=title or None,
            snippet=snippet or None,
            platform=platform or None,
            confidence=round(min(confidence, 0.95), 4),
            evidence_path=[seed_image, source, url],
            provenance={
                "dork_query": hit.get("dork_query"),
                "hash_similarity": hit_hash,
                "hash_verified": hit_hash >= 0.72,
            },
            profile_urls=profiles,
            organizations=orgs,
        ))
    return matches


async def browser_hits_to_matches(
    hits: list[dict[str, Any]],
    *,
    source: str,
    seed_image: str,
    seed_url: str | None,
    max_verify: int = 15,
) -> list[ReverseImageMatch]:
    """Score browser reverse-search hits — keep visual candidates even when below identity threshold."""
    verified: dict[str, float] = {}
    image_urls: list[str] = []
    for hit in hits:
        u = str(hit.get("url") or "").strip()
        if u.startswith(("http://", "https://")):
            image_urls.append(u)

    unique_urls = list(dict.fromkeys(image_urls))[:max_verify]
    if unique_urls:
        scores = await asyncio.gather(*[_verify_hit_hash(seed_image, u) for u in unique_urls])
        verified = dict(zip(unique_urls, scores))

    matches: list[ReverseImageMatch] = []
    for hit in hits:
        url = str(hit.get("url") or "").strip()
        if not url or is_junk_url(url):
            continue
        page_url = str(hit.get("page_url") or url)
        if is_junk_url(page_url):
            continue
        title = str(hit.get("title") or "")
        snippet = str(hit.get("snippet") or "")
        platform = extract_platform(page_url) or extract_platform(url) or ""
        profiles = [u for u in extract_profile_urls(page_url, title, snippet) if is_real_profile_url(u)]
        hit_hash = verified.get(url, 0.0)
        if hit_hash < 0.48 and not profiles:
            continue
        confidence = confidence_from_hash(hit_hash) if hit_hash >= 0.72 else round(0.50 + hit_hash * 0.25, 4)
        if profiles:
            confidence = max(confidence, 0.62)
        matches.append(ReverseImageMatch(
            match_id=str(uuid4()),
            source=source,
            match_type=classify_match_type(
                url_a=seed_url or seed_image,
                url_b=url,
                hash_similarity=hit_hash,
                title=title,
                snippet=snippet,
                platform=platform,
            ),
            match_url=url,
            page_url=page_url,
            title=title or None,
            snippet=snippet or None,
            platform=platform or None,
            confidence=round(min(confidence, 0.88), 4),
            evidence_path=[source, url],
            provenance={
                "hash_similarity": hit_hash,
                "hash_verified": hit_hash >= 0.72,
                "browser_reverse": True,
            },
            profile_urls=profiles,
            organizations=[],
        ))
    return matches


async def hits_to_matches_verified(
    hits: list[dict[str, Any]],
    *,
    source: str,
    seed_image: str,
    seed_url: str | None,
) -> list[ReverseImageMatch]:
    """Pre-verify image hits against seed perceptual hash before scoring."""
    verified: dict[str, float] = {}
    image_urls: list[str] = []
    for hit in hits:
        for key in ("url", "page_url"):
            u = str(hit.get(key) or "").strip()
            if u.startswith(("http://", "https://")) and u.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
            ):
                image_urls.append(u)

    unique_urls = list(dict.fromkeys(image_urls))[:12]
    if unique_urls:
        scores = await asyncio.gather(*[_verify_hit_hash(seed_image, u) for u in unique_urls])
        verified = dict(zip(unique_urls, scores))

    return hits_to_matches(
        hits,
        source=source,
        seed_image=seed_image,
        seed_url=seed_url,
        verified_hashes=verified,
    )
