"""Lead Visual Engine — prioritized hackathon / news / college capture."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from schemas.evidence import PlatformProfile
from schemas.fusion import Entity
from schemas.lead_visual import LeadVisual, LeadVisualOutput
from services.google_dorking.filters import dork_hit_displayable
from services.discovery.validators import is_image_url, is_plausible_profile_photo
from services.lead_visual.classifier import (
    classify_lead_type,
    extract_seed_username,
    is_junk_lead_url,
    source_domain,
)
from services.lead_visual.preview import resolve_lead_visual
from services.lead_visual.scorer import score_lead
from services.lead_visual.youtube import youtube_thumbnail

MAX_LEAD_CAPTURES = 18
MAX_PROFILE_LEADS = 5
LEAD_CAPTURE_CONCURRENCY = 3


@dataclass
class _Candidate:
    url: str
    title: str
    snippet: str
    dork_category: str
    fusion_score: float
    entity_id: str | None
    lead_type: str
    priority_score: float
    serp_image: str | None = None


def _collect_from_entities(entities: list[Entity], seed_query: str) -> list[_Candidate]:
    username = extract_seed_username(seed_query)
    out: list[_Candidate] = []
    seen: set[str] = set()

    for entity in entities:
        meta = entity.metadata or {}
        if meta.get("check_type") != "google_dork" and entity.type != "document":
            continue
        url = str(meta.get("url") or entity.value or "")
        if url:
            from services.social_urls import fix_facebook_post_url
            url = fix_facebook_post_url(url)
        if is_junk_lead_url(url) or url in seen:
            continue
        title = str(meta.get("title") or "")
        snippet = str(meta.get("snippet") or meta.get("content") or "")
        dork_cat = str(meta.get("dork_category") or "")

        if username and not dork_hit_displayable(
            url=url,
            title=title,
            snippet=snippet,
            seed_query=username,
            dork_category=dork_cat,
            dork_query=str(meta.get("dork_query") or ""),
        ):
            continue

        seen.add(url)
        lead_type = classify_lead_type(url=url, title=title, snippet=snippet, dork_category=dork_cat)
        if lead_type in ("mention", "profile") and lead_type == "mention":
            blob = f"{title} {snippet}".lower()
            if not any(k in blob for k in ("hackathon", "winner", "college", "news", "award", "event")):
                continue

        serp_image = None
        structured = meta.get("structured_intelligence")
        if isinstance(structured, dict):
            for img in structured.get("images") or []:
                if isinstance(img, str) and img.startswith("http"):
                    serp_image = img
                    break
        if not serp_image and is_image_url(url):
            serp_image = url

        priority = score_lead(
            lead_type=lead_type,
            title=title,
            snippet=snippet,
            url=url,
            dork_category=dork_cat,
            fusion_score=float(entity.fusion_score or 0.5),
        )
        out.append(_Candidate(
            url=url,
            title=title or source_domain(url),
            snippet=snippet[:1200],
            dork_category=dork_cat,
            fusion_score=float(entity.fusion_score or 0.5),
            entity_id=entity.entity_id,
            lead_type=lead_type,
            priority_score=priority,
            serp_image=serp_image,
        ))

    return out


def _collect_profile_leads(profiles: list[PlatformProfile], limit: int = MAX_PROFILE_LEADS) -> list[_Candidate]:
    out: list[_Candidate] = []
    ranked = sorted(
        [p for p in profiles if p.verified and p.url and not is_junk_lead_url(p.url)],
        key=lambda p: (-(p.fusion_score or 0), -len(p.bio or "")),
    )
    for pp in ranked[:limit]:
        out.append(_Candidate(
            url=pp.url or "",
            title=pp.display_name or pp.handle or pp.platform,
            snippet=(pp.bio or "")[:1200],
            dork_category="profile",
            fusion_score=float(pp.fusion_score or 0.5),
            entity_id=pp.entity_id,
            lead_type="profile",
            priority_score=score_lead(
                lead_type="profile",
                title=pp.display_name or pp.handle,
                snippet=pp.bio or "",
                url=pp.url or "",
                fusion_score=float(pp.fusion_score or 0.5),
            ),
            serp_image=pp.avatar_url if pp.avatar_url and pp.avatar_url.startswith("http") else None,
        ))
    return out


async def build_lead_visuals(
    entities: list[Entity],
    *,
    seed_query: str,
    platform_profiles: list[PlatformProfile] | None = None,
    limit: int = MAX_LEAD_CAPTURES,
) -> LeadVisualOutput:
    """Build prioritized lead cards with images for hackathon/news/college content."""
    candidates = _collect_from_entities(entities, seed_query)
    candidates.extend(_collect_profile_leads(platform_profiles or []))

    # Prefer hackathon/news/college over generic profiles
    candidates.sort(key=lambda c: -c.priority_score)
    deduped: list[_Candidate] = []
    seen_urls: set[str] = set()
    for c in candidates:
        if c.url in seen_urls:
            continue
        seen_urls.add(c.url)
        deduped.append(c)

    lead_candidates = [c for c in deduped if c.lead_type != "profile"][:limit]
    profile_candidates = [c for c in deduped if c.lead_type == "profile"][:MAX_PROFILE_LEADS]

    sem = asyncio.Semaphore(LEAD_CAPTURE_CONCURRENCY)
    leads: list[LeadVisual] = []
    strategies: set[str] = set()
    screenshots = 0

    async def _process(c: _Candidate, *, allow_screenshot: bool) -> LeadVisual | None:
        nonlocal screenshots
        try:
            image_url = c.serp_image
            thumb = c.serp_image
            visual_source = "serp_image" if image_url else ""

            if c.lead_type == "video" and not image_url:
                thumb = youtube_thumbnail(c.url)
                if thumb:
                    image_url, visual_source = thumb, "youtube_thumb"

            if not image_url and c.serp_image and is_plausible_profile_photo(c.serp_image):
                image_url, thumb, visual_source = c.serp_image, c.serp_image, "serp_image"

            if not image_url and allow_screenshot:
                async with sem:
                    img, th, src = await resolve_lead_visual(c.url, lead_type=c.lead_type, allow_screenshot=True)
                if img:
                    image_url, thumb, visual_source = img, th or img, src
                    if src == "page_screenshot":
                        screenshots += 1

            if not image_url and not c.title:
                return None

            strategies.add(visual_source or "text_only")
            return LeadVisual(
                lead_id=c.entity_id or str(uuid.uuid4())[:12],
                lead_type=c.lead_type,
                title=c.title,
                url=c.url,
                snippet=c.snippet,
                source_domain=source_domain(c.url),
                image_url=image_url,
                thumbnail_url=thumb or image_url,
                visual_source=visual_source or "none",
                confidence=min(1.0, 0.45 + c.fusion_score * 0.4 + (0.15 if image_url else 0)),
                priority_score=c.priority_score,
            )
        except Exception:
            if not c.title:
                return None
            strategies.add("text_only")
            return LeadVisual(
                lead_id=c.entity_id or str(uuid.uuid4())[:12],
                lead_type=c.lead_type,
                title=c.title,
                url=c.url,
                snippet=c.snippet,
                source_domain=source_domain(c.url),
                image_url=None,
                thumbnail_url=None,
                visual_source="none",
                confidence=min(1.0, 0.45 + c.fusion_score * 0.4),
                priority_score=c.priority_score,
            )

    tasks = [_process(c, allow_screenshot=True) for c in lead_candidates]
    tasks += [_process(c, allow_screenshot=False) for c in profile_candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for item in results:
        if isinstance(item, LeadVisual):
            leads.append(item)

    leads.sort(key=lambda lv: -lv.priority_score)

    # Write back to entity metadata for downstream parsers
    entity_by_id = {e.entity_id: e for e in entities}
    for lead in leads:
        ent = entity_by_id.get(lead.lead_id)
        if not ent:
            continue
        meta = dict(ent.metadata or {})
        if lead.image_url:
            meta["preview_image_url"] = lead.image_url if lead.visual_source != "page_screenshot" else meta.get("preview_image_url")
            if lead.visual_source == "page_screenshot":
                meta["page_screenshot_url"] = lead.image_url
        meta["lead_type"] = lead.lead_type
        meta["lead_title"] = lead.title
        ent.metadata = meta

    return LeadVisualOutput(
        leads=leads,
        captured_screenshots=screenshots,
        strategies=sorted(strategies),
    )
