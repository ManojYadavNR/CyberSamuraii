"""Fetch Instagram post timestamps via Apify instagram-posts-scraper-pro."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from services.apify.instagram_comments import apify_configured, shortcode_from_post_url

logger = logging.getLogger(__name__)

APIFY_ACTOR = os.getenv("APIFY_IG_POSTS_ACTOR", "nH2AHrwxeTRJoN5hX")
APIFY_SYNC_URL = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
DEFAULT_RESULTS_LIMIT = 20
DEFAULT_TIMEOUT_SEC = 180
MAX_RESULTS_LIMIT = 100

_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_WEEKDAY_LABELS_SUN_FIRST = ["Sun", "Sat", "Fri", "Thu", "Wed", "Tue", "Mon"]
_HOUR_TICKS = [0, 3, 6, 9, 12, 15, 18, 21, 23]

_IG_PROFILE_RE = re.compile(
    r"^https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?$",
    re.IGNORECASE,
)


def normalize_profile_target(username_or_url: str) -> str | None:
    raw = (username_or_url or "").strip()
    if not raw:
        return None
    if raw.startswith("http"):
        if _IG_PROFILE_RE.match(raw.rstrip("/") + "/" if not raw.endswith("/") else raw):
            return raw.rstrip("/") + "/"
        return raw.rstrip("/") + "/"
    handle = raw.lstrip("@").strip()
    if not handle or "/" in handle:
        return None
    return f"https://www.instagram.com/{handle}/"


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if ts > 1_000_000_000_000:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _parse_timestamp(int(text))
    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _timestamp_from_row(row: dict[str, Any]) -> datetime | None:
    for key in (
        "publishedAt",
        "published_at",
        "timestamp",
        "takenAt",
        "taken_at",
        "createdAt",
        "created_at",
        "date",
    ):
        dt = _parse_timestamp(row.get(key))
        if dt:
            return dt
    return None


def normalize_apify_post(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    if row.get("accessStatus") not in (None, "success"):
        return None

    post_url = row.get("postUrl") or row.get("url") or row.get("inputUrl")
    shortcode = row.get("shortCode") or row.get("shortcode") or shortcode_from_post_url(str(post_url or ""))
    published = _timestamp_from_row(row)
    if not published:
        return None

    likes = row.get("likesCount")
    if likes is None:
        likes = row.get("likeCount") or row.get("likes")
    comments = row.get("commentsCount")
    if comments is None:
        comments = row.get("commentCount") or row.get("comments")
    views = row.get("videoViewCount") or row.get("viewCount") or row.get("views")

    engagement = None
    if isinstance(likes, (int, float)) and isinstance(views, (int, float)) and views > 0:
        engagement = round((float(likes) + float(comments or 0)) / float(views) * 100, 2)
    elif isinstance(likes, (int, float)) and isinstance(comments, (int, float)):
        engagement = float(likes) + float(comments)

    weekday = published.weekday()  # Mon=0
    return {
        "shortcode": str(shortcode) if shortcode else None,
        "post_url": str(post_url).rstrip("/") + "/" if post_url else None,
        "type": row.get("type"),
        "caption": str(row.get("caption") or "")[:280],
        "published_at": published.isoformat().replace("+00:00", "Z"),
        "published_date": published.strftime("%Y-%m-%d"),
        "weekday": weekday,
        "weekday_label": _WEEKDAY_LABELS[weekday],
        "hour_utc": published.hour,
        "minute_utc": published.minute,
        "likes_count": int(likes) if isinstance(likes, (int, float)) else None,
        "comments_count": int(comments) if isinstance(comments, (int, float)) else None,
        "views_count": int(views) if isinstance(views, (int, float)) else None,
        "engagement_score": engagement,
        "owner_username": row.get("ownerUsername") or row.get("username"),
    }


def compute_timeline_analytics(posts: list[dict[str, Any]]) -> dict[str, Any]:
    if not posts:
        return {
            "posts_count": 0,
            "date_span_days": 0,
            "posts_per_day": 0.0,
            "posts_per_week": 0.0,
            "by_week": [],
            "day_counts": [{"day": i, "label": label, "count": 0} for i, label in enumerate(_WEEKDAY_LABELS)],
            "most_popular": None,
            "calendar_days": [],
        }

    timestamps = [_parse_timestamp(p.get("published_at")) for p in posts]
    timestamps = [t for t in timestamps if t]
    span_days = max(1, (max(timestamps) - min(timestamps)).days + 1) if len(timestamps) > 1 else 1
    count = len(posts)
    posts_per_day = round(count / span_days, 2)
    posts_per_week = round(count / max(span_days / 7.0, 1.0), 2)

    day_counts = {i: 0 for i in range(7)}
    hour_by_day: dict[tuple[int, int], int] = {}
    calendar_map: dict[str, int] = {}

    by_week: list[dict[str, Any]] = []
    for post in posts:
        weekday = int(post.get("weekday", 0))
        hour = int(post.get("hour_utc", 0))
        day_counts[weekday] = day_counts.get(weekday, 0) + 1
        hour_by_day[(weekday, hour)] = hour_by_day.get((weekday, hour), 0) + 1
        date_key = post.get("published_date")
        if date_key:
            calendar_map[str(date_key)] = calendar_map.get(str(date_key), 0) + 1
        by_week.append(
            {
                "weekday": weekday,
                "weekday_label": post.get("weekday_label") or _WEEKDAY_LABELS[weekday],
                "hour_utc": hour,
                "shortcode": post.get("shortcode"),
                "post_url": post.get("post_url"),
                "published_at": post.get("published_at"),
                "engagement_score": post.get("engagement_score"),
                "likes_count": post.get("likes_count"),
            }
        )

    best_day = max(range(7), key=lambda d: day_counts.get(d, 0))
    best_hour = 0
    if day_counts.get(best_day, 0) > 0:
        best_hour = max(
            range(24),
            key=lambda h: hour_by_day.get((best_day, h), 0),
        )

    most_popular = {
        "weekday": best_day,
        "weekday_label": _WEEKDAY_LABELS[best_day],
        "hour_utc": best_hour,
        "label": f"{_WEEKDAY_LABELS[best_day]} | {best_hour:02d}:00",
    }

    calendar_days = [
        {"date": date, "count": calendar_map[date]}
        for date in sorted(calendar_map.keys())
    ]

    return {
        "posts_count": count,
        "date_span_days": span_days,
        "posts_per_day": posts_per_day,
        "posts_per_week": posts_per_week,
        "by_week": by_week,
        "day_counts": [
            {"day": i, "label": _WEEKDAY_LABELS[i], "count": day_counts.get(i, 0)}
            for i in range(7)
        ],
        "most_popular": most_popular,
        "calendar_days": calendar_days,
        "hour_ticks": _HOUR_TICKS,
        "weekday_order_sun_first": _WEEKDAY_LABELS_SUN_FIRST,
    }


async def fetch_instagram_timeline(
    username_or_url: str,
    *,
    results_limit: int = DEFAULT_RESULTS_LIMIT,
    skip_pinned: bool = False,
    data_detail_level: str = "basicData",
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    if not apify_configured():
        return {
            "success": False,
            "error": "APIFY_API_TOKEN is not configured. Add it to .env and restart the backend.",
            "posts": [],
            "analytics": compute_timeline_analytics([]),
        }

    target = normalize_profile_target(username_or_url)
    if not target:
        return {
            "success": False,
            "error": "Invalid Instagram username or profile URL.",
            "posts": [],
            "analytics": compute_timeline_analytics([]),
        }

    limit = max(1, min(int(results_limit or DEFAULT_RESULTS_LIMIT), MAX_RESULTS_LIMIT))
    payload: dict[str, Any] = {
        "username": [target],
        "resultsLimit": limit,
        "skipPinnedPosts": bool(skip_pinned),
        "dataDetailLevel": data_detail_level or "basicData",
    }
    params = {"token": os.getenv("APIFY_API_TOKEN", "").strip(), "timeout": max(60, min(int(timeout_sec), 300))}

    try:
        async with httpx.AsyncClient(timeout=float(params["timeout"]) + 20.0) as client:
            resp = await client.post(APIFY_SYNC_URL, params=params, json=payload)
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": f"Apify timeline request timed out after {params['timeout']}s.",
            "posts": [],
            "analytics": compute_timeline_analytics([]),
        }
    except httpx.HTTPError as exc:
        logger.warning("Apify timeline HTTP error: %s", exc)
        return {
            "success": False,
            "error": f"Apify request failed: {exc}",
            "posts": [],
            "analytics": compute_timeline_analytics([]),
        }

    if resp.status_code >= 400:
        detail = resp.text[:400] if resp.text else resp.reason_phrase
        return {
            "success": False,
            "error": f"Apify error ({resp.status_code}): {detail}",
            "posts": [],
            "analytics": compute_timeline_analytics([]),
        }

    try:
        items = resp.json()
    except ValueError:
        return {
            "success": False,
            "error": "Apify returned invalid JSON.",
            "posts": [],
            "analytics": compute_timeline_analytics([]),
        }

    if not isinstance(items, list):
        return {
            "success": False,
            "error": "Unexpected Apify response shape.",
            "posts": [],
            "analytics": compute_timeline_analytics([]),
        }

    posts: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("recordType") in ("RUN_META", "SUMMARY") or item.get("type") == "meta":
            continue
        normalized = normalize_apify_post(item)
        if normalized:
            posts.append(normalized)

    posts.sort(key=lambda p: p.get("published_at") or "", reverse=True)
    analytics = compute_timeline_analytics(posts)

    profile_username = None
    if posts:
        profile_username = posts[0].get("owner_username")
    if not profile_username:
        match = _IG_PROFILE_RE.match(target)
        profile_username = match.group(1) if match else username_or_url.lstrip("@")

    return {
        "success": True,
        "profile_username": profile_username,
        "target_url": target,
        "results_limit": limit,
        "posts": posts,
        "analytics": analytics,
    }
