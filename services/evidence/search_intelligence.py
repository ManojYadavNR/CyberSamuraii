"""Extract first-class intelligence from Google dork / search engine hits."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from schemas.evidence import FieldProvenance
from schemas.fusion import Entity
from services.discovery.attribution import dork_hit_attributed
from services.discovery.validators import extract_urls_from_text, is_image_url, normalize_domain
from services.evidence.document_parser import parse_dork_document
from services.google_dorking.filters import is_junk_dork_url, dork_hit_displayable

PROFILE_PATH_HINTS = re.compile(
    r"/(?:in/|u/|user/|users/|profile/|@|channel/|c/|p/|r/|u_|member/|author/|people/)",
    re.I,
)
REPO_PATH_HINTS = re.compile(r"^[\w.-]+/[\w.-]+/?$")
FORUM_PATH_HINTS = re.compile(r"/(?:forum|forums|thread|topic|discussion|community)/", re.I)
BLOG_PATH_HINTS = re.compile(r"/(?:blog|posts?)/", re.I)
NEWS_PATH_HINTS = re.compile(r"/(?:news|press|headline|coverage)/", re.I)
ARTICLE_PATH_HINTS = re.compile(r"/(?:article|articles|story|stories|editorial|feature)/", re.I)
VIDEO_PATH_HINTS = re.compile(r"/(?:watch|shorts|video|v|embed)/", re.I)


def classify_search_hit(url: str, title: str = "", snippet: str = "") -> str:
    """Evidence category from URL shape — no platform names."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    path = parsed.path.lower()
    blob = f"{title} {snippet} {url}".lower()

    if is_image_url(url) or any(ext in path for ext in (".jpg", ".png", ".webp", ".gif")):
        return "image"
    if VIDEO_PATH_HINTS.search(path) or any(k in blob for k in (" video", " channel", " watch?v=")):
        return "video"
    if NEWS_PATH_HINTS.search(path) or any(k in blob for k in (" headline", " reported", " press release", " coverage")):
        return "news"
    if ARTICLE_PATH_HINTS.search(path) or any(k in blob for k in (" article", " editorial", " feature story")):
        return "article"
    if BLOG_PATH_HINTS.search(path) or any(k in blob for k in (" blog post", " blogger", " weblog")):
        return "blog"
    if PROFILE_PATH_HINTS.search(path) or (
        path.count("/") <= 2 and path.strip("/") and not REPO_PATH_HINTS.match(path.strip("/"))
    ):
        return "profile"
    host = (parsed.netloc or "").lower()
    if (
        REPO_PATH_HINTS.match(path.strip("/"))
        or "/repos/" in path
        or "/blob/" in path
        or "/tree/" in path
    ) and any(
        token in host
        for token in ("github", "gitlab", "bitbucket", "codeberg", "gitee", "sr.ht", "sourceforge")
    ):
        return "repository"
    if FORUM_PATH_HINTS.search(path):
        return "forum"
    if any(k in blob for k in ("pdf", "document", "resume", "cv", "paper")):
        return "document"
    if any(k in blob for k in ("archive.org", "cached", "wayback")):
        return "archived"
    return "mention"


def _provenance(
    entity: Entity,
    *,
    field: str,
    value: str,
    strategy: str,
    confidence: float = 0.72,
) -> FieldProvenance:
    meta = entity.metadata or {}
    return FieldProvenance(
        field=field,
        value=value,
        source_entity_id=entity.entity_id,
        source_entity_type=entity.type,
        source_platform=str(meta.get("platform") or normalize_domain(str(meta.get("url") or entity.value)) or "search"),
        source_tool=entity.sources[0] if entity.sources else "google_dorking",
        source_ref=str(meta.get("url") or entity.value),
        extraction_strategy=strategy,
        confidence=confidence,
    )


def extract_search_findings(entity: Entity, *, seed_query: str) -> list[FieldProvenance]:
    meta = dict(entity.metadata or {})
    if meta.get("check_type") != "google_dork":
        return []

    url = str(meta.get("url") or entity.value)
    if is_junk_dork_url(url):
        return []

    title = str(meta.get("title") or "")
    snippet = str(meta.get("snippet") or meta.get("content") or "")
    if seed_query and not dork_hit_displayable(
        url=url, title=title, snippet=snippet, seed_query=seed_query,
        dork_category=str(meta.get("dork_category") or ""),
        dork_query=str(meta.get("dork_query") or ""),
    ):
        return []

    findings: list[FieldProvenance] = []
    category = classify_search_hit(url, title, snippet)
    dork_cat = str(meta.get("dork_category") or "general")
    label = title or url

    findings.append(_provenance(
        entity, field="search_hit", value=f"{label}|{url}",
        strategy=f"search_{category}", confidence=float(entity.fusion_score or 0.65),
    ))
    findings.append(_provenance(
        entity, field="search_snippet", value=snippet[:1200] if snippet else title,
        strategy="search_snippet", confidence=0.7,
    ))
    if category == "profile":
        findings.append(_provenance(entity, field="public_link", value=url, strategy="search_profile_link", confidence=0.75))
    elif category in ("repository", "blog", "forum", "document", "video", "image", "news", "article"):
        findings.append(_provenance(entity, field=category, value=url, strategy=f"search_{category}_link", confidence=0.72))

    for field, value, strategy, confidence in parse_dork_document(meta, entity_value=entity.value, seed_query=seed_query):
        findings.append(_provenance(entity, field=field, value=value, strategy=strategy, confidence=confidence))

    for extra_url in extract_urls_from_text(f"{title} {snippet}")[:5]:
        if extra_url == url or is_junk_dork_url(extra_url):
            continue
        extra_cat = classify_search_hit(extra_url, title, snippet)
        findings.append(_provenance(
            entity, field=extra_cat, value=extra_url,
            strategy="search_embedded_link", confidence=0.62,
        ))

    findings.append(_provenance(
        entity, field="search_category", value=f"{dork_cat}:{category}",
        strategy="search_classification", confidence=0.6,
    ))

    structured = meta.get("structured_intelligence")
    if isinstance(structured, dict):
        for blog in structured.get("blogs") or []:
            findings.append(_provenance(entity, field="blog", value=str(blog), strategy="serp_blog", confidence=0.74))
        for article in structured.get("articles") or []:
            findings.append(_provenance(entity, field="article", value=str(article), strategy="serp_article", confidence=0.74))
        for news in structured.get("news") or []:
            findings.append(_provenance(entity, field="news", value=str(news), strategy="serp_news", confidence=0.73))
        for forum in structured.get("forums") or []:
            findings.append(_provenance(entity, field="forum", value=str(forum), strategy="serp_forum", confidence=0.72))
        for discussion in structured.get("discussions") or []:
            findings.append(_provenance(entity, field="forum", value=str(discussion), strategy="serp_discussion", confidence=0.71))
        for event in structured.get("events") or []:
            findings.append(_provenance(entity, field="event", value=str(event), strategy="serp_event", confidence=0.72))
        for ach in structured.get("achievements") or []:
            findings.append(_provenance(entity, field="achievement", value=str(ach), strategy="serp_achievement", confidence=0.73))
        for vid in structured.get("videos") or []:
            findings.append(_provenance(entity, field="video", value=str(vid), strategy="serp_video", confidence=0.72))
        for img in structured.get("images") or []:
            findings.append(_provenance(entity, field="image", value=str(img), strategy="serp_image", confidence=0.68))
        for email in structured.get("emails") or []:
            findings.append(_provenance(entity, field="email", value=str(email), strategy="serp_email", confidence=0.8))

    return findings


def extract_all_search_findings(entities: list[Entity], *, seed_query: str) -> list[FieldProvenance]:
    out: list[FieldProvenance] = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        if entity.type != "document":
            continue
        for fp in extract_search_findings(entity, seed_query=seed_query):
            key = (fp.field, fp.value.lower().split("|")[-1] if "|" in fp.value else fp.value.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(fp)
    return out
