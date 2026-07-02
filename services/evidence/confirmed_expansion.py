"""Expand investigation from confirmed anchors — college pages, org social, websites."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from schemas.fusion import Entity
from services.discovery.attribution import dork_hit_attributed
from services.discovery.validators import normalize_domain
from services.evidence.college_enrichment import (
    build_college_campus_search_queries,
    fetch_college_page_profile,
    prefetch_college_targets,
)
from services.evidence.google_search_intel import _dork_hits_from_entities
from services.evidence.platform_deep import deep_fetch_profile
from services.google_dorking.client import run_dork_queries
from services.google_dorking.dynamic_queries import build_dynamic_dork_queries
from services.google_dorking.filters import is_junk_dork_url
from services.google_dorking.keyword_discovery import DiscoveredKeyword, extract_keywords_from_serp


@dataclass
class ExpansionResult:
    new_hits: list[dict[str, Any]] = field(default_factory=list)
    new_entities: list[Entity] = field(default_factory=list)
    deep_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    queries_run: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)


def _hits_to_entities(hits: list[dict[str, Any]], *, seed_query: str) -> list[Entity]:
    from services.fusion_engine import _extract_from_item

    out: list[Entity] = []
    for hit in hits:
        url = str(hit.get("url") or "")
        if not url.startswith("http") or is_junk_dork_url(url):
            continue
        title = str(hit.get("title") or "")
        snippet = str(hit.get("snippet") or "")
        attributed = dork_hit_attributed(
            url=url,
            title=title,
            snippet=snippet,
            seed_query=seed_query,
            dork_query=str(hit.get("dork_query") or ""),
            dork_category=str(hit.get("dork_category") or ""),
        )
        item = {
            **hit,
            "platform": normalize_domain(url) or "web",
            "check_type": "google_dork",
            "username_attributed": attributed,
            "discovery_source": "confirmed_expansion",
            "expansion_anchor": True,
        }
        out.extend(_extract_from_item(item, "google_dorking", seed_query, "username_search"))
    return out


def _queries_from_intel(google_intel: dict[str, Any], seed_query: str) -> list[str]:
    """Build follow-up dorks from already-confirmed intel — no hardcoded names."""
    from services.google_dorking.dynamic_queries import _anchor

    anchor = _anchor(seed_query)
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            queries.append(q)

    for college in google_intel.get("colleges") or []:
        page_url = str(college.get("page_url") or "").strip()
        slug = ""
        if "facebook.com/" in page_url.lower():
            slug = page_url.rstrip("/").split("facebook.com/", 1)[-1].split("/")[0]
        if slug:
            add(f"site:facebook.com/{slug} {anchor}")
        for handle in college.get("instagram_handles") or []:
            h = str(handle).strip().lstrip("@")
            if h:
                add(f"site:instagram.com/{h} {anchor}")
        domain = str(college.get("website_domain") or "").strip()
        if domain:
            add(f"site:{domain} {anchor}")
            add(f"site:{domain} {anchor} hackathon")

    for kw in google_intel.get("discovered_keywords") or []:
        phrase = str(kw.get("phrase") if isinstance(kw, dict) else kw).strip()
        if len(phrase) >= 4:
            add(f'"{anchor}" {phrase}')

    for win in google_intel.get("hackathon_wins") or []:
        event = str(win.get("hackathon") or "").strip()
        if len(event) >= 4:
            add(f'"{anchor}" "{event}"')

    return queries[:20]


async def _deep_enrich_anchors(
    google_intel: dict[str, Any],
    *,
    seed_query: str,
) -> dict[str, dict[str, Any]]:
    """Deep-scrape confirmed college / org social pages for more leads."""
    profiles: dict[str, dict[str, Any]] = {}
    urls: list[tuple[str, str]] = []
    seen: set[str] = set()

    def queue(url: str, kind: str) -> None:
        u = url.strip()
        if not u.startswith("http") or u in seen:
            return
        seen.add(u)
        urls.append((u, kind))

    for college in google_intel.get("colleges") or []:
        page_url = str(college.get("page_url") or "").strip()
        if page_url:
            queue(page_url, "college_facebook")
        ig_url = str(college.get("instagram_url") or "").strip()
        if ig_url:
            queue(ig_url, "college_instagram")
        for handle in college.get("instagram_handles") or []:
            h = str(handle).strip().lstrip("@")
            if h:
                queue(f"https://www.instagram.com/{h}/", "college_instagram")
        web = str(college.get("website_url") or "").strip()
        if web:
            queue(web, "college_website")

    sem = asyncio.Semaphore(6)

    async def one(url: str, kind: str) -> None:
        async with sem:
            try:
                if kind == "college_facebook":
                    target = await fetch_college_page_profile(url)
                    payload: dict[str, Any] = {
                        "official_name": target.official_name,
                        "website_url": target.website_url,
                        "website_domain": target.website_domain,
                        "instagram_handles": sorted(target.instagram_handles),
                        "confirmed_anchor_type": kind,
                        "expansion_anchor": True,
                    }
                else:
                    payload = await deep_fetch_profile(url, seed_query=seed_query)
                    payload["confirmed_anchor_type"] = kind
                    payload["expansion_anchor"] = True
                if payload:
                    profiles[url] = payload
            except Exception:
                return

    await asyncio.gather(*(one(u, k) for u, k in urls[:8]), return_exceptions=True)
    return profiles


async def expand_from_confirmed_anchors(
    entities: list[Entity],
    google_intel: dict[str, Any],
    *,
    seed_query: str,
    budget_sec: float = 50.0,
) -> ExpansionResult:
    """
    When something is confirmed (college FB post, campus page, hackathon win),
    run deeper Google searches and scrape those anchor pages for more intel.
    """
    if not seed_query.strip():
        return ExpansionResult()

    result = ExpansionResult()
    deadline = time.monotonic() + budget_sec
    existing_urls = {
        str((e.metadata or {}).get("url") or e.value)
        for e in entities
        if e.type in ("document", "account")
    }

    serp_hits = _dork_hits_from_entities(entities)
    campus_targets = await prefetch_college_targets(seed_query, serp_hits)
    campus_queries = [d.query for d in build_college_campus_search_queries(seed_query, campus_targets)]
    intel_queries = _queries_from_intel(google_intel, seed_query)

    keywords_raw = google_intel.get("discovered_keywords") or []
    keywords: list[DiscoveredKeyword] = []
    for item in keywords_raw:
        if isinstance(item, dict) and item.get("phrase"):
            try:
                keywords.append(DiscoveredKeyword(
                    phrase=str(item["phrase"]),
                    category=str(item.get("category") or "general"),
                    source_url=str(item.get("source_url") or ""),
                    source_title=str(item.get("source_title") or ""),
                    score=float(item.get("score") or 0.5),
                    source_snippet=str(item.get("source_snippet") or ""),
                ))
            except Exception:
                continue
    if not keywords and serp_hits:
        keywords = extract_keywords_from_serp(serp_hits, seed_query=seed_query)
    dynamic = [d.query for d in build_dynamic_dork_queries(seed_query, keywords)]
    dynamic = [q for q in dynamic if q not in campus_queries and q not in intel_queries]

    all_queries = list(dict.fromkeys([*campus_queries, *intel_queries, *dynamic[:12]]))
    if not all_queries or time.monotonic() >= deadline - 5:
        result.deep_profiles = await _deep_enrich_anchors(google_intel, seed_query=seed_query)
        if result.deep_profiles:
            result.strategies.append("anchor_deep_scrape")
        return result

    dork_categories = {q: "social_post_search" for q in all_queries}
    new_hits = await run_dork_queries(
        all_queries,
        results_per_dork=8,
        max_concurrency=5,
        dork_categories=dork_categories,
        deadline_monotonic=deadline,
    )
    for hit in new_hits:
        hit["serp_phase"] = "confirmed_expansion"
        hit.setdefault("dork_category", "social_post_search")

    fresh = [h for h in new_hits if str(h.get("url") or "") not in existing_urls]
    result.new_hits = fresh
    result.queries_run = all_queries
    result.new_entities = _hits_to_entities(fresh, seed_query=seed_query)
    result.deep_profiles = await _deep_enrich_anchors(google_intel, seed_query=seed_query)

    if fresh:
        result.strategies.append("confirmed_anchor_dorking")
    if result.deep_profiles:
        result.strategies.append("anchor_deep_scrape")
    return result


def apply_deep_profiles_to_intel(
    google_intel: dict[str, Any],
    deep_profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Merge anchor deep-scrape results (college IG, website) back into intel rows."""
    if not deep_profiles:
        return google_intel

    intel = dict(google_intel)
    colleges = [dict(row) for row in (intel.get("colleges") or [])]
    if not colleges:
        return intel

    for row in colleges:
        page_url = str(row.get("page_url") or row.get("url") or "").strip().lower()
        slug = ""
        if "facebook.com/" in page_url:
            slug = page_url.split("facebook.com/", 1)[-1].split("/")[0]

        for url, payload in deep_profiles.items():
            if not isinstance(payload, dict):
                continue
            url_l = url.lower()
            matched = bool(page_url and (page_url in url_l or url_l in page_url))
            if not matched and slug and slug in url_l:
                matched = True
            if not matched:
                continue

            handles = set(row.get("instagram_handles") or [])
            handles.update(payload.get("instagram_handles") or [])
            if handles:
                row["instagram_handles"] = sorted(handles)
                row["instagram_url"] = f"https://www.instagram.com/{sorted(handles)[0]}/"

            if payload.get("official_name") and not row.get("official_name"):
                row["official_name"] = payload["official_name"]
                row["college"] = payload["official_name"]

            if payload.get("website_url"):
                row["website_url"] = payload["website_url"]
                row["website_domain"] = payload.get("website_domain") or row.get("website_domain")

            for post in payload.get("social_posts") or payload.get("recent_posts") or []:
                text = post if isinstance(post, str) else str(post.get("text") or post.get("snippet") or "")
                if text.strip():
                    row.setdefault("campus_posts", []).append(text.strip()[:400])

    intel["colleges"] = colleges
    return intel
