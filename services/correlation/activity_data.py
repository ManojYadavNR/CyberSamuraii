"""Harvest activity signals from entity metadata for behavioral correlation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

HASHTAG_RE = re.compile(r"#[\w\u0080-\uFFFF]{2,}", re.UNICODE)
ISO_DATETIME_RE = re.compile(
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})[T\s](\d{1,2}):(\d{2})",
)
TIME_ONLY_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DATE_ONLY_RE = re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b")

POST_LIST_KEYS = (
    "recent_posts",
    "highlights",
    "post_captions",
    "captions",
    "social_posts",
    "posts",
)
POST_FIELD_NAMES = frozenset(
    {"recent_post", "post", "caption", "achievement", "project", "video", "media_video"}
)
TIMESTAMP_KEYS = (
    "posting_times",
    "post_times",
    "activity_hours",
    "created_at",
    "published_at",
    "last_active",
    "updated_at",
)
TOPIC_LIST_KEYS = ("achievements", "projects", "schools", "organizations", "organization")


def _append_unique(target: list[str], value: str) -> None:
    cleaned = " ".join(str(value).split()).strip()
    if cleaned and len(cleaned) > 2 and cleaned not in target:
        target.append(cleaned)


def _from_extracted_fields(meta: dict[str, Any], posts: list[str], topics: list[str]) -> None:
    extracted = meta.get("extracted_intelligence")
    if not isinstance(extracted, dict):
        return
    for item in extracted.get("extracted_fields") or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "")
        value = item.get("value")
        if not isinstance(value, str) or not value.strip():
            continue
        if field in POST_FIELD_NAMES or field in ("achievement", "project", "school", "organization"):
            if field in ("achievement", "project", "school", "organization"):
                _append_unique(topics, value)
            else:
                _append_unique(posts, value)


def _from_google_discovery(meta: dict[str, Any], posts: list[str], topics: list[str]) -> None:
    for container_key in ("google_search_discovery", "google_search_intel"):
        discovery = meta.get(container_key)
        if not isinstance(discovery, dict):
            continue
        for key in ("social_posts", "highlights", "hackathon_wins", "colleges"):
            val = discovery.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        _append_unique(posts if key in ("social_posts", "highlights") else topics, item)
                    elif isinstance(item, dict):
                        text = (
                            item.get("title")
                            or item.get("snippet")
                            or item.get("text")
                            or item.get("hackathon")
                            or item.get("college")
                        )
                        if isinstance(text, str):
                            target = posts if key in ("social_posts", "highlights", "hackathon_wins") else topics
                            _append_unique(target, text)
                        snippet = item.get("snippet")
                        if isinstance(snippet, str) and key in ("hackathon_wins", "colleges"):
                            _append_unique(posts, snippet)


def collect_post_snippets(meta: dict[str, Any]) -> list[str]:
    """Post captions, comments, and activity text — not bios."""
    posts: list[str] = []
    for key in POST_LIST_KEYS:
        val = meta.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    _append_unique(posts, item)
                elif isinstance(item, dict):
                    for sub in ("text", "caption", "content", "body", "title", "snippet"):
                        sub_val = item.get(sub)
                        if isinstance(sub_val, str):
                            _append_unique(posts, sub_val)
        elif isinstance(val, str) and val.strip():
            _append_unique(posts, val)

    _from_extracted_fields(meta, posts, [])
    for key in ("social_posts",):
        val = meta.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    _append_unique(posts, item)
    return posts


def collect_topic_labels(meta: dict[str, Any]) -> list[str]:
    """Organizations, schools, projects, achievements for topic overlap."""
    topics: list[str] = []
    for key in TOPIC_LIST_KEYS:
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            _append_unique(topics, val)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.strip():
                    _append_unique(topics, item)
    _from_extracted_fields(meta, [], topics)
    _from_google_discovery(meta, [], topics)
    for key in ("achievements", "schools"):
        val = meta.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    _append_unique(topics, item)
    return topics


def extract_hashtags(texts: list[str]) -> list[str]:
    tags: list[str] = []
    for text in texts:
        for match in HASHTAG_RE.findall(text):
            tag = match.lower()
            if tag not in tags:
                tags.append(tag)
    return tags


def _hour_from_token(token: str) -> int | None:
    token = token.strip()
    if not token:
        return None
    iso = ISO_DATETIME_RE.search(token)
    if iso:
        return int(iso.group(2)) % 24
    time_only = TIME_ONLY_RE.search(token)
    if time_only:
        return int(time_only.group(1)) % 24
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(token[:19], fmt)
            return parsed.hour
        except ValueError:
            continue
    date_only = DATE_ONLY_RE.search(token)
    if date_only:
        return None
    return None


def collect_timestamps(meta: dict[str, Any], posts: list[str]) -> list[str]:
    """Raw timestamps and normalized HH:00 slots from metadata and post objects."""
    raw: list[str] = []
    for key in TIMESTAMP_KEYS:
        val = meta.get(key)
        if isinstance(val, list):
            raw.extend(str(v) for v in val if v)
        elif val is not None and str(val).strip():
            raw.append(str(val).strip())

    public = meta.get("public_metadata")
    if isinstance(public, dict):
        for key in TIMESTAMP_KEYS:
            val = public.get(key)
            if val is not None and str(val).strip():
                raw.append(str(val).strip())

    for key in POST_LIST_KEYS:
        val = meta.get(key)
        if not isinstance(val, list):
            continue
        for item in val:
            if isinstance(item, dict):
                for sub in ("timestamp", "created_at", "published_at", "date", "time"):
                    sub_val = item.get(sub)
                    if sub_val is not None:
                        raw.append(str(sub_val))

    slots: list[str] = []
    for token in raw:
        hour = _hour_from_token(token)
        if hour is not None:
            slot = f"{hour:02d}:00"
            if slot not in slots:
                slots.append(slot)
    return slots or raw


def infer_activity_windows(timestamps: list[str]) -> list[str]:
    """Classify activity into business_hours, evening, or night_owl."""
    windows: set[str] = set()
    for token in timestamps:
        hour = _hour_from_token(token)
        if hour is None:
            continue
        if 9 <= hour < 17:
            windows.add("business_hours")
        elif 17 <= hour < 22:
            windows.add("evening")
        else:
            windows.add("night_owl")
    return sorted(windows)


def build_behavior_corpus(posts: list[str], hashtags: list[str]) -> str:
    """Account-specific post activity only — no shared SERP topic labels."""
    parts = list(posts)
    parts.extend(hashtags)
    return " ".join(parts).strip()
