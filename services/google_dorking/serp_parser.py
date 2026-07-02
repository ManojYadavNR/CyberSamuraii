"""Parse search-engine hits the way a Google results page presents them."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from services.discovery.attribution import dork_hit_attributed, extract_phones_from_text
from services.discovery.validators import extract_emails_from_text, extract_urls_from_text, is_image_url, is_plausible_profile_photo, normalize_domain
from services.evidence.document_parser import parse_dork_document
from services.evidence.search_intelligence import classify_search_hit
from services.google_dorking.filters import is_junk_dork_url, dork_hit_displayable, is_social_post_url

IMAGE_URL_RE = re.compile(
    r"https?://[^\s<>\"']+\.(?:jpg|jpeg|png|webp|gif|bmp)(?:\?[^\s<>\"']*)?",
    re.IGNORECASE,
)


def _display_link(url: str, fallback: str = "") -> str:
    if fallback:
        return fallback
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = parsed.path.strip("/")
    if path and len(path) <= 48:
        return f"{host} › {path.split('/')[0]}"
    return host or url


def build_serp_record(
    *,
    title: str,
    url: str,
    snippet: str,
    dork_query: str,
    dork_category: str,
    source: str = "",
    display_link: str = "",
) -> dict[str, Any]:
    """Structured record mirroring a Google SERP result card."""
    hit_type = classify_search_hit(url, title, snippet)
    text_blob = f"{title} {snippet}".strip()
    return {
        "serp_title": title,
        "serp_url": url,
        "serp_snippet": snippet,
        "serp_display_link": display_link or _display_link(url),
        "serp_hit_type": hit_type,
        "serp_dork_category": dork_category,
        "serp_dork_query": dork_query,
        "serp_source_engine": source or "web_search",
        "serp_text_blob": text_blob,
    }


def extract_hit_intelligence(
    *,
    title: str,
    url: str,
    snippet: str,
    dork_category: str,
    seed_query: str,
) -> dict[str, Any]:
    """Pull emails, phones, images, events, articles, blogs, forums from one hit."""
    text_blob = f"{title} {snippet}".strip()
    hit_type = classify_search_hit(url, title, snippet)

    doc_fields = parse_dork_document(
        {
            "title": title,
            "snippet": snippet,
            "content": text_blob,
            "url": url,
            "dork_category": dork_category,
        },
        entity_value=url,
        seed_query=seed_query,
    )

    structured: dict[str, list[str]] = {
        "emails": [],
        "phones": [],
        "images": [],
        "events": [],
        "achievements": [],
        "articles": [],
        "blogs": [],
        "forums": [],
        "news": [],
        "videos": [],
        "public_links": [],
        "discussions": [],
    }

    for field, value, _strategy, _conf in doc_fields:
        if field == "email" and value not in structured["emails"]:
            structured["emails"].append(value)
        elif field == "phone" and value not in structured["phones"]:
            structured["phones"].append(value)
        elif field in ("avatar_url", "image") and value not in structured["images"]:
            structured["images"].append(value)
        elif field == "event" and value not in structured["events"]:
            structured["events"].append(value)
        elif field == "achievement" and value not in structured["achievements"]:
            structured["achievements"].append(value)
        elif field in ("article", "publication") and value not in structured["articles"]:
            structured["articles"].append(value)
        elif field == "blog" and value not in structured["blogs"]:
            structured["blogs"].append(value)
        elif field == "news" and value not in structured["news"]:
            structured["news"].append(value)
        elif field == "media_video" and value not in structured["videos"]:
            structured["videos"].append(value)
        elif field == "public_link" and value not in structured["public_links"]:
            structured["public_links"].append(value)

    if hit_type == "forum" or dork_category in ("forum_mentions", "discussion_search"):
        ref = f"{title}|{url}" if title else url
        if ref not in structured["forums"]:
            structured["forums"].append(ref)
    if dork_category == "discussion_search" or any(k in text_blob.lower() for k in ("discussion", "thread", " replied ", "comment")):
        ref = f"{title}|{url}" if title else url
        if ref not in structured["discussions"]:
            structured["discussions"].append(ref)
    if hit_type == "blog" and not structured["blogs"]:
        structured["blogs"].append(f"{title or 'Blog'}|{url}")
    if hit_type in ("article", "document") and not structured["articles"]:
        structured["articles"].append(f"{title or 'Article'}|{url}")
    if hit_type == "news" and not structured["news"]:
        structured["news"].append(f"{title or 'News'}|{url}")
    if hit_type == "image" or dork_category.startswith("media_images"):
        if is_plausible_profile_photo(url) or is_image_url(url):
            if url not in structured["images"]:
                structured["images"].append(url)

    for email in extract_emails_from_text(text_blob):
        if email not in structured["emails"]:
            structured["emails"].append(email)
    for phone in extract_phones_from_text(text_blob):
        if phone not in structured["phones"]:
            structured["phones"].append(phone)
    for img in IMAGE_URL_RE.findall(text_blob):
        if is_plausible_profile_photo(img) and img not in structured["images"]:
            structured["images"].append(img)
    for extra_url in extract_urls_from_text(text_blob)[:8]:
        if is_junk_dork_url(extra_url):
            continue
        extra_type = classify_search_hit(extra_url, title, snippet)
        if extra_type == "image" and is_plausible_profile_photo(extra_url):
            if extra_url not in structured["images"]:
                structured["images"].append(extra_url)

    return {
        "hit_type": hit_type,
        "structured_intelligence": structured,
        "parsed_fields": [
            {"field": f, "value": v, "strategy": s, "confidence": c}
            for f, v, s, c in doc_fields
        ],
    }


def process_search_hit(
    hit: dict[str, Any],
    *,
    seed_query: str,
    query_type: str,
) -> dict[str, Any] | None:
    """Validate attribution and return merged SERP + intelligence payload."""
    url = str(hit.get("url") or "").strip()
    if url:
        from services.social_urls import fix_facebook_post_url
        url = fix_facebook_post_url(url)
    if not url or is_junk_dork_url(url):
        return None

    title = str(hit.get("title") or "")
    snippet = str(hit.get("snippet") or "")
    category = str(hit.get("dork_category") or "general")
    dork = str(hit.get("dork_query") or "")
    if category == "social_post_search":
        if not is_social_post_url(url):
            return None

    from services.discovery.attribution import context_references_seed
    from services.google_dorking.filters import is_college_homepage_url

    if is_college_homepage_url(url) and not context_references_seed(title, snippet, seed_query=seed_query):
        return None

    if query_type == "username" and not dork_hit_displayable(
        url=url,
        title=title,
        snippet=snippet,
        seed_query=seed_query,
        dork_category=category,
        dork_query=dork,
    ):
        return None

    if query_type == "phone":
        from services.google_dorking.filters import phone_dork_hit_displayable

        if not phone_dork_hit_displayable(
            url=url,
            title=title,
            snippet=snippet,
            seed_query=seed_query,
        ):
            return None
    serp = build_serp_record(
        title=title,
        url=url,
        snippet=snippet,
        dork_query=dork,
        dork_category=category,
        source=str(hit.get("source") or ""),
        display_link=str(hit.get("display_link") or ""),
    )
    intel = extract_hit_intelligence(
        title=title,
        url=url,
        snippet=snippet,
        dork_category=category,
        seed_query=seed_query,
    )
    platform = normalize_domain(url) or serp["serp_display_link"] or "google_search"
    attributed = dork_hit_attributed(
        url=url, title=title, snippet=snippet, seed_query=seed_query,
        dork_query=dork, dork_category=category,
    )

    return {
        "platform": platform,
        "url": url,
        "title": title,
        "snippet": snippet,
        "dork_query": dork,
        "dork_category": category,
        "username_attributed": attributed,
        **serp,
        **intel,
    }
