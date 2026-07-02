"""Attach page previews (og:image or screenshot) to Google dork / web document hits."""

from __future__ import annotations

import asyncio
import re

from schemas.fusion import Entity
from services.google_dorking.filters import dork_hit_displayable, is_social_post_url
from services.page_preview import resolve_page_visual

MAX_DORK_PREVIEWS = 36

HACKATHON_SOCIAL_RE = re.compile(
    r"hackathon|winner|won|award|fest|college|university|instagram|facebook",
    re.I,
)


def _page_url(entity: Entity) -> str | None:
    meta = entity.metadata or {}
    url = str(meta.get("url") or entity.value or "")
    return url if url.startswith("http") else None


def _needs_preview(entity: Entity, seed_query: str = "") -> bool:
    meta = entity.metadata or {}
    if meta.get("page_screenshot_url") or meta.get("preview_image_url"):
        return False
    if meta.get("check_type") != "google_dork" and entity.type != "document":
        return False
    url = _page_url(entity)
    if not url:
        return False
    category = str(meta.get("dork_category") or "")
    if category in ("media_images", "media_lens"):
        return False
    if seed_query and not dork_hit_displayable(
        url=url,
        title=str(meta.get("title") or ""),
        snippet=str(meta.get("snippet") or meta.get("content") or ""),
        seed_query=seed_query,
        dork_category=category,
    ):
        return False
    return True


def _preview_priority(entity: Entity) -> float:
    meta = entity.metadata or {}
    url = str(meta.get("url") or "").lower()
    blob = f"{meta.get('title')} {meta.get('snippet')}".lower()
    score = float(meta.get("fusion_score") or 0.5) * 10
    cat = str(meta.get("dork_category") or "")
    if cat == "social_post_search":
        score += 200
    if meta.get("trigger_keyword"):
        score += 120
    if cat in ("achievements", "events_general", "serp_discovered"):
        score += 100
    if cat in ("education", "news_mentions", "article_search"):
        score += 70
    if "facebook.com" in url or "instagram.com" in url:
        score += 90
    if re.search(r"facebook\.com/[^/]+/(?:photos|posts)", url):
        score += 80
    if is_social_post_url(url):
        score += 60
    if HACKATHON_SOCIAL_RE.search(blob):
        score += 50
    return score


async def enrich_dork_document_previews(
    entities: list[Entity],
    *,
    seed_query: str = "",
    limit: int = MAX_DORK_PREVIEWS,
) -> int:
    """Capture og:image or screenshots for seed-attributed dork pages lacking images."""
    candidates = [e for e in entities if _needs_preview(e, seed_query)]
    candidates.sort(key=_preview_priority, reverse=True)
    targets = candidates[:limit]
    if not targets:
        return 0

    async def _one(entity: Entity) -> None:
        url = _page_url(entity)
        if not url:
            return
        visual = await resolve_page_visual(url, budget="lead")
        if not visual:
            return
        meta = dict(entity.metadata or {})
        if visual.get("image_url"):
            meta["preview_image_url"] = visual["image_url"]
        if visual.get("screenshot_url"):
            meta["page_screenshot_url"] = visual["screenshot_url"]
        entity.metadata = meta

    await asyncio.gather(*[_one(e) for e in targets], return_exceptions=True)
    return len(targets)
