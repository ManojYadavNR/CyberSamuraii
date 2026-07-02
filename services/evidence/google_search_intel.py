"""Merge plain Google username search + dork follow-ups for the frontend."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from schemas.fusion import Entity
from services.discovery.attribution import context_references_seed, dork_hit_attributed
from services.discovery.validators import normalize_domain
from services.evidence.document_parser import SCHOOL_RE, _extract_event_labels
from services.google_dorking.filters import is_social_post_url
from services.google_dorking.keyword_discovery import (
    ACHIEVEMENT_HINT,
    COLLEGE_TITLE_PREFIX_RE,
    DiscoveredKeyword,
    HACKATHON_EVENT_RE,
    INSTITUTION_IN_TITLE_RE,
    PLACEMENT_RE,
    extract_keywords_from_serp,
)
from services.google_dorking.dynamic_queries import build_dynamic_dork_queries

FB_PAGE_POST_RE = re.compile(
    r"facebook\.com/([^/?#]+)/(?:photos|posts|videos|reel|permalink)",
    re.I,
)
COLLEGE_POST_CONTEXT = re.compile(
    r"congrat|winner|hackathon|placement|award|student|alumni|runner|fest|trophy|college|institute",
    re.I,
)
INSTITUTION_TAIL_RE = re.compile(
    r"\b([A-Z][\w\s&'.-]{2,48}(?:Institute|College|University|School|Academy|Polytechnic)"
    r"(?:\s+of\s+[A-Z][\w\s&'.-]{2,24})?)\b",
    re.I,
)
INSTITUTION_NOISE = re.compile(
    r"hackathon|winner|won|congrat|smart india|runner|finalist|placement|award|student",
    re.I,
)
BAD_COLLEGE_LABEL = re.compile(
    r"^congratulations\b|^team\b|\bsecond prize\b|\blet your food\b|^\"|"
    r"^\d|\bposition\b|problem-solving|their problem",
    re.I,
)
INSTITUTION_LABEL_RE = re.compile(
    r"institute|college|university|school|academy|polytechnic|engineering",
    re.I,
)
def _platform_key_from_url(url: str) -> str:
    from services.discovery.validators import normalize_domain

    host = normalize_domain(url)
    if host:
        return host.split(".")[0]
    return "web"


FB_RESERVED_SLUGS = frozenset({
    "www", "share", "sharer", "photo", "video", "reel", "groups", "events", "pages", "watch",
})


def _facebook_page_slug(url: str) -> str | None:
    match = FB_PAGE_POST_RE.search((url or "").lower())
    if not match:
        return None
    slug = match.group(1)
    if slug.lower() in FB_RESERVED_SLUGS:
        return None
    return slug


def _facebook_page_url(slug: str) -> str:
    return f"https://www.facebook.com/{slug.strip('/')}"


def _dork_hits_from_entities(entities: list[Entity]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for entity in entities:
        meta = entity.metadata or {}
        if meta.get("check_type") != "google_dork":
            continue
        url = str(meta.get("url") or entity.value or "")
        if not url.startswith("http"):
            continue
        hits.append({
            "title": str(meta.get("title") or ""),
            "snippet": str(meta.get("snippet") or meta.get("content") or ""),
            "url": url,
            "dork_category": str(meta.get("dork_category") or ""),
            "dork_query": str(meta.get("dork_query") or ""),
            "serp_phase": str(meta.get("serp_phase") or ""),
            "trigger_keyword": str(meta.get("trigger_keyword") or ""),
            "page_screenshot_url": meta.get("page_screenshot_url"),
            "preview_image_url": meta.get("preview_image_url"),
            "username_attributed": meta.get("username_attributed"),
        })
    return hits


def _attributed(hit: dict[str, Any], seed_query: str) -> bool:
    return dork_hit_attributed(
        url=hit["url"],
        title=hit["title"],
        snippet=hit["snippet"],
        seed_query=seed_query,
        dork_query=str(hit.get("dork_query") or ""),
        dork_category=str(hit.get("dork_category") or ""),
    )


def _clean_label(value: str, *, institution: bool = False, allow_page: bool = False) -> str | None:
    clean = " ".join(value.split()).strip(" .,-|•")
    if not clean or len(clean) < 3 or "..." in clean:
        return None
    low = clean.lower()
    if low in {"instagram", "facebook"}:
        return None
    if institution or re.search(
        r"institute|college|university|school|campus|polytechnic|academy",
        low,
    ):
        return clean if len(clean) >= 5 else None
    if allow_page and len(clean) >= 3:
        return clean
    if len(clean) < 12:
        return None
    return clean


def _is_institution_label(value: str) -> bool:
    clean = " ".join((value or "").split()).strip()
    return bool(clean) and bool(INSTITUTION_LABEL_RE.search(clean))


def _group_title_references_seed(group_hits: list[dict[str, Any]], *, seed_query: str) -> bool:
    return any(context_references_seed(h.get("title") or "", seed_query=seed_query) for h in group_hits)


def _is_bad_college_label(value: str, *, seed_query: str = "") -> bool:
    clean = " ".join(value.split()).strip()
    if not clean or len(clean) < 3:
        return True
    if BAD_COLLEGE_LABEL.search(clean):
        return True
    if seed_query and context_references_seed(clean, seed_query=seed_query):
        return True
    if not _is_institution_label(clean) and len(clean) < 12:
        return True
    return False


def _resolve_facebook_page_college(hit: dict[str, Any], slug: str, *, seed_query: str = "") -> str | None:
    title = hit.get("title") or ""
    snippet = hit.get("snippet") or ""
    if " - " not in title:
        return None
    prefix = title.split(" - ", 1)[0].strip().strip('"')
    if _is_bad_college_label(prefix, seed_query=seed_query):
        return None
    for match in INSTITUTION_TAIL_RE.finditer(f"{title} {snippet}"):
        name = _normalize_institution_name(match.group(1))
        if name:
            return name
    if INSTITUTION_LABEL_RE.search(prefix):
        return _normalize_institution_name(prefix) or prefix
    return None


def _instagram_page_handle(url: str) -> str | None:
    match = re.search(r"instagram\.com/([^/?#]+)/", url.lower())
    if not match:
        return None
    handle = match.group(1).lower()
    if handle in {"p", "reel", "tv", "explore", "accounts"}:
        return None
    return handle


def _normalize_institution_name(value: str) -> str | None:
    clean = " ".join(value.split()).strip(" .,-|•")
    if not clean:
        return None
    clean = re.sub(
        r"\s+(celebrates|is proud|wishes|congratulates|students?|campus|community).*$",
        "",
        clean,
        flags=re.I,
    )
    if INSTITUTION_NOISE.search(clean):
        match = INSTITUTION_TAIL_RE.search(clean)
        if match:
            clean = match.group(1).strip()
        else:
            return None
    return _clean_label(clean, institution=True)


def _college_names_from_hit(hit: dict[str, Any]) -> list[str]:
    title = hit.get("title") or ""
    snippet = hit.get("snippet") or ""
    url = hit.get("url") or ""
    text = f"{title} {snippet}".strip()
    names: list[str] = []
    seen: set[str] = set()

    def add(name: str, *, institution: bool = False, allow_page: bool = False) -> None:
        clean = (
            _normalize_institution_name(name)
            if institution
            else _clean_label(name, institution=institution, allow_page=allow_page)
        )
        if not clean:
            return
        key = clean.lower()
        if key in seen:
            return
        seen.add(key)
        names.append(clean)

    for match in INSTITUTION_TAIL_RE.finditer(snippet or title):
        add(match.group(1), institution=True)
    for school in SCHOOL_RE.findall(snippet or title):
        add(school, institution=True)

    if " - " in title:
        left, right = title.split(" - ", 1)
        for inst in INSTITUTION_IN_TITLE_RE.findall(right):
            add(inst, institution=True)
        if COLLEGE_POST_CONTEXT.search(text):
            add(left, allow_page=True)

    prefix = COLLEGE_TITLE_PREFIX_RE.match(title)
    if prefix and COLLEGE_POST_CONTEXT.search(text):
        add(prefix.group(1), allow_page=True)

    slug = _facebook_page_slug(url)
    if slug and COLLEGE_POST_CONTEXT.search(text) and " - " in title:
        add(title.split(" - ", 1)[0].strip(), allow_page=True)

    return names


def _placement_from_text(text: str) -> str:
    match = PLACEMENT_RE.search(text)
    if not match:
        return "mentioned"
    return match.group(1).lower().replace(" ", "_")


def _extract_hackathon_wins(hits: list[dict[str, Any]], *, seed_query: str) -> list[dict[str, Any]]:
    wins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        if not _attributed(hit, seed_query):
            continue
        text = f"{hit['title']} {hit['snippet']}".strip()
        if not ACHIEVEMENT_HINT.search(text):
            continue
        placement = _placement_from_text(text)
        preview = hit.get("page_screenshot_url") or hit.get("preview_image_url")
        candidates: list[str] = []
        candidates.extend(_extract_event_labels(text))
        for match in HACKATHON_EVENT_RE.finditer(text):
            candidates.append(match.group(1).strip())
        for kw in re.findall(r"(?:in|at|for)\s+([\w][\w\s\d.]{3,48}(?:fest|hackathon|hack)\b[\w\s\d.]*)", text, re.I):
            candidates.append(kw.strip())
        for name in candidates:
            clean = _clean_label(" ".join(name.split()).strip(" .,-") or "")
            if not clean:
                continue
            key = clean.lower()
            if key in seen:
                continue
            if not (HACKATHON_EVENT_RE.search(clean) or "hack" in key or "fest" in key):
                continue
            seen.add(key)
            wins.append({
                "hackathon": clean,
                "placement": placement,
                "title": hit["title"] or clean,
                "url": hit["url"],
                "snippet": hit["snippet"][:400],
                "platform": "facebook" if "facebook.com" in hit["url"].lower() else (
                    "instagram" if "instagram.com" in hit["url"].lower() else "web"
                ),
                "preview_url": str(preview) if preview else "",
                "source": hit.get("trigger_keyword") or "google_search",
            })
    return wins


def _extract_colleges(hits: list[dict[str, Any]], *, seed_query: str) -> list[dict[str, Any]]:
    """One row per college Facebook page (or Instagram handle), with best institution label."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        if not _attributed(hit, seed_query):
            continue
        url = hit["url"]
        if "facebook.com" not in url.lower() and "instagram.com" not in url.lower():
            continue
        text = f"{hit['title']} {hit['snippet']}".strip()
        if not COLLEGE_POST_CONTEXT.search(text):
            continue
        slug = _facebook_page_slug(url)
        if slug:
            key = f"fb:{slug.lower()}"
        elif "instagram.com" in url.lower():
            handle = _instagram_page_handle(url)
            blob = text.lower()
            if not handle and not re.search(r"@[\w.]+", blob):
                continue
            key = f"ig:{handle or url.lower()}"
        else:
            continue
        groups.setdefault(key, []).append(hit)

    colleges: list[dict[str, Any]] = []
    fb_slugs: dict[str, str] = {}
    for key, group_hits in groups.items():
        if not key.startswith("fb:"):
            continue
        if not _group_title_references_seed(group_hits, seed_query=seed_query):
            continue
        slug = key.split(":", 1)[1]
        combined = " ".join(f"{h.get('title') or ''} {h.get('snippet') or ''}" for h in group_hits)
        best_name: str | None = None
        for hit in group_hits:
            snippet = str(hit.get("snippet") or "")
            for match in INSTITUTION_TAIL_RE.finditer(snippet):
                candidate = _normalize_institution_name(match.group(1))
                if candidate and not _is_bad_college_label(candidate, seed_query=seed_query):
                    best_name = candidate
                    break
            if best_name:
                break
        if not best_name:
            for match in INSTITUTION_TAIL_RE.finditer(combined):
                candidate = _normalize_institution_name(match.group(1))
                if candidate and not _is_bad_college_label(candidate, seed_query=seed_query):
                    best_name = candidate
                    break
        if not best_name:
            for hit in group_hits:
                best_name = _resolve_facebook_page_college(hit, slug, seed_query=seed_query)
                if best_name:
                    break
        if best_name and not _is_bad_college_label(best_name, seed_query=seed_query):
            fb_slugs[slug] = best_name

    for key, group_hits in groups.items():
        if not _group_title_references_seed(group_hits, seed_query=seed_query):
            continue
        combined = " ".join(f"{h.get('title') or ''} {h.get('snippet') or ''}" for h in group_hits)
        best_name: str | None = None
        slug = key.split(":", 1)[1] if key.startswith("fb:") else ""

        if key.startswith("ig:"):
            handle = slug
            linked = False
            for fb_slug, fb_name in fb_slugs.items():
                if fb_slug in combined.lower() or fb_slug.replace(".", "") in combined.lower():
                    linked = True
                    best_name = fb_name
                    break
                if handle and (handle == fb_slug or handle.replace("_", ".") == fb_slug):
                    linked = True
                    best_name = fb_name
                    break
                if fb_name.lower() in combined.lower():
                    linked = True
                    best_name = fb_name
                    break
            if not linked:
                continue
        else:
            best_name = fb_slugs.get(slug)
            if not best_name:
                for match in INSTITUTION_TAIL_RE.finditer(combined):
                    candidate = _normalize_institution_name(match.group(1))
                    if candidate and not _is_bad_college_label(candidate, seed_query=seed_query):
                        best_name = candidate
                        break
                if not best_name:
                    for hit in group_hits:
                        best_name = _resolve_facebook_page_college(hit, slug, seed_query=seed_query)
                        if best_name:
                            break
            if not best_name and slug:
                for hit in group_hits:
                    title = str(hit.get("title") or "")
                    if " - " in title:
                        prefix = title.split(" - ", 1)[0].strip().strip('"')
                        if prefix and not _is_bad_college_label(prefix, seed_query=seed_query):
                            if not context_references_seed(prefix, seed_query=seed_query):
                                best_name = prefix
                                break
                if not best_name:
                    best_name = slug.replace(".", " ").replace("_", " ").strip()

        if not best_name or _is_bad_college_label(best_name, seed_query=seed_query):
            continue

        group_hits.sort(
            key=lambda h: (
                0 if h.get("preview_image_url") or h.get("page_screenshot_url") else 1,
                0 if "congrat" in f"{h.get('title') or ''} {h.get('snippet') or ''}".lower() else 1,
            ),
        )
        hit = group_hits[0]
        url = hit["url"]
        preview = hit.get("page_screenshot_url") or hit.get("preview_image_url")
        page_url = _facebook_page_url(slug) if slug else url
        page_name = ""
        if " - " in (hit.get("title") or ""):
            page_name = (hit["title"].split(" - ", 1)[0] or "").strip().strip('"')

        colleges.append({
            "college": best_name,
            "facebook_slug": slug if key.startswith("fb:") else "",
            "page_name": page_name or best_name,
            "page_url": page_url,
            "title": hit["title"] or best_name,
            "url": url,
            "snippet": hit["snippet"][:400],
            "platform": "facebook" if "facebook.com" in url.lower() else "instagram",
            "preview_url": str(preview) if preview else "",
        })

    colleges.sort(key=lambda c: (0 if c.get("platform") == "facebook" else 1, c["college"]))
    return colleges


def _is_social_highlight(row: dict[str, Any]) -> bool:
    platform = str(row.get("platform") or "")
    url = str(row.get("url") or "")
    if platform not in ("facebook", "instagram"):
        return False
    if is_social_post_url(url):
        return True
    if platform == "instagram" and re.search(r"instagram\.com/(?:p|reel|tv)/", url, re.I):
        return True
    return False


def _extract_employment(hits: list[dict[str, Any]], *, seed_query: str) -> list[dict[str, Any]]:
    """LinkedIn / professional SERP hits for current employer context."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        if not _attributed(hit, seed_query):
            continue
        url = hit["url"].lower()
        text = f"{hit['title']} {hit['snippet']}".strip()
        if "linkedin.com" not in url and not re.search(
            r"developer|engineer|works at|working at|employed|experience|company",
            text,
            re.I,
        ):
            continue
        preview = hit.get("page_screenshot_url") or hit.get("preview_image_url")
        org = ""
        if " - " in (hit.get("title") or ""):
            parts = hit["title"].split(" - ")
            for part in parts:
                cleaned = _clean_label(part, institution=False)
                if cleaned and not re.search(r"linkedin|profile|sign in", cleaned, re.I):
                    org = cleaned
                    break
        for match in re.finditer(
            r"(?:works?\s+at|working\s+at|employed\s+(?:at|by)|experience\s+at)\s+"
            r"([\w][\w\s&'.-]{2,56})",
            text,
            re.I,
        ):
            org = match.group(1).strip()
            break
        if not org:
            continue
        key = org.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "employer": org,
            "title": hit["title"] or org,
            "url": hit["url"],
            "snippet": hit["snippet"][:400],
            "platform": "linkedin" if "linkedin.com" in url else "web",
            "preview_url": str(preview) if preview else "",
        })
    return rows


def _highlight_from_hit(hit: dict[str, Any], *, seed_query: str) -> dict[str, Any] | None:
    if not _attributed(hit, seed_query):
        return None

    url = hit["url"]
    title = hit["title"]
    snippet = hit["snippet"]
    url_low = url.lower()
    platform = _platform_key_from_url(url)

    blob = f"{title} {snippet}".lower()
    if hit.get("trigger_keyword"):
        topic = hit["trigger_keyword"]
    elif any(k in blob for k in ("hackathon", "winner", "runner-up", "award", "trophy")):
        topic = "achievement"
    elif any(k in blob for k in ("college", "university", "institute", "school")):
        topic = "education"
    elif any(k in blob for k in ("developer", "engineer", "experience", "company")):
        topic = "professional"
    else:
        topic = hit.get("dork_category") or "general"

    preview = hit.get("page_screenshot_url") or hit.get("preview_image_url")

    return {
        "title": title or url,
        "url": url,
        "snippet": snippet[:500],
        "platform": platform,
        "topic": topic,
        "serp_phase": hit.get("serp_phase") or "follow_up",
        "trigger_keyword": hit.get("trigger_keyword") or "",
        "preview_url": str(preview) if preview else "",
    }


def build_google_search_intel(
    entities: list[Entity],
    *,
    seed_query: str,
    discovery_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merged Google username search intelligence for UI."""
    hits = _dork_hits_from_entities(entities)
    seed_hits = [
        h for h in hits
        if h.get("serp_phase") in ("seed", "social_pass1", "social_pass2", "social_college_ig", "social_campus_pass")
        or h.get("dork_category") in ("google_plain", "profile_exact", "achievements", "serp_discovered")
    ]

    keywords: list[DiscoveredKeyword]
    if discovery_meta and discovery_meta.get("discovered_keywords"):
        keywords = [
            DiscoveredKeyword(
                phrase=str(k.get("phrase") or ""),
                category=str(k.get("category") or "general"),
                source_url=str(k.get("source_url") or ""),
                source_title=str(k.get("source_title") or ""),
                source_snippet=str(k.get("source_snippet") or ""),
                score=float(k.get("score") or 0.5),
            )
            for k in discovery_meta["discovered_keywords"]
            if k.get("phrase")
        ]
    else:
        keywords = extract_keywords_from_serp(hits[:24], seed_query=seed_query)

    follow_up = build_dynamic_dork_queries(seed_query, keywords)
    follow_up_queries = [d.query for d in follow_up]

    highlights: list[dict[str, Any]] = []
    google_highlights: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for hit in hits:
        row = _highlight_from_hit(hit, seed_query=seed_query)
        if not row or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        highlights.append(row)
        if hit.get("serp_phase") == "seed" or hit.get("dork_category") in ("google_plain", "profile_exact", "achievements"):
            google_highlights.append(row)

    highlights.sort(
        key=lambda h: (
            0 if h["platform"] in ("facebook", "instagram") and is_social_post_url(h["url"]) else 1,
            0 if h["platform"] in ("facebook", "instagram") else 2,
            0 if h.get("preview_url") else 3,
            0 if h["serp_phase"] == "seed" else 4,
        ),
    )

    social_posts = [h for h in highlights if _is_social_highlight(h)]
    instagram_posts = [h for h in social_posts if h["platform"] == "instagram"]
    facebook_posts = [h for h in social_posts if h["platform"] == "facebook"]

    hackathon_wins = _extract_hackathon_wins(hits, seed_query=seed_query)
    colleges = _extract_colleges(hits, seed_query=seed_query)
    employment = _extract_employment(hits, seed_query=seed_query)

    return {
        "discovered_keywords": [k.to_dict() for k in keywords],
        "follow_up_queries": follow_up_queries,
        "seed_hit_count": len(seed_hits),
        "google_highlights": google_highlights[:12],
        "hackathon_wins": hackathon_wins[:8],
        "colleges": colleges[:6],
        "employment": employment[:6],
        "highlights": highlights[:24],
        "social_posts": social_posts[:12],
        "instagram_posts": instagram_posts[:8],
        "facebook_posts": facebook_posts[:8],
    }


def _append_unique_str(target: list[str], value: str) -> None:
    cleaned = " ".join(str(value).split()).strip()
    if cleaned and len(cleaned) > 2 and cleaned not in target:
        target.append(cleaned)


def _entity_platform_key(entity: Entity) -> str:
    meta = entity.metadata or {}
    url = str(meta.get("url") or entity.value or "")
    if url.startswith("http"):
        return _platform_key_from_url(url)
    platform = str(meta.get("platform") or "")
    from services.discovery.validators import normalize_domain

    host = normalize_domain(platform)
    if host:
        return host.split(".")[0]
    return platform.lower().split(".")[0] if platform else "unknown"


def _college_matches_account(entity: Entity, college: dict[str, Any]) -> bool:
    meta = entity.metadata or {}
    account_url = str(meta.get("url") or entity.value or "").lower().rstrip("/")
    if not account_url:
        return False
    for key in ("facebook_page_url", "url", "page_url"):
        page = str(college.get(key) or "").lower().rstrip("/")
        if page and (page in account_url or account_url in page):
            return True
    slug = str(college.get("facebook_slug") or "").strip().lower()
    return bool(slug and slug in account_url)


def _account_matches_seed(entity: Entity, seed_query: str) -> bool:
    if not seed_query:
        return True
    from services.discovery.attribution import account_handle_matches_seed

    meta = entity.metadata or {}
    url = str(meta.get("url") or entity.value or "")
    for key in ("username", "handle"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip() and account_handle_matches_seed(val.strip(), seed_query, url):
            return True
    if ":" in entity.value and not entity.value.startswith("http"):
        part = entity.value.split(":", 1)[1].strip()
        if part and account_handle_matches_seed(part, seed_query, url):
            return True
    return False


def _snippet_from_intel_row(row: dict[str, Any]) -> str:
    parts = [str(row.get("title") or ""), str(row.get("snippet") or ""), str(row.get("hackathon") or ""), str(row.get("college") or "")]
    return " ".join(p for p in parts if p).strip()


def person_fields_from_google_intel(
    google_intel: dict[str, Any],
    *,
    seed_query: str,
) -> list[Any]:
    """Person-level education/achievement fields — not duplicated on every platform card."""
    from schemas.evidence import FieldProvenance

    fields: list[FieldProvenance] = []
    seen: set[tuple[str, str]] = set()

    def add(field: str, value: str, strategy: str, confidence: float = 0.82) -> None:
        clean = " ".join(str(value).split()).strip()
        if not clean:
            return
        key = (field, clean.lower())
        if key in seen:
            return
        seen.add(key)
        fields.append(
            FieldProvenance(
                field=field,
                value=clean,
                source_platform="google_search",
                source_tool="google_search_intel",
                extraction_strategy=strategy,
                confidence=confidence,
            )
        )

    for college in google_intel.get("colleges") or []:
        name = str(college.get("official_name") or college.get("college") or "").strip()
        if name and not _is_bad_college_label(name, seed_query=seed_query):
            add("education", name, "google_college_intel", 0.88)
        page_url = str(college.get("page_url") or college.get("url") or "").strip()
        if page_url:
            add("public_link", page_url, "google_college_page", 0.8)
        ig_url = str(college.get("instagram_url") or "").strip()
        if ig_url:
            add("public_link", ig_url, "google_college_instagram", 0.78)
        web_url = str(college.get("website_url") or "").strip()
        if web_url:
            add("website", web_url, "google_college_website", 0.8)

    for win in google_intel.get("hackathon_wins") or []:
        snippet = _snippet_from_intel_row(win)
        if snippet:
            add("achievement", snippet[:500], "google_hackathon_intel", 0.86)

    return fields


def merge_search_intel_onto_accounts(
    entities: list[Entity],
    google_intel: dict[str, Any],
    *,
    seed_query: str,
) -> int:
    """
    Copy platform-matched SERP posts onto a few social accounts for correlation.
    Global hackathon/college intel stays on google_search_intel + person-level fields.
    """
    from services.account_confirmation import account_confirmed

    if not google_intel:
        return 0

    enriched = 0
    social_posts = google_intel.get("social_posts") or []
    hackathon_wins = google_intel.get("hackathon_wins") or []
    colleges = google_intel.get("colleges") or []

    for entity in entities:
        if entity.type != "account":
            continue
        meta = dict(entity.metadata or {})
        if not account_confirmed(meta, set(entity.sources)):
            continue
        if seed_query and not _account_matches_seed(entity, seed_query):
            continue

        platform_key = _entity_platform_key(entity)
        touched = False

        for college in colleges:
            if not _college_matches_account(entity, college):
                continue
            label = str(college.get("official_name") or college.get("college") or "").strip()
            if label and not _is_bad_college_label(label, seed_query=seed_query):
                _append_unique_str(meta.setdefault("schools", []), label)
                touched = True

        for win in hackathon_wins:
            win_platform = str(win.get("platform") or "web").lower()
            win_url = str(win.get("url") or "")
            win_key = _platform_key_from_url(win_url) if win_url.startswith("http") else win_platform
            if win_platform not in {platform_key, "web"} and win_key != platform_key:
                continue
            snippet = _snippet_from_intel_row(win)
            if snippet:
                _append_unique_str(meta.setdefault("achievements", []), snippet)
                touched = True

        for post in social_posts:
            post_platform = str(post.get("platform") or "").lower()
            post_url = str(post.get("url") or "")
            post_key = _platform_key_from_url(post_url) if post_url.startswith("http") else post_platform
            if post_platform and post_platform not in {platform_key, "web"} and post_key != platform_key:
                continue
            snippet = _snippet_from_intel_row(post)
            if snippet:
                _append_unique_str(meta.setdefault("recent_posts", []), snippet)
                _append_unique_str(meta.setdefault("social_posts", []), snippet)
                touched = True

        if touched:
            meta["correlation_intel_merged"] = True
            entity.metadata = meta
            enriched += 1

    return enriched


_PROFILE_PATH_RE = re.compile(r"^/[@~]?[\w.-]{2,32}(?:/[\w.-]+)?/?$")


def _looks_like_profile_url(url: str) -> bool:
    from services.discovery.validators import GENERIC_PATH_SEGMENTS, normalize_domain
    from services.google_dorking.filters import is_social_post_url

    if is_social_post_url(url):
        return False
    parsed = urlparse(url)
    if not normalize_domain(url):
        return False
    path = parsed.path.strip("/")
    if not path:
        return False
    segments = [s.lower().lstrip("@~") for s in path.split("/") if s]
    if not segments or segments[0] in GENERIC_PATH_SEGMENTS:
        return False
    return bool(_PROFILE_PATH_RE.match("/" + "/".join(segments[:2])))


def promote_attributed_profile_documents(
    entities: list[Entity],
    *,
    seed_query: str,
) -> int:
    """Turn high-confidence attributed profile SERP hits into account entities."""
    from schemas.fusion import Entity as EntityModel
    from services.fusion_engine import _make_entity, deduplicate_entities, entity_key

    if not seed_query.strip():
        return 0

    existing = {
        entity_key(e.type, e.canonical_value or e.value)
        for e in entities
        if e.type == "account"
    }
    promoted: list[Entity] = []
    for entity in entities:
        if entity.type != "document":
            continue
        meta = entity.metadata or {}
        if meta.get("check_type") != "google_dork":
            continue
        url = str(meta.get("url") or entity.value or "")
        if not _looks_like_profile_url(url):
            continue
        if not _attributed({
            "url": url,
            "title": str(meta.get("title") or ""),
            "snippet": str(meta.get("snippet") or meta.get("content") or ""),
            "dork_category": str(meta.get("dork_category") or ""),
            "dork_query": str(meta.get("dork_query") or ""),
        }, seed_query):
            continue
        domain = normalize_domain(url) or "web"
        from services.correlation.handle_quality import is_correlatable_handle, normalize_profile_handle

        handle = normalize_profile_handle(url, domain, meta)
        if not handle or not is_correlatable_handle(handle, seed_query, url):
            continue
        if re.fullmatch(r"\d+", handle):
            continue
        if re.search(r"facebook\.com/.+/(?:photos|posts|videos)", url, re.I):
            continue
        key = entity_key("account", normalize_domain(url) and f"{normalize_domain(url)}:{handle}" or url)
        if key in existing:
            continue
        account_meta = {
            **meta,
            "url": url,
            "platform": domain,
            "username": handle,
            "handle": handle,
            "verified": False,
            "investigation_lead": True,
            "registered": None,
            "check_type": "google_dork_profile",
            "corroboration_status": "lead",
            "status": "search_profile",
            "live_profile_verified": None,
            "live_verify_reason": "dork_profile_lead",
        }
        val = f"{domain}:{handle}"
        promoted.append(_make_entity("account", val, "google_dorking", account_meta))
        existing.add(key)

    if not promoted:
        return 0
    merged = deduplicate_entities([*entities, *promoted])
    entities.clear()
    entities.extend(merged)
    return len(promoted)
