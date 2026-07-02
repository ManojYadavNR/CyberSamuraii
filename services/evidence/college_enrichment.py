"""Resolve full college names from page metadata and mine college websites."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from services.discovery.attribution import context_references_seed
from services.discovery.validators import extract_urls_from_text, normalize_domain
from services.evidence.document_parser import SCHOOL_RE, _extract_event_labels
from services.evidence.platform_deep import _fetch_html, _parse_og_tags
from services.google_dorking.keyword_discovery import ACHIEVEMENT_HINT, HACKATHON_EVENT_RE
from services.google_dorking.queries import DorkQuery

INSTITUTION_TAIL_RE = re.compile(
    r"\b([A-Z][\w\s&'.-]{2,56}(?:Institute|College|University|School|Academy|Polytechnic|"
    r"Engineering)(?:\s+of\s+[A-Z][\w\s&'.-]{2,32})?(?:\s*,\s*[A-Z][\w\s&'.-]{2,24})?)\b",
    re.I,
)
PLATFORM_TITLE_SUFFIX_RE = re.compile(
    r"\s*[\|–-]\s*(Facebook|Instagram|Home|Posts|Photos|Videos|Timeline)\s*$",
    re.I,
)
INSTAGRAM_HANDLE_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]+)", re.I)
from adapters.site_lists import scanner_registry_domains
MAX_COLLEGE_PAGE_FETCHES = 4
MAX_WEBSITE_FETCHES = 3


@dataclass
class CollegeCampusTarget:
    facebook_slug: str = ""
    facebook_page_url: str = ""
    official_name: str = ""
    instagram_handles: set[str] = field(default_factory=set)
    website_domain: str = ""
    website_url: str = ""
    hackathons: set[str] = field(default_factory=set)


def _strip_platform_title(title: str) -> str:
    cleaned = PLATFORM_TITLE_SUFFIX_RE.sub("", title.strip())
    return " ".join(cleaned.split()).strip(" .,-|")


def institution_name_from_text(text: str) -> str | None:
    if not text:
        return None
    for match in INSTITUTION_TAIL_RE.finditer(text):
        name = " ".join(match.group(1).split()).strip()
        if len(name) >= 8:
            return name
    for match in SCHOOL_RE.finditer(text):
        name = " ".join(match.group(0).split()).strip()
        if len(name) >= 8:
            return name
    return None


def _decode_facebook_redirect(url: str) -> str:
    if "l.facebook.com/l.php" not in url.lower():
        return url
    parsed = urlparse(url)
    target = parse_qs(parsed.query).get("u", [""])[0]
    return unquote(target) if target else url


def _extract_external_links(html: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r'href=["\'](https?://[^"\']+)["\']', html[:120000], re.I):
        urls.append(match.group(1))
    urls.extend(extract_urls_from_text(html[:120000]))
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = _decode_facebook_redirect(raw.split("&")[0] if "&amp;" in raw else raw)
        if not url.startswith("http"):
            continue
        domain = normalize_domain(url) or ""
        if not domain or domain in scanner_registry_domains():
            continue
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _extract_instagram_handles(html: str) -> set[str]:
    handles: set[str] = set()
    for match in INSTAGRAM_HANDLE_RE.finditer(html[:120000]):
        handle = match.group(1).lower()
        if handle not in {"p", "reel", "tv", "explore", "accounts", "about"}:
            handles.add(handle)
    for match in re.finditer(r'instagram\.com\\?/([a-zA-Z0-9._]{2,30})', html[:120000], re.I):
        handle = match.group(1).lower()
        if handle not in {"p", "reel", "tv", "explore", "accounts", "about"}:
            handles.add(handle)
    return handles


async def fetch_college_page_profile(page_url: str) -> CollegeCampusTarget:
    """Read og:title / links from a college Facebook or Instagram profile page."""
    target = CollegeCampusTarget(facebook_page_url=page_url)
    html = await _fetch_html(page_url)
    if not html:
        return target

    tags = _parse_og_tags(html)
    og_title = _strip_platform_title(tags.get("og:title") or tags.get("og:site_name") or "")
    og_desc = tags.get("og:description") or tags.get("description") or ""
    name = institution_name_from_text(f"{og_title} {og_desc}") or institution_name_from_text(og_title)
    if name:
        target.official_name = name
    elif og_title and len(og_title) >= 6 and not re.search(r"^congratulations\b", og_title, re.I):
        target.official_name = og_title

    parsed = urlparse(page_url if "://" in page_url else f"https://{page_url}")
    host = (parsed.netloc or "").lower()
    path = parsed.path.strip("/")
    if "facebook.com" in host and path:
        slug = path.split("/")[0]
        if slug.lower() not in {"www", "pages", "profile.php"}:
            target.facebook_slug = slug
            target.facebook_page_url = f"https://www.facebook.com/{slug}"

    if "instagram.com" in host and path:
        handle = path.split("/")[0].lower()
        if handle not in {"p", "reel", "tv", "explore"}:
            target.instagram_handles.add(handle)

    target.instagram_handles.update(_extract_instagram_handles(html))

    for url in _extract_external_links(html):
        domain = normalize_domain(url) or ""
        if domain and not target.website_domain:
            target.website_domain = domain
            target.website_url = url if url.startswith("http") else f"https://{domain}"
            break

    return target


def _achievement_snippets(html: str, seed_query: str) -> list[dict[str, Any]]:
    text = re.sub(r"<[^>]+>", " ", html[:100000])
    text = " ".join(text.split())
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for match in re.finditer(r"[^.!?]{20,320}(?:hackathon|winner|runner-?up|award|fest)[^.!?]{0,160}[.!?]?", text, re.I):
        sentence = " ".join(match.group(0).split()).strip()
        if not context_references_seed(sentence, seed_query=seed_query):
            continue
        if not ACHIEVEMENT_HINT.search(sentence):
            continue
        key = sentence.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        hackathon = ""
        for event in _extract_event_labels(sentence):
            hackathon = event
            break
        if not hackathon:
            hm = HACKATHON_EVENT_RE.search(sentence)
            if hm:
                hackathon = hm.group(1).strip()
        rows.append({
            "text": sentence[:400],
            "hackathon": hackathon,
            "source": "college_website",
        })
    return rows[:8]


async def fetch_college_website_intel(website_url: str, *, seed_query: str) -> dict[str, Any]:
    html = await _fetch_html(website_url)
    if not html:
        return {}
    tags = _parse_og_tags(html)
    title = _strip_platform_title(tags.get("og:title") or tags.get("title") or "")
    name = institution_name_from_text(f"{title} {tags.get('og:description') or ''}") or institution_name_from_text(title)
    return {
        "official_name": name or "",
        "achievements": _achievement_snippets(html, seed_query),
        "website_url": website_url,
    }


async def prefetch_college_targets(
    seed_query: str,
    hits: list[dict[str, Any]],
    *,
    limit: int = MAX_COLLEGE_PAGE_FETCHES,
) -> list[CollegeCampusTarget]:
    """Build campus targets from SERP hits and enrich via live page fetch."""
    from services.evidence.google_search_intel import (
        COLLEGE_POST_CONTEXT,
        _attributed,
        _facebook_page_slug,
        _facebook_page_url,
    )

    by_slug: dict[str, CollegeCampusTarget] = {}

    for hit in hits:
        if not _attributed(hit, seed_query):
            continue
        url = str(hit.get("url") or "")
        text = f"{hit.get('title') or ''} {hit.get('snippet') or ''}"
        if not COLLEGE_POST_CONTEXT.search(text):
            continue
        slug = _facebook_page_slug(url)
        if not slug:
            continue
        target = by_slug.setdefault(slug.lower(), CollegeCampusTarget(
            facebook_slug=slug,
            facebook_page_url=_facebook_page_url(slug),
        ))
        for event in _extract_event_labels(text):
            if len(event) >= 4:
                target.hackathons.add(event)
        for match in HACKATHON_EVENT_RE.finditer(text):
            event = match.group(1).strip()
            if len(event) >= 4:
                target.hackathons.add(event)

    slugs = list(by_slug.keys())[:limit]
    if not slugs:
        return []

    async def _one(slug_key: str) -> CollegeCampusTarget:
        base = by_slug[slug_key]
        profile = await fetch_college_page_profile(base.facebook_page_url)
        base.official_name = profile.official_name or base.official_name
        base.instagram_handles.update(profile.instagram_handles)
        if profile.website_domain:
            base.website_domain = profile.website_domain
            base.website_url = profile.website_url
        return base

    enriched = await asyncio.gather(*[_one(s) for s in slugs], return_exceptions=True)
    out: list[CollegeCampusTarget] = []
    for item in enriched:
        if isinstance(item, CollegeCampusTarget):
            out.append(item)
    return out


def build_college_campus_search_queries(
    seed_query: str,
    targets: list[CollegeCampusTarget],
    *,
    max_queries: int = 16,
) -> list[DorkQuery]:
    """Search college Facebook/Instagram/website for more posts about the seed user."""
    from services.google_dorking.dynamic_queries import _anchor

    anchor = _anchor(seed_query)
    out: list[DorkQuery] = []
    seen: set[str] = set()

    def add(query: str) -> None:
        if query in seen or len(out) >= max_queries:
            return
        seen.add(query)
        out.append(DorkQuery(query=query, category="social_post_search"))

    for target in targets:
        slug = target.facebook_slug
        if slug:
            add(f"site:facebook.com/{slug} {anchor}")
            add(f"site:facebook.com/{slug} {anchor} hackathon")
            for hack in sorted(target.hackathons):
                if len(hack) >= 4:
                    add(f"site:facebook.com/{slug} {anchor} {hack}")

        for handle in sorted(target.instagram_handles):
            add(f"site:instagram.com {anchor} {handle}")
            add(f"site:instagram.com/{handle} {anchor}")
            for hack in sorted(target.hackathons):
                if len(hack) >= 4:
                    add(f"site:instagram.com/{handle} {anchor} {hack}")

        if target.website_domain:
            add(f"site:{target.website_domain} {anchor} hackathon")
            add(f"site:{target.website_domain} {anchor} winner")
            for hack in sorted(target.hackathons):
                if len(hack) >= 4:
                    add(f"site:{target.website_domain} {anchor} {hack}")

        if target.official_name and len(target.official_name) >= 8:
            name = target.official_name.replace('"', "")
            add(f'site:facebook.com {anchor} "{name}"')
            add(f'site:instagram.com {anchor} "{name}"')

    return out


async def enrich_google_search_intel_colleges(
    intel: dict[str, Any],
    *,
    seed_query: str,
) -> dict[str, Any]:
    """Attach official names, website links, and website achievements to college rows."""
    colleges = list(intel.get("colleges") or [])
    if not colleges:
        return intel

    website_fetches = 0
    enriched_rows: list[dict[str, Any]] = []

    for row in colleges:
        row = dict(row)
        page_url = str(row.get("page_url") or row.get("url") or "")
        if "facebook.com" in page_url.lower():
            profile = await fetch_college_page_profile(page_url)
            if profile.official_name:
                row["college"] = profile.official_name
                row["official_name"] = profile.official_name
            if profile.instagram_handles:
                row["instagram_handles"] = sorted(profile.instagram_handles)
                row["instagram_url"] = f"https://www.instagram.com/{sorted(profile.instagram_handles)[0]}/"
            if profile.website_url:
                row["website_url"] = profile.website_url
                row["website_domain"] = profile.website_domain
                if website_fetches < MAX_WEBSITE_FETCHES:
                    web = await fetch_college_website_intel(profile.website_url, seed_query=seed_query)
                    website_fetches += 1
                    achievements = web.get("achievements") or []
                    if achievements:
                        row["website_achievements"] = achievements
                    if web.get("official_name") and not row.get("official_name"):
                        row["college"] = web["official_name"]
                        row["official_name"] = web["official_name"]

        enriched_rows.append(row)

    intel = dict(intel)
    kept: list[dict[str, Any]] = []
    for row in enriched_rows:
        name = str(row.get("official_name") or row.get("college") or "").strip()
        page_url = str(row.get("page_url") or row.get("url") or "")
        if not name and not page_url:
            continue
        if name and not re.search(r"institute|college|university|school|academy|polytechnic|engineering", name, re.I):
            if len(name) < 8 and not row.get("facebook_slug"):
                continue
        kept.append(row)
    intel["colleges"] = kept[:4]

    extra_wins: list[dict[str, Any]] = []
    seen_win: set[str] = set()
    for row in enriched_rows:
        for ach in row.get("website_achievements") or []:
            text = str(ach.get("text") or "")
            hack = str(ach.get("hackathon") or "Hackathon achievement")
            key = text.lower()[:100]
            if key in seen_win:
                continue
            seen_win.add(key)
            extra_wins.append({
                "hackathon": hack,
                "placement": "mentioned",
                "title": text[:160],
                "url": row.get("website_url") or row.get("page_url") or "",
                "snippet": text,
                "platform": "web",
                "preview_url": "",
                "source": "college_website",
            })

    if extra_wins:
        wins = list(intel.get("hackathon_wins") or [])
        wins.extend(extra_wins)
        intel["hackathon_wins"] = wins[:12]

    return intel
