"""Fetch Instagram post/reel comments via Apify instagram-comment-scraper."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

APIFY_ACTOR = "apify~instagram-comment-scraper"
APIFY_SYNC_URL = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
DEFAULT_RESULTS_LIMIT = 15
DEFAULT_TIMEOUT_SEC = 120
DEFAULT_BATCH_TIMEOUT_SEC = 180
MAX_BATCH_POSTS = 10
DEFAULT_TOP_COMMENTERS = 10

_IG_POST_RE = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[A-Za-z0-9_-]+/?",
    re.IGNORECASE,
)
_IG_SHORTCODE_RE = re.compile(
    r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


def apify_configured() -> bool:
    return bool(os.getenv("APIFY_API_TOKEN", "").strip())


def shortcode_from_post_url(url: str | None) -> str | None:
    if not url:
        return None
    match = _IG_SHORTCODE_RE.search(url)
    return match.group(1) if match else None


def normalize_instagram_post_urls(urls: list[str], *, max_posts: int = MAX_BATCH_POSTS) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        normalized = normalize_instagram_post_url(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
        if len(out) >= max_posts:
            break
    return out


def normalize_instagram_post_url(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    if not raw.startswith("http"):
        raw = f"https://{raw.lstrip('/')}"
    if not _IG_POST_RE.match(raw):
        return None
    return raw.rstrip("/") + "/"


def _username_from_row(row: dict[str, Any]) -> str | None:
    owner = row.get("owner")
    if isinstance(owner, dict):
        u = owner.get("username")
        if u:
            return str(u).strip() or None
    for key in ("ownerUsername", "username"):
        val = row.get(key)
        if val:
            return str(val).strip() or None
    return None


def _profile_url_from_row(row: dict[str, Any], username: str | None) -> str | None:
    for key in ("ownerProfileUrl", "profileUrl"):
        val = row.get(key)
        if val and str(val).startswith("http"):
            return str(val)
    if username:
        return f"https://www.instagram.com/{username}/"
    return None


def normalize_apify_comment(row: dict[str, Any]) -> dict[str, Any]:
    username = _username_from_row(row)
    replies_raw = row.get("replies") or []
    replies: list[dict[str, Any]] = []
    if isinstance(replies_raw, list):
        for item in replies_raw:
            if isinstance(item, dict):
                replies.append(normalize_apify_comment(item))

    likes = row.get("likesCount")
    if likes is None:
        likes = row.get("commentLikeCount")

    post_url = row.get("postUrl")
    return {
        "id": row.get("id"),
        "username": username,
        "text": str(row.get("text") or "").strip(),
        "like_count": likes,
        "timestamp": row.get("timestamp"),
        "profile_url": _profile_url_from_row(row, username),
        "comment_url": row.get("commentUrl"),
        "post_url": str(post_url).rstrip("/") + "/" if post_url else None,
        "replies_count": row.get("repliesCount") if row.get("repliesCount") is not None else len(replies),
        "replies": replies,
    }


def normalize_apify_comments(items: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = normalize_apify_comment(item)
        if normalized.get("text") or normalized.get("username"):
            out.append(normalized)
    return out


def _profile_pic_from_row(row: dict[str, Any]) -> str | None:
    owner = row.get("owner")
    if isinstance(owner, dict):
        for key in ("profile_pic_url", "profilePicUrl"):
            val = owner.get(key)
            if val and str(val).startswith("http"):
                return str(val)
    for key in ("ownerProfilePicUrl", "profilePicUrl"):
        val = row.get(key)
        if val and str(val).startswith("http"):
            return str(val)
    return None


def _is_verified_from_row(row: dict[str, Any]) -> bool:
    owner = row.get("owner")
    if isinstance(owner, dict) and owner.get("is_verified") is True:
        return True
    return row.get("isVerified") is True


def _post_type_from_url(url: str | None) -> str | None:
    if not url:
        return None
    low = url.lower()
    if "/reel/" in low:
        return "reel"
    if "/tv/" in low:
        return "tv"
    if "/p/" in low:
        return "post"
    return None


def _extract_post_meta(row: dict[str, Any]) -> dict[str, Any]:
    post_url = row.get("postUrl")
    normalized = str(post_url).rstrip("/") + "/" if post_url else None
    shortcode = row.get("postShortcode") or shortcode_from_post_url(normalized)
    total_on_post = row.get("postCommentCount")
    return {
        "post_url": normalized,
        "shortcode": str(shortcode) if shortcode else None,
        "post_owner_username": row.get("postOwnerUsername"),
        "total_comments_on_post": int(total_on_post) if total_on_post is not None else None,
        "post_type": _post_type_from_url(normalized),
    }


def aggregate_post_statistics(items: list[Any]) -> list[dict[str, Any]]:
    posts: dict[str, dict[str, Any]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        meta = _extract_post_meta(item)
        post_url = meta.get("post_url")
        if not post_url:
            continue

        bucket = posts.setdefault(
            post_url,
            {
                "post_url": post_url,
                "shortcode": meta.get("shortcode"),
                "post_type": meta.get("post_type"),
                "post_owner_username": meta.get("post_owner_username"),
                "total_comments_on_post": meta.get("total_comments_on_post"),
                "comments_scraped": 0,
                "replies_scraped": 0,
                "unique_commenters": set(),
            },
        )
        if meta.get("shortcode") and not bucket.get("shortcode"):
            bucket["shortcode"] = meta["shortcode"]
        if meta.get("post_owner_username") and not bucket.get("post_owner_username"):
            bucket["post_owner_username"] = meta["post_owner_username"]
        if meta.get("total_comments_on_post") is not None:
            bucket["total_comments_on_post"] = meta["total_comments_on_post"]

        bucket["comments_scraped"] += 1
        username = _username_from_row(item)
        if username:
            bucket["unique_commenters"].add(username.lower())

        for reply in item.get("replies") or []:
            if isinstance(reply, dict):
                bucket["replies_scraped"] += 1
                reply_user = _username_from_row(reply)
                if reply_user:
                    bucket["unique_commenters"].add(reply_user.lower())

    out: list[dict[str, Any]] = []
    for row in posts.values():
        out.append(
            {
                "post_url": row["post_url"],
                "shortcode": row.get("shortcode"),
                "post_type": row.get("post_type"),
                "post_owner_username": row.get("post_owner_username"),
                "total_comments_on_post": row.get("total_comments_on_post"),
                "comments_scraped": row["comments_scraped"],
                "replies_scraped": row["replies_scraped"],
                "unique_commenters": len(row["unique_commenters"]),
            }
        )
    return sorted(out, key=lambda p: (p.get("shortcode") or p["post_url"]))


def _ingest_comment_row(
    row: dict[str, Any],
    post_url: str | None,
    users: dict[str, dict[str, Any]],
    *,
    exclude_username: str | None,
    is_reply: bool = False,
) -> int:
    username = _username_from_row(row)
    text = str(row.get("text") or "").strip()
    if not username or (not text and not row.get("commentUrl")):
        return 0
    if exclude_username and username.lower() == exclude_username.lower():
        return 0

    likes = row.get("likesCount")
    if likes is None:
        likes = row.get("commentLikeCount")

    entry = users.setdefault(
        username.lower(),
        {
            "username": username,
            "comment_count": 0,
            "top_level_count": 0,
            "reply_count": 0,
            "total_likes": 0,
            "posts": set(),
            "profile_url": _profile_url_from_row(row, username),
            "profile_pic_url": _profile_pic_from_row(row),
            "is_verified": _is_verified_from_row(row),
            "by_post": {},
        },
    )
    if not entry.get("profile_url"):
        entry["profile_url"] = _profile_url_from_row(row, username)
    pic = _profile_pic_from_row(row)
    if pic and not entry.get("profile_pic_url"):
        entry["profile_pic_url"] = pic
    if _is_verified_from_row(row):
        entry["is_verified"] = True

    resolved_post = post_url or row.get("postUrl")
    if resolved_post:
        resolved_post = str(resolved_post).rstrip("/") + "/"
        meta = _extract_post_meta({**row, "postUrl": resolved_post})
        entry["posts"].add(resolved_post)
        bucket = entry["by_post"].setdefault(
            resolved_post,
            {
                "post_url": resolved_post,
                "shortcode": meta.get("shortcode") or shortcode_from_post_url(resolved_post),
                "post_type": meta.get("post_type"),
                "post_owner_username": meta.get("post_owner_username"),
                "total_comments_on_post": meta.get("total_comments_on_post"),
                "comment_count": 0,
                "comments": [],
            },
        )
        bucket["comments"].append(
            {
                "text": text,
                "timestamp": row.get("timestamp"),
                "like_count": likes,
                "comment_url": row.get("commentUrl"),
                "is_reply": is_reply,
            }
        )
        bucket["comment_count"] = len(bucket["comments"])

    entry["comment_count"] += 1
    if is_reply:
        entry["reply_count"] += 1
    else:
        entry["top_level_count"] += 1
    if isinstance(likes, (int, float)):
        entry["total_likes"] += int(likes)
    return 1


def aggregate_top_commenters(
    items: list[Any],
    *,
    exclude_username: str | None = None,
    top_n: int = DEFAULT_TOP_COMMENTERS,
) -> dict[str, Any]:
    users: dict[str, dict[str, Any]] = {}
    total_comments = 0
    posts_seen: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        post_url = item.get("postUrl")
        if post_url:
            posts_seen.add(str(post_url).rstrip("/") + "/")
        total_comments += _ingest_comment_row(item, post_url, users, exclude_username=exclude_username, is_reply=False)
        for reply in item.get("replies") or []:
            if isinstance(reply, dict):
                total_comments += _ingest_comment_row(
                    reply, post_url, users, exclude_username=exclude_username, is_reply=True,
                )

    ranked = sorted(
        users.values(),
        key=lambda u: (-u["comment_count"], -len(u["posts"]), u["username"].lower()),
    )
    top = ranked[: max(1, min(int(top_n or DEFAULT_TOP_COMMENTERS), 50))]

    top_commenters: list[dict[str, Any]] = []
    for row in top:
        by_post = sorted(
            row["by_post"].values(),
            key=lambda p: p.get("comment_count", len(p["comments"])),
            reverse=True,
        )
        top_commenters.append(
            {
                "username": row["username"],
                "comment_count": row["comment_count"],
                "top_level_count": row["top_level_count"],
                "reply_count": row["reply_count"],
                "posts_count": len(row["posts"]),
                "total_likes": row["total_likes"],
                "profile_url": row.get("profile_url"),
                "profile_pic_url": row.get("profile_pic_url"),
                "is_verified": row.get("is_verified") is True,
                "by_post": by_post,
            }
        )

    return {
        "posts_analyzed": len(posts_seen),
        "total_comments": total_comments,
        "unique_commenters": len(users),
        "top_commenters": top_commenters,
    }


def aggregate_comment_statistics(
    items: list[Any],
    *,
    exclude_username: str | None = None,
    top_n: int = DEFAULT_TOP_COMMENTERS,
) -> dict[str, Any]:
    user_stats = aggregate_top_commenters(items, exclude_username=exclude_username, top_n=top_n)
    user_stats["post_stats"] = aggregate_post_statistics(items)
    return user_stats


async def _fetch_apify_comment_items(
    post_urls: list[str],
    *,
    results_limit: int = DEFAULT_RESULTS_LIMIT,
    include_replies: bool = True,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not token:
        return {
            "success": False,
            "error": "APIFY_API_TOKEN is not configured. Add it to .env and restart the backend.",
            "items": [],
            "post_urls": [],
        }

    normalized_urls = normalize_instagram_post_urls(post_urls)
    if not normalized_urls:
        return {
            "success": False,
            "error": "No valid Instagram post or reel URLs.",
            "items": [],
            "post_urls": [],
        }

    limit = max(1, min(int(results_limit or DEFAULT_RESULTS_LIMIT), 100))
    payload: dict[str, Any] = {
        "directUrls": normalized_urls,
        "resultsLimit": limit,
    }
    if include_replies:
        payload["includeNestedComments"] = True

    params = {"token": token, "timeout": max(30, min(int(timeout_sec), 300))}

    try:
        async with httpx.AsyncClient(timeout=float(params["timeout"]) + 15.0) as client:
            resp = await client.post(APIFY_SYNC_URL, params=params, json=payload)
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": f"Apify request timed out after {params['timeout']}s.",
            "post_urls": normalized_urls,
            "items": [],
        }
    except httpx.HTTPError as exc:
        logger.warning("Apify HTTP error: %s", exc)
        return {
            "success": False,
            "error": f"Apify request failed: {exc}",
            "post_urls": normalized_urls,
            "items": [],
        }

    if resp.status_code >= 400:
        detail = resp.text[:400] if resp.text else resp.reason_phrase
        return {
            "success": False,
            "error": f"Apify error ({resp.status_code}): {detail}",
            "post_urls": normalized_urls,
            "items": [],
        }

    try:
        items = resp.json()
    except ValueError:
        return {
            "success": False,
            "error": "Apify returned invalid JSON.",
            "post_urls": normalized_urls,
            "items": [],
        }

    if not isinstance(items, list):
        return {
            "success": False,
            "error": "Unexpected Apify response shape.",
            "post_urls": normalized_urls,
            "items": [],
        }

    return {
        "success": True,
        "post_urls": normalized_urls,
        "results_limit": limit,
        "items": items,
    }


async def fetch_instagram_comments(
    post_url: str,
    *,
    results_limit: int = DEFAULT_RESULTS_LIMIT,
    include_replies: bool = True,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    batch = await _fetch_apify_comment_items(
        [post_url],
        results_limit=results_limit,
        include_replies=include_replies,
        timeout_sec=timeout_sec,
    )
    if not batch.get("success"):
        return {**batch, "comments": []}

    normalized_url = batch["post_urls"][0] if batch.get("post_urls") else None
    comments = normalize_apify_comments(batch["items"])
    return {
        "success": True,
        "post_url": normalized_url,
        "results_limit": batch.get("results_limit"),
        "count": len(comments),
        "comments": comments,
    }


async def fetch_profile_comment_statistics(
    post_urls: list[str],
    *,
    profile_username: str | None = None,
    results_limit: int = DEFAULT_RESULTS_LIMIT,
    include_replies: bool = True,
    top_n: int = DEFAULT_TOP_COMMENTERS,
    timeout_sec: int = DEFAULT_BATCH_TIMEOUT_SEC,
) -> dict[str, Any]:
    batch = await _fetch_apify_comment_items(
        post_urls,
        results_limit=results_limit,
        include_replies=include_replies,
        timeout_sec=timeout_sec,
    )
    if not batch.get("success"):
        return {**batch, "top_commenters": []}

    stats = aggregate_comment_statistics(
        batch["items"],
        exclude_username=profile_username,
        top_n=top_n,
    )
    return {
        "success": True,
        "post_urls": batch.get("post_urls") or [],
        "results_limit": batch.get("results_limit"),
        "posts_analyzed": len(batch.get("post_urls") or []),
        "total_comments": stats["total_comments"],
        "unique_commenters": stats["unique_commenters"],
        "post_stats": stats.get("post_stats") or [],
        "top_commenters": stats["top_commenters"],
    }
