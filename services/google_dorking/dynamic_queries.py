"""Build social post searches from SERP-discovered keywords."""

from __future__ import annotations

import re

from services.discovery.attribution import split_handle_to_display_name
from services.google_dorking.keyword_discovery import DiscoveredKeyword
from services.google_dorking.queries import DorkQuery
from services.platform_registry import (
    is_priority_social_host,
    normalize_platform_host,
    platform_key_from_host,
    priority_social_domains,
    profile_slug_from_url,
    site_post_search_query,
)

# Keywords worth searching on social platforms — discovered per person, never hardcoded.
SOCIAL_KEYWORD_CATEGORIES = frozenset({
    "achievement",
    "education",
    "organization",
    "professional",
    "hashtag",
})

SOCIAL_POST_URL_RE = re.compile(
    r"/(?:posts|photos|videos|reel|permalink)(?:/|$)|/(?:p|reel|tv)/[^/?#]+",
    re.I,
)

SKIP_PHRASES = frozenset({
    "social post",
})


def _social_domains(limit: int = 4) -> list[str]:
    return list(priority_social_domains(limit))


def is_social_post_url(url: str) -> bool:
    """Backward-compatible wrapper — local regex plus platform registry."""
    if not url:
        return False
    low = url.lower()
    if SOCIAL_POST_URL_RE.search(low):
        return True
    from services.platform_registry import is_social_post_url as registry_is_social_post_url
    return registry_is_social_post_url(url)


def _post_search_site(domain: str, anchor: str, phrase: str) -> str:
    return site_post_search_query(domain, anchor, phrase)


def _anchor(seed_query: str) -> str:
    seed = seed_query.split("|")[0].strip()
    display = split_handle_to_display_name(seed)
    name = display or seed
    return f'"{name}"' if " " in name else name


def build_display_name_seed_queries(seed_query: str) -> list[DorkQuery]:
    """Plain Google searches using the handle-derived display name."""
    seed = seed_query.split("|")[0].strip()
    display = split_handle_to_display_name(seed)
    if not display or display.lower() == seed.lower():
        return []
    escaped = display.replace('"', "")
    return [
        DorkQuery(query=f'"{escaped}"', category="google_plain"),
        DorkQuery(query=f'"{escaped}" hackathon', category="achievements"),
    ]


def build_fallback_social_queries(seed_query: str, *, max_queries: int = 8) -> list[DorkQuery]:
    """
    When SERP keyword extraction finds nothing, search top social hosts with
    the person's display name + generic achievement/education terms.
    """
    seed = seed_query.split("|")[0].strip()
    display = split_handle_to_display_name(seed)
    if not display:
        return []
    anchor = f'"{display.replace(chr(34), "")}"'
    out: list[DorkQuery] = []
    seen: set[str] = set()
    domains = _social_domains(4)
    for term in ("hackathon", "winner", "college", "university", "fest"):
        for domain in domains[:2]:
            q = f"site:{domain} {anchor} {term}"
            if q in seen:
                continue
            seen.add(q)
            out.append(DorkQuery(query=q, category="social_post_search"))
            if len(out) >= max_queries:
                return out
    return out


def build_college_cross_post_queries(
    seed_query: str,
    hits: list[dict],
    *,
    max_queries: int = 10,
) -> list[DorkQuery]:
    """Cross-post search: college page on one host → posts on other ranked social hosts."""
    from services.evidence.google_search_intel import (
        COLLEGE_POST_CONTEXT,
        _normalize_institution_name,
        INSTITUTION_TAIL_RE,
    )
    from services.discovery.attribution import dork_hit_attributed

    anchor = _anchor(seed_query)
    out: list[DorkQuery] = []
    seen: set[str] = set()
    page_slugs: set[str] = set()
    page_names: set[str] = set()
    cross_domains = _social_domains(8)

    for hit in hits:
        url = str(hit.get("url") or "")
        if not is_priority_social_host(url):
            continue
        text = f"{hit.get('title') or ''} {hit.get('snippet') or ''}"
        if not COLLEGE_POST_CONTEXT.search(text):
            continue
        if not dork_hit_attributed(
            url=url,
            title=str(hit.get("title") or ""),
            snippet=str(hit.get("snippet") or ""),
            seed_query=seed_query,
            dork_query=str(hit.get("dork_query") or ""),
            dork_category=str(hit.get("dork_category") or ""),
        ):
            continue
        slug = profile_slug_from_url(url)
        if slug:
            page_slugs.add(slug.lower())
        title = str(hit.get("title") or "")
        if " - " in title:
            prefix = title.split(" - ", 1)[0].strip().strip('"')
            if prefix and len(prefix) >= 4:
                page_names.add(prefix)
        for match in INSTITUTION_TAIL_RE.finditer(text):
            name = _normalize_institution_name(match.group(1))
            if name:
                page_names.add(name)

    source_host = normalize_platform_host(next((str(h.get("url") or "") for h in hits if h.get("url")), ""))
    targets = [d for d in cross_domains if d != source_host][:3]

    for slug in sorted(page_slugs):
        slug_variants = {slug, slug.replace(".", "_"), slug.replace(".", "")}
        for slug_q in slug_variants:
            for domain in targets:
                for q in (
                    f"site:{domain} {anchor} {slug_q}",
                    f"site:{domain} {slug_q} hackathon",
                ):
                    if q in seen:
                        continue
                    seen.add(q)
                    out.append(DorkQuery(query=q, category="social_post_search"))
                    if len(out) >= max_queries:
                        return out

    for name in sorted(page_names):
        if len(name) < 4:
            continue
        name_q = name.replace('"', "")
        for domain in targets:
            candidates = [
                f'site:{domain} {anchor} "{name_q}"',
                f"site:{domain} {name_q} hackathon",
            ]
            if "institute" not in name_q.lower() and len(name_q.split()) <= 2:
                candidates.append(f'site:{domain} {anchor} "{name_q}" hackathon')
            for q in candidates:
                if q in seen:
                    continue
                seen.add(q)
                out.append(DorkQuery(query=q, category="social_post_search"))
                if len(out) >= max_queries:
                    return out

    return out


# Backward-compatible alias
build_college_instagram_queries = build_college_cross_post_queries


def _queries_for_keyword(anchor: str, kw: DiscoveredKeyword) -> list[tuple[str, str]]:
    phrase = kw.phrase.replace('"', "").strip()
    if not phrase:
        return []

    social_domains = _social_domains(6)
    base = [(f"{anchor} {phrase}", "serp_discovered")]
    for domain in social_domains[:2]:
        base.append((_post_search_site(domain, anchor, phrase), "social_post_search"))

    if kw.category == "achievement":
        for domain in social_domains:
            base.append((_post_search_site(domain, anchor, phrase), "serp_discovered"))
    elif kw.category == "education":
        for domain in social_domains[:2]:
            base.append((f'site:{domain} {anchor} "{phrase}"', "social_post_search"))
    elif kw.category == "organization":
        for domain in social_domains[:4]:
            base.append((f"site:{domain} {anchor} {phrase}", "serp_discovered"))
    elif kw.category == "hashtag":
        tag = phrase if phrase.startswith("#") else f"#{phrase.lstrip('#')}"
        base = [(f"{anchor} {tag}", "serp_discovered")]
        for domain in social_domains[:3]:
            base.append((_post_search_site(domain, anchor, tag), "serp_discovered"))
    elif kw.category == "professional":
        for domain in social_domains[:4]:
            base.append((f"site:{domain} {anchor} {phrase}", "serp_discovered"))

    return base


def build_dynamic_dork_queries(
    seed_query: str,
    keywords: list[DiscoveredKeyword],
    *,
    max_queries: int = 30,
) -> list[DorkQuery]:
    """
    Follow-up searches from Google highlights — social hosts from Maigret registry.
    """
    if not keywords:
        return []

    anchor = _anchor(seed_query)
    out: list[DorkQuery] = []
    seen: set[str] = set()

    actionable = sorted(
        [
            kw for kw in keywords
            if kw.category in SOCIAL_KEYWORD_CATEGORIES
            and kw.phrase.lower() not in SKIP_PHRASES
            and kw.score >= 0.72
        ],
        key=lambda k: (-k.score, -len(k.phrase)),
    )

    for kw in actionable:
        for q, cat in _queries_for_keyword(anchor, kw):
            if q in seen:
                continue
            seen.add(q)
            out.append(DorkQuery(query=q, category=cat))
            if len(out) >= max_queries:
                return out

    return out
