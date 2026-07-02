"""Parse Google dork and web documents into structured person intelligence."""

from __future__ import annotations

import re
from typing import Any

from services.discovery.attribution import context_references_seed, url_references_seed
from services.discovery.validators import is_image_url, is_plausible_profile_photo
from services.google_dorking.filters import sanitize_org_label
from services.query_detector import detect_query_type

SCHOOL_RE = re.compile(
    r"\b[\w][\w\s&'.-]{1,48}(?:University|College|Institute|School|Academy|Polytechnic)\b",
    re.IGNORECASE,
)
EVENT_KEYWORDS = (
    "hackathon", "winner", "award", "conference", "competition", "festival",
    "summit", "participated", "finalist", "champion", "runner-up", "congratulations",
    "meetup", "workshop", "seminar", "symposium", "expo", "ceremony", "keynote",
    "speaker", "webinar", "tournament", "showcase", "gala", "forum", "congress",
    "convocation", "conclave", "fest", "panel", "hosted", "organized", "attended",
    "presented", "spoke", "featured",
)
ACHIEVEMENT_KEYWORDS = (
    "winner", "award", "finalist", "champion", "runner-up", "medal", "trophy",
    "recognition", "honored", "placed", "ranked", "selected", "congratulations",
)
EVENT_NAME_PATTERNS = (
    re.compile(
        r"(?:runner-?up|winner|finalist|champion|participant|placed)\s+(?:in|of|at)\s+"
        r"([\w][\w\s&'.-]{2,58}?)(?:\s+v?\d+\.?,|$|\s+(?:compet|against|with|\.))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:congratulations|congrats)\s+(?:to|on)\s+.*?(?:in|at|for)\s+"
        r"([\w][\w\s&'.-]{2,58}?)(?:\s+v?\d|\.|,|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:award(?:ed)?|selected|qualified|honored|recognized)\s+(?:for|at|in)\s+"
        r"([A-Z][\w][\w\s&'.-]{1,58}?)(?:\s+v?\d|\.|,|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:participated|attended|spoke\s+at|presented\s+at|featured\s+at|hosted|organized)\s+"
        r"(?:in|at)?\s*([A-Z][\w][\w\s&'.-]{1,58}?)(?:\s+v?\d|\.|,|$|\s+(?:on|with))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:event|conference|meetup|workshop|seminar|summit|festival|symposium|expo|webinar|tournament)\s*[:\-]?\s*"
        r"([A-Z][\w][\w\s&'.-]{1,58}?)(?:\s+v?\d|\.|,|$)",
        re.IGNORECASE,
    ),
)
TITLE_SPLIT_RE = re.compile(r"\s*[-–|]\s*")
CONTENT_CATEGORIES = frozenset({
    "news_mentions", "blog_search", "article_search", "publications", "events_general",
})


def _extract_event_labels(text: str) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for pattern in EVENT_NAME_PATTERNS:
        for match in pattern.finditer(text):
            label = " ".join(match.group(1).split()).strip(" .,-")
            key = label.lower()
            if len(label) >= 3 and key not in seen:
                seen.add(key)
                labels.append(label)
    return labels


def _content_ref(title: str, url: str) -> str:
    return f"{title.strip()}|{url.strip()}" if title.strip() else url.strip()


def _document_text(meta: dict[str, Any]) -> str:
    parts = [
        str(meta.get("title") or ""),
        str(meta.get("snippet") or ""),
        str(meta.get("content") or ""),
        str(meta.get("text") or ""),
    ]
    return " ".join(p for p in parts if p).strip()


def _document_url(meta: dict[str, Any], fallback: str) -> str:
    return str(meta.get("url") or fallback or "")


def _extract_events(
    text: str,
    *,
    title: str,
    category: str,
    out: list[tuple[str, str, str, float]],
) -> None:
    """Pull any event tied to the username — hackathons, conferences, meetups, etc."""
    blob = text.lower()
    should_scan = (
        category in ("achievements", "events_general", "forum_mentions", "news_mentions")
        or any(k in blob for k in EVENT_KEYWORDS)
    )
    if not should_scan:
        return

    event_labels = _extract_event_labels(text)
    if not event_labels and title and len(title) >= 4:
        event_labels = [title]

    snippet_label = text[:240].strip() if text else ""
    for label in event_labels:
        out.append(("event", label, "dork_event_participation", 0.72))
        if category == "achievements" or any(k in blob for k in ACHIEVEMENT_KEYWORDS):
            out.append(("achievement", label, "dork_achievement", 0.74))
        if any(k in blob for k in ("speaker", "keynote", "panel", "presented", "spoke")):
            out.append(("appearance", label, "dork_event_appearance", 0.73))

    if snippet_label and snippet_label not in event_labels:
        out.append(("event", snippet_label, "dork_event_snippet", 0.68))


def parse_dork_document(
    meta: dict[str, Any],
    *,
    entity_value: str,
    seed_query: str,
) -> list[tuple[str, str, str, float]]:
    """Return list of (field, value, strategy, confidence) from a dork document."""
    text = _document_text(meta)
    url = _document_url(meta, entity_value)
    category = str(meta.get("dork_category") or "")
    title = str(meta.get("title") or "").strip()
    if not text and not url:
        return []

    seed_match = (
        not seed_query
        or url_references_seed(url, seed_query)
        or context_references_seed(text, seed_query=seed_query)
    )
    if seed_query and not seed_match:
        return []

    from services.evidence.search_intelligence import classify_search_hit

    hit_type = classify_search_hit(url, title=title, snippet=text)
    out: list[tuple[str, str, str, float]] = []
    seed_is_phone = detect_query_type(seed_query) == "phone"

    if hit_type == "video" or category == "media_video":
        out.append(("media_video", _content_ref(title or "Video", url), "dork_media_video", 0.78))

    if hit_type == "forum" or category in ("forum_mentions", "discussion_search"):
        out.append(("forum", _content_ref(title or "Forum", url), "dork_forum", 0.74))
        out.append(("public_link", url, "dork_forum_link", 0.72))

    if category == "discussion_search" or any(k in text.lower() for k in ("discussion", "thread", "comment", "replied")):
        out.append(("forum", _content_ref(title or "Discussion", url), "dork_discussion", 0.73))

    if hit_type == "news" or category == "news_mentions":
        out.append(("news", _content_ref(title or "News", url), "dork_news", 0.76))
        out.append(("public_link", url, "dork_news_link", 0.74))

    if hit_type == "blog" or category == "blog_search":
        out.append(("blog", _content_ref(title or "Blog", url), "dork_blog", 0.75))
        out.append(("publication", _content_ref(title or "Blog post", url), "dork_blog_publication", 0.74))

    if hit_type in ("article", "document") or (
        category in ("article_search", "publications")
        and hit_type not in ("repository", "video", "profile", "image")
    ):
        out.append(("article", _content_ref(title or "Article", url), "dork_article", 0.76))
        out.append(("publication", _content_ref(title or "Article", url), "dork_article_publication", 0.75))

    if hit_type == "repository":
        out.append(("project", title or url.rsplit("/", 1)[-1], "dork_repository", 0.74))
        out.append(("public_link", url, "dork_repository_link", 0.72))

    _extract_events(text, title=title, category=category, out=out)

    if hit_type == "profile" or category in ("documents", "profile_exact", "profile_mentions", "discovered_domain"):
        for school in SCHOOL_RE.findall(text):
            cleaned = " ".join(school.split())
            if len(cleaned) > 4:
                out.append(("school", cleaned, "dork_education", 0.7))
        if title:
            out.append(("public_link", url, "dork_profile_link", 0.75))
            if not seed_is_phone:
                parts = [p.strip() for p in TITLE_SPLIT_RE.split(title) if p.strip()]
                if parts:
                    out.append(("display_name", parts[0], "dork_profile_name", 0.72))
                if len(parts) > 1:
                    org = sanitize_org_label(parts[1])
                    if org:
                        out.append(("organization", org, "dork_profile_affiliation", 0.7))

    if hit_type in ("forum", "blog", "repository", "mention", "document"):
        ref_title = title or url
        out.append(("public_link", url, f"dork_{hit_type}_link", 0.72))
        if hit_type == "blog" and not any(f == "blog" for f, _, _, _ in out):
            out.append(("blog", _content_ref(ref_title, url), "dork_blog_hit", 0.73))
        if any(k in text.lower() for k in ACHIEVEMENT_KEYWORDS):
            for label in _extract_event_labels(text) or ([ref_title] if ref_title else []):
                out.append(("achievement", label, "dork_reference_achievement", 0.76))
            out.append(("event", text[:200] or ref_title, "dork_reference_event", 0.74))

    for school in SCHOOL_RE.findall(text):
        cleaned = " ".join(school.split())
        if len(cleaned) > 4:
            out.append(("school", cleaned, "document_education", 0.68))

    if category in ("media_images", "media_lens") and is_plausible_profile_photo(url):
        out.append(("avatar_url", url, "dork_image_discovery", 0.65))

    img_urls = re.findall(r"https?://[^\s<>\"']+\.(?:jpg|jpeg|png|webp|gif)", text, flags=re.IGNORECASE)
    for img in img_urls[:3]:
        if is_plausible_profile_photo(img):
            out.append(("avatar_url", img, "dork_image_discovery", 0.62))

    return out
