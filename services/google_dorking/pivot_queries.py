"""Entity-based pivot queries from SERP hits — no hardcoded names."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from services.discovery.attribution import dork_hit_attributed, person_name_variants, split_handle_to_display_name
from services.discovery.validators import normalize_domain
from services.google_dorking.queries import DorkQuery
from services.platform_registry import (
    is_priority_social_host,
    normalize_platform_host,
    platform_label_from_host,
    priority_social_domains,
    profile_slug_from_url,
    site_post_search_query,
    skip_pivot_domain,
)

HASHTAG_RE = re.compile(r"#[\w][\w\d_]{2,39}")
INSTITUTION_RE = re.compile(
    r"\b[\w][\w\s&'.-]{2,72}(?:Institute|College|University|School|Academy|Polytechnic)\b",
    re.I,
)


def _anchor_variants(seed_query: str) -> list[str]:
    seed = seed_query.split("|")[0].strip()
    out: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        clean = text.replace('"', "").strip()
        if not clean or clean.lower() in seen:
            return
        seen.add(clean.lower())
        out.append(f'"{clean}"' if " " in clean else clean)

    add(seed)
    display = split_handle_to_display_name(seed)
    if display:
        add(display)
    for variant in person_name_variants(seed):
        add(variant)
    return out


def _is_institution_phrase(phrase: str) -> bool:
    return bool(INSTITUTION_RE.search(phrase))


def _social_domains(limit: int = 6) -> list[str]:
    return list(priority_social_domains(limit))


def extract_entity_pivots(hits: list[dict[str, Any]], *, seed_query: str) -> dict[str, set[str] | dict[str, set[str]]]:
    """Pull hashtags, profile slugs, domains, org names from attributed hits."""
    site_slugs: dict[str, set[str]] = defaultdict(set)
    pivots: dict[str, set[str] | dict[str, set[str]]] = {
        "hashtags": set(),
        "site_slugs": site_slugs,
        "domains": set(),
        "institutions": set(),
        "events": set(),
    }
    skip_hosts = frozenset()  # pivot skip handled by skip_pivot_domain()
    for hit in hits:
        if not dork_hit_attributed(
            url=str(hit.get("url") or ""),
            title=str(hit.get("title") or ""),
            snippet=str(hit.get("snippet") or ""),
            seed_query=seed_query,
            dork_query=str(hit.get("dork_query") or ""),
            dork_category=str(hit.get("dork_category") or ""),
        ):
            continue
        text = f"{hit.get('title') or ''} {hit.get('snippet') or ''}"
        url = str(hit.get("url") or "")

        for tag in HASHTAG_RE.findall(text):
            pivots["hashtags"].add(tag.lower())  # type: ignore[union-attr]

        slug = profile_slug_from_url(url)
        host = normalize_platform_host(url)
        if slug and host and not skip_pivot_domain(host):
            site_slugs[host].add(slug.lower())

        domain = normalize_domain(url) or ""
        if domain and not skip_pivot_domain(domain) and not is_priority_social_host(domain):
            if any(k in text.lower() for k in ("college", "university", "institute", "school", "campus")):
                pivots["domains"].add(domain)  # type: ignore[union-attr]

        for inst in INSTITUTION_RE.findall(text):
            clean = " ".join(inst.split()).strip()
            if len(clean) >= 8 and _is_institution_phrase(clean):
                pivots["institutions"].add(clean)  # type: ignore[union-attr]

        from services.google_dorking.keyword_discovery import HACKATHON_EVENT_RE

        for match in HACKATHON_EVENT_RE.finditer(text):
            event = " ".join(match.group(1).split()).strip()
            if len(event) >= 6:
                pivots["events"].add(event)  # type: ignore[union-attr]

    return pivots


def build_pivot_dork_queries(
    seed_query: str,
    pivots: dict[str, set[str] | dict[str, set[str]]],
    *,
    max_queries: int = 16,
) -> list[DorkQuery]:
    """Turn discovered entities into surgical follow-up dorks."""
    anchors = _anchor_variants(seed_query)
    if not anchors:
        return []

    primary = anchors[0]
    out: list[DorkQuery] = []
    seen: set[str] = set()
    social_domains = _social_domains(6)

    def add(query: str, category: str = "entity_pivot") -> None:
        q = " ".join(query.split()).strip()
        if not q or q in seen or len(out) >= max_queries:
            return
        seen.add(q)
        out.append(DorkQuery(query=q, category=category))

    site_slugs = pivots.get("site_slugs") or {}
    if isinstance(site_slugs, dict):
        for domain in sorted(site_slugs):
            for slug in sorted(site_slugs[domain]):
                add(f"site:{domain}/{slug} {primary}", "social_post_search")
                add(f"site:{domain}/{slug} {primary} hackathon", "social_post_search")

    domains = pivots.get("domains") or set()
    if isinstance(domains, set):
        for domain in sorted(domains):
            add(f"site:{domain} {primary}", "serp_discovered")
            add(f"site:{domain} {primary} hackathon", "achievements")

    institutions = pivots.get("institutions") or set()
    if isinstance(institutions, set):
        for inst in sorted(institutions):
            name = inst.replace('"', "")
            add(f'{primary} "{name}"', "education")
            for domain in social_domains[:2]:
                add(f"site:{domain} {primary} \"{name}\"", "social_post_search")

    hashtags = pivots.get("hashtags") or set()
    if isinstance(hashtags, set):
        for tag in sorted(hashtags):
            for domain in social_domains[:3]:
                add(site_post_search_query(domain, tag, primary), "serp_discovered")

    events = pivots.get("events") or set()
    if isinstance(events, set):
        for event in sorted(events):
            ev = event.replace('"', "")
            add(f'{primary} "{ev}"', "achievements")
            for domain in social_domains[:2]:
                add(site_post_search_query(domain, primary, f'"{ev}"'), "serp_discovered")

    return out
