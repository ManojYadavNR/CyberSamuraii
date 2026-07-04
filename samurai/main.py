import argparse
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

console = Console()

SIMPLE_UA = "Mozilla/5.0"
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
IG_APP_ID = "936619743392459"

# How many of the most recent video posts to enrich with full reel metadata.
MAX_REEL_DETAIL_FETCHES = 6
# Small pause between detail requests to reduce the chance of rate limiting.
DETAIL_FETCH_DELAY = 0.6

# Comment fetching (requires a logged-in session via IG_SESSIONID).
MAX_COMMENT_POSTS = 6
COMMENTS_PER_POST = 15

# Safe concurrency — enough for speed, low enough to avoid OOM / process kills.
# Nested pools must stay small; total active Samurai threads should stay under ~10.
SAMURAI_SAFE_WORKERS = max(2, min(4, int(os.getenv("SAMURAI_SAFE_WORKERS", "3"))))

# Investigation fast path — fewer HTTP round-trips, parallel probes, skip deep enrichment.
FAST_HTTP_TIMEOUT = 10
FAST_FB_PROBE_LIMIT = 5
FAST_SIMILAR_PROFILE_LIMIT = 6
FAST_CONFIDENT_MATCH_SCORE = 3

BROWSER_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": DESKTOP_UA,
}

# Instagram's desktop HTML shell often omits og: tags; the lightweight UA still
# receives the classic public profile page with follower counts in meta tags.
PROFILE_PAGE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": SIMPLE_UA,
}
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
MOBILE_PROFILE_HEADERS = {**PROFILE_PAGE_HEADERS, "user-agent": MOBILE_UA}

FB_CRAWLER_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
FB_HEADERS = {
    "user-agent": FB_CRAWLER_UA,
    "accept-language": "en-US,en;q=0.9",
    "accept": "text/html,application/xhtml+xml",
}

MAX_FB_FRIENDS = 100
MAX_FB_PHOTOS = 50
MAX_FB_VIDEOS = 30
MAX_FB_POSTS = 25
FB_FETCH_DELAY = 0.5
MBASIC_UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)
MBASIC_HEADERS = {
    "user-agent": MBASIC_UA,
    "accept-language": "en-US,en;q=0.9",
    "accept": "text/html,application/xhtml+xml",
}

MOBILE_FB_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "accept-language": "en-US,en;q=0.9",
    "accept": "text/html,application/xhtml+xml",
}

GOOGLEBOT_HEADERS = {
    "user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "accept-language": "en-US,en;q=0.9",
    "accept": "text/html,application/xhtml+xml",
}


def show_banner():
    console.print(
        Panel.fit(
            "[bold blue]Social Media Public Profile Scraper[/bold blue]\n"
            "[green]Instagram & Facebook — Public Profile Data[/green]\n"
            "Created by Walid Elfeky",
            border_style="bright_blue",
        )
    )


def parse_platform(value: str) -> str | None:
    value = value.strip().lower()
    if value in ("instagram", "ig", "insta", "1"):
        return "instagram"
    if value in ("facebook", "fb", "face", "2"):
        return "facebook"
    return None


def parse_username(value: str) -> str:
    value = value.strip().strip("/")
    match = re.search(r"instagram\.com/([A-Za-z0-9._]+)", value)
    if match:
        return match.group(1)
    return value.lstrip("@")


def parse_facebook_slug(value: str) -> str:
    value = value.strip().strip("/")
    profile_id = re.search(r"facebook\.com/profile\.php\?id=(\d+)", value, re.I)
    if profile_id:
        return f"profile.php?id={profile_id.group(1)}"
    match = re.search(r"facebook\.com/(?:pages/[^/]+/)?([A-Za-z0-9.\-_]+)", value, re.I)
    if match:
        return match.group(1)
    match = re.search(r"fb\.com/([A-Za-z0-9.\-_]+)", value, re.I)
    if match:
        return match.group(1)
    slug = value.lstrip("@")
    if " " in slug:
        return slug.lower().replace(" ", ".")
    return slug


def slug_to_filename(slug: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", slug).strip("_") or "profile"


# ---------------------------------------------------------------------------
# Low-level extraction helpers (work on the escaped JSON embedded in HTML)
# ---------------------------------------------------------------------------

def extract_json_string(text: str, key: str) -> str | None:
    """Return the raw (still backslash-escaped) value of a JSON string key.

    Instagram embeds a JSON document inside a JS string, so values contain
    sequences like ``\\"`` that a naive regex would terminate on. This scans
    character by character, honoring escapes, to capture the full value.
    """
    marker = f'"{key}":"'
    start = text.find(marker)
    if start < 0:
        return None
    i = start + len(marker)
    out = []
    while i < len(text):
        char = text[i]
        if char == "\\":
            out.append(text[i : i + 2])
            i += 2
            continue
        if char == '"':
            break
        out.append(char)
        i += 1
    return "".join(out)


def load_context_json(page: str) -> dict | None:
    raw = extract_json_string(page, "contextJSON")
    if not raw:
        return None
    try:
        return json.loads(json.loads('"' + raw + '"'))
    except (json.JSONDecodeError, ValueError):
        return None


def find_key(obj, key):
    """Depth-first search for the first value stored under ``key``."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = find_key(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_key(value, key)
            if found is not None:
                return found
    return None


def extract_embed_value(page: str, field: str) -> str | None:
    patterns = [
        rf'\\"{field}\\":(true|false|\d+)',
        rf'\\"{field}\\":\\"([^\\"]*)\\"',
        rf'"{field}":(true|false|\d+)',
        rf'"{field}":"([^"]*)"',
        rf'{field}["\\]+:(true|false|\d+)',
        rf'{field}["\\]+:\\"([^\\"]*)\\"',
    ]
    for pattern in patterns:
        match = re.search(pattern, page)
        if not match:
            continue
        value = match.group(1)
        if value in ("true", "false") or value.isdigit():
            return value
        return html.unescape(value)
    return None


def extract_profile_pic_url(page: str) -> str | None:
    patterns = [
        r'profile_pic_url\\":\\"(https:[^\\]+)',
        r'"profile_pic_url":"(https:[^"]+)"',
        r'profile_pic_url["\\]+:\\"(https:[^\\]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, page)
        if match:
            return match.group(1).replace("\\/", "/").replace("\\\\/", "/")
    return None


def extract_graphql_count(page: str, edge: str) -> int | None:
    match = re.search(rf'\\"{edge}\\":\{{\\"count\\":(\d+)\}}', page)
    if match:
        return int(match.group(1))
    match = re.search(rf'"{edge}":\{{"count":(\d+)\}}', page)
    if match:
        return int(match.group(1))
    return None


def parse_meta_counts(description: str) -> dict:
    match = re.search(
        r"([\d,.]+[KMB]?)\s+Followers?,\s+([\d,.]+[KMB]?)\s+Following,\s+([\d,.]+[KMB]?)\s+Posts?",
        description,
        re.IGNORECASE,
    )
    if not match:
        return {}

    def to_int(value: str) -> int | None:
        value = value.replace(",", "").strip()
        if not value:
            return None
        multiplier = 1
        suffix = value[-1].upper()
        if suffix in "KMB":
            multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
            value = value[:-1]
        try:
            return int(float(value) * multiplier)
        except ValueError:
            return None

    return {
        "followers": to_int(match.group(1)),
        "following": to_int(match.group(2)),
        "posts": to_int(match.group(3)),
    }


def _bio_from_og_description(description: str) -> str:
    """Pull bio text from Instagram og:description when present (no login needed)."""
    if not description:
        return ""
    low = description.lower()
    if "see instagram photos" in low or "see instagram videos" in low:
        return ""
    if "share what you're into" in low:
        return ""
    if " - " in description:
        tail = description.split(" - ", 1)[1].strip()
        if tail and "see instagram" not in tail.lower():
            return tail
    return ""


def _is_instagram_branding_url(url: str | None) -> bool:
    if not url:
        return False
    low = url.lower()
    return (
        "rsrc.php" in low
        or "static.cdninstagram.com" in low
        or "/yr/r/" in low
        or (low.endswith(".webp") and "rsrc" in low)
    )


def _is_generic_instagram_bio(text: str | None) -> bool:
    if not text:
        return False
    low = text.strip().lower()
    return any(
        phrase in low
        for phrase in (
            "share what you're into",
            "see instagram photos",
            "see instagram videos",
            "create an account or log in",
        )
    )


def _sanitize_instagram_profile(profile: dict) -> dict:
    """Drop Instagram site branding mistaken for profile media/metadata."""
    cleaned = dict(profile)
    if _is_instagram_branding_url(cleaned.get("profile_pic_url")):
        cleaned["profile_pic_url"] = None
    if (cleaned.get("full_name") or "").strip().lower() in ("instagram", "log in to instagram"):
        cleaned["full_name"] = cleaned.get("username") or ""
    if _is_generic_instagram_bio(cleaned.get("biography")):
        cleaned["biography"] = ""
    has_posts = bool(cleaned.get("posts"))
    has_pic = bool(cleaned.get("profile_pic_url"))
    has_counts = cleaned.get("follower_count") is not None or cleaned.get("media_count") is not None
    if has_posts or has_pic or has_counts or cleaned.get("source") == "embed":
        cleaned.pop("scrape_limited", None)
    elif cleaned.get("source") == "profile_page" and not has_posts and not has_pic:
        cleaned["scrape_limited"] = True
    return cleaned


def _extract_embed_comments(node: dict, limit: int = COMMENTS_PER_POST) -> list[dict]:
    """Comment snippets occasionally present in public embed GraphQL."""
    edges = (node.get("edge_media_to_comment") or {}).get("edges") or []
    comments: list[dict] = []
    for edge in edges[:limit]:
        cnode = edge.get("node") or {}
        text = (cnode.get("text") or "").strip()
        if not text:
            continue
        owner = cnode.get("owner") or {}
        comments.append(
            {
                "username": owner.get("username"),
                "text": text,
                "like_count": (cnode.get("edge_liked_by") or {}).get("count"),
                "timestamp": timestamp_to_str(cnode.get("created_at")),
            }
        )
    return comments


def _parse_profile_meta(page: str, username: str) -> dict:
    """Extract public profile fields from og/meta tags on a profile HTML page."""
    meta: dict[str, str] = {}
    for key, pattern in {
        "description": r'property="og:description"[^>]+content="([^"]*)"',
        "title": r'property="og:title"[^>]+content="([^"]*)"',
        "image": r'property="og:image"[^>]+content="([^"]*)"',
    }.items():
        match = re.search(pattern, page)
        if match:
            meta[key] = html.unescape(match.group(1))

    if not meta.get("description"):
        alt = re.search(r'name="description"[^>]+content="([^"]*)"', page, re.I)
        if alt:
            meta["description"] = html.unescape(alt.group(1))

    description = meta.get("description") or ""
    title = meta.get("title") or ""
    private_hint = "account is private" in description.lower() or "account is private" in title.lower()
    if private_hint:
        return {
            "username": username,
            "full_name": "",
            "biography": "",
            "is_verified": False,
            "is_private": True,
            "profile_pic_url": meta.get("image"),
            "follower_count": None,
            "following_count": None,
            "media_count": None,
            "posts": [],
            "source": "profile_page",
        }

    counts = parse_meta_counts(description)
    if counts.get("followers") is None:
        for pattern in (
            r'"edge_followed_by":\{"count":(\d+)\}',
            r'"follower_count":(\d+)',
            r'"interaction_count":(\d+)',
        ):
            match = re.search(pattern, page)
            if match:
                counts["followers"] = int(match.group(1))
                break
    full_name = ""
    if title:
        name_match = re.match(r"^(.+?)\s+\(@", title)
        full_name = name_match.group(1).strip() if name_match else title

    user_id = None
    for pattern in (r'"user_id":"(\d+)"', r"profilePage_(\d+)"):
        match = re.search(pattern, page)
        if match:
            user_id = match.group(1)
            break

    return {
        "username": username,
        "full_name": full_name,
        "biography": _bio_from_og_description(description),
        "is_verified": False,
        "is_private": False,
        "profile_pic_url": meta.get("image"),
        "id": user_id,
        "follower_count": counts.get("followers"),
        "following_count": counts.get("following"),
        "media_count": counts.get("posts"),
        "posts": [],
        "source": "profile_page",
    }


def _merge_profile_fields(base: dict, overlay: dict) -> dict:
    """Fill missing scalar fields on ``base`` from ``overlay``."""
    for key in (
        "username",
        "full_name",
        "biography",
        "profile_pic_url",
        "id",
        "follower_count",
        "following_count",
        "media_count",
        "is_verified",
        "is_private",
    ):
        if base.get(key) in (None, "", False) and overlay.get(key) not in (None, ""):
            base[key] = overlay[key]
    if not base.get("posts") and overlay.get("posts"):
        base["posts"] = overlay["posts"]
    return base


def _has_usable_public_profile(profile: dict) -> bool:
    if profile.get("is_private"):
        return False
    if _is_instagram_branding_url(profile.get("profile_pic_url")) and not profile.get("posts"):
        if profile.get("follower_count") is None and profile.get("media_count") is None:
            return False
    if (profile.get("full_name") or "").strip().lower() == "instagram" and not profile.get("posts"):
        return False
    if _is_generic_instagram_bio(profile.get("biography")) and not profile.get("posts"):
        if profile.get("follower_count") is None:
            return False
    return any(
        profile.get(key) not in (None, "", False)
        for key in (
            "follower_count",
            "following_count",
            "media_count",
            "profile_pic_url",
            "full_name",
            "biography",
            "id",
            "posts",
        )
    )


def fetch_profile_from_public_page(username: str) -> dict:
    """Fallback when the embed endpoint returns empty contextJSON (common since 2025)."""
    last_error: Exception | None = None
    for headers in (PROFILE_PAGE_HEADERS, MOBILE_PROFILE_HEADERS):
        try:
            session = requests.Session()
            session.get("https://www.instagram.com/", headers=headers, timeout=30)
            response = session.get(
                f"https://www.instagram.com/{username}/",
                headers={**headers, "referer": "https://www.instagram.com/"},
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            last_error = exc
            continue

        page = response.text
        if response.status_code == 404 or "Sorry, this page isn't available." in page:
            raise ValueError(f"Profile '{username}' was not found.")

        profile = _parse_profile_meta(page, username)
        profile = _sanitize_instagram_profile(profile)
        if profile.get("is_private"):
            raise RuntimeError(f"Profile '{username}' is private.")
        if _has_usable_public_profile(profile):
            return profile
        if username.lower() in page.lower():
            profile["scrape_limited"] = True
            return profile
        last_error = RuntimeError("Could not parse public profile metadata from Instagram HTML.")

    if last_error:
        raise last_error
    raise RuntimeError(
        "Could not read profile data from Instagram. "
        "Instagram may be rate-limiting this server, or the account may be private or suspended."
    )


# ---------------------------------------------------------------------------
# Post / caption / hashtag / reel helpers
# ---------------------------------------------------------------------------

HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")
MENTION_RE = re.compile(r"@([A-Za-z0-9_.]+)")


def extract_hashtags(caption: str) -> list[str]:
    return HASHTAG_RE.findall(caption or "")


def extract_mentions(caption: str) -> list[str]:
    return MENTION_RE.findall(caption or "")


def caption_text(node: dict) -> str:
    edges = node.get("edge_media_to_caption", {}).get("edges", [])
    if edges:
        return edges[0].get("node", {}).get("text", "") or ""
    return node.get("accessibility_caption", "") or ""


def timestamp_to_str(ts) -> str | None:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, OSError, OverflowError):
        return None


def media_type(node: dict) -> str:
    typename = node.get("__typename", "")
    product = node.get("product_type")
    if product == "clips" or typename == "GraphReel":
        return "Reel"
    if node.get("is_video") or typename == "GraphVideo":
        return "Video"
    if typename == "GraphSidecar":
        return "Carousel"
    return "Image"


def media_item(node: dict) -> dict:
    """Return a single downloadable media entry for an image/video node."""
    if node.get("is_video") and node.get("video_url"):
        return {"kind": "video", "url": node.get("video_url"), "thumbnail": node.get("display_url")}
    return {"kind": "image", "url": node.get("display_url"), "thumbnail": node.get("display_url")}


def collect_media(node: dict) -> list[dict]:
    """Return every downloadable image/video in a post, including each child of
    a carousel/sidecar post."""
    children = node.get("edge_sidecar_to_children", {}).get("edges")
    if children:
        items = []
        for edge in children:
            child = edge.get("node", {})
            if child:
                items.append(media_item(child))
        if items:
            return items
    item = media_item(node)
    return [item] if item.get("url") else []


def normalize_feed_item(item: dict) -> dict:
    """Normalize an Instagram ``/api/v1/feed/user/`` media item into a post dict."""
    code = str(item.get("code") or "")
    media_type = item.get("media_type")
    product_type = str(item.get("product_type") or "")
    carousel = item.get("carousel_media") or []
    is_video = bool(item.get("is_video")) or media_type == 2 or product_type == "clips"

    caption_obj = item.get("caption")
    caption = ""
    if isinstance(caption_obj, dict):
        caption = caption_obj.get("text") or ""
    elif isinstance(caption_obj, str):
        caption = caption_obj

    display_url = None
    candidates = (item.get("image_versions2") or {}).get("candidates") or []
    if candidates and isinstance(candidates[0], dict):
        display_url = candidates[0].get("url")

    video_url = None
    if is_video:
        video_versions = item.get("video_versions") or []
        if video_versions and isinstance(video_versions[0], dict):
            video_url = video_versions[0].get("url")

    media: list[dict] = []
    if carousel:
        for child in carousel:
            if not isinstance(child, dict):
                continue
            child_candidates = (child.get("image_versions2") or {}).get("candidates") or []
            child_url = None
            if child_candidates and isinstance(child_candidates[0], dict):
                child_url = child_candidates[0].get("url")
            child_video = None
            if child.get("is_video") or child.get("media_type") == 2:
                vv = child.get("video_versions") or []
                if vv and isinstance(vv[0], dict):
                    child_video = vv[0].get("url")
            if child_video:
                media.append(
                    {
                        "kind": "video",
                        "url": child_video,
                        "thumbnail": child_url,
                        "display_url": child_url,
                    }
                )
            elif child_url:
                media.append(
                    {
                        "kind": "image",
                        "url": child_url,
                        "thumbnail": child_url,
                        "display_url": child_url,
                    }
                )
    elif video_url:
        media.append({"kind": "video", "url": video_url, "thumbnail": display_url})
    elif display_url:
        media.append({"kind": "image", "url": display_url, "thumbnail": display_url})

    if product_type == "clips":
        post_type = "Reel"
    elif is_video:
        post_type = "Video"
    elif media_type == 8 or carousel:
        post_type = "Carousel"
    else:
        post_type = "Image"

    return {
        "shortcode": code or None,
        "media_id": str(item.get("pk") or item.get("id") or ""),
        "url": f"https://www.instagram.com/p/{code}/" if code else None,
        "type": post_type,
        "is_video": is_video,
        "caption": caption,
        "hashtags": extract_hashtags(caption),
        "mentions": extract_mentions(caption),
        "like_count": item.get("like_count"),
        "comment_count": item.get("comment_count"),
        "timestamp": timestamp_to_str(item.get("taken_at")),
        "video_view_count": item.get("view_count") or item.get("play_count"),
        "video_duration": item.get("video_duration"),
        "video_url": video_url,
        "display_url": display_url,
        "media": media,
        "comments": [],
    }


def fetch_user_media_feed(session: requests.Session, user_id: str, username: str) -> list[dict]:
    """Public timeline feed — works without IG_SESSIONID when profile id is known."""
    if not user_id or not username:
        return []
    try:
        response = session.get(
            f"https://www.instagram.com/api/v1/feed/user/{user_id}/",
            headers=_api_headers(session, f"https://www.instagram.com/{username}/"),
            timeout=30,
        )
    except requests.RequestException:
        return []
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    posts: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = normalize_feed_item(item)
        if normalized.get("shortcode") or normalized.get("url"):
            posts.append(normalized)
    return posts


def enrich_posts_from_user_feed(profile: dict, session: requests.Session) -> None:
    """Backfill timeline posts when embed/profile-page scraping returns counts only."""
    user_id = profile.get("id")
    username = profile.get("username")
    if not user_id or not username:
        return
    existing = profile.get("posts") or []
    needs_feed = not existing
    if existing and not needs_feed:
        for post in existing[:8]:
            media = post.get("media") or []
            if post.get("type") == "Carousel" and len(media) < 2:
                needs_feed = True
                break
            if not post.get("display_url") and not media:
                needs_feed = True
                break
    if not needs_feed:
        return
    if profile.get("media_count") == 0 and not existing:
        return
    feed_posts = fetch_user_media_feed(session, str(user_id), str(username))
    if not feed_posts:
        return
    profile["posts"] = feed_posts
    if profile.get("source") in ("profile_page", "embed"):
        profile["source"] = "public_feed_api"


def normalize_post(node: dict) -> dict:
    caption = caption_text(node)
    return {
        "shortcode": node.get("shortcode"),
        "media_id": node.get("id"),
        "url": f"https://www.instagram.com/p/{node.get('shortcode')}/" if node.get("shortcode") else None,
        "type": media_type(node),
        "is_video": bool(node.get("is_video")),
        "caption": caption,
        "hashtags": extract_hashtags(caption),
        "mentions": extract_mentions(caption),
        "like_count": node.get("edge_liked_by", {}).get("count")
        or node.get("edge_media_preview_like", {}).get("count"),
        "comment_count": node.get("edge_media_to_comment", {}).get("count"),
        "timestamp": timestamp_to_str(node.get("taken_at_timestamp")),
        "video_view_count": node.get("video_view_count"),
        "video_duration": node.get("video_duration"),
        "video_url": node.get("video_url"),
        "display_url": node.get("display_url"),
        "media": collect_media(node),
        "comments": _extract_embed_comments(node),
    }


# ---------------------------------------------------------------------------
# Network calls
# ---------------------------------------------------------------------------

def make_session(sessionid: str | None = None) -> requests.Session:
    """Build a requests session, warmed up with cookies. When a ``sessionid``
    is supplied the session is authenticated, unlocking the bio and the
    comments API."""
    session = requests.Session()
    cookies = load_instagram_cookies() or {}
    if sessionid:
        cookies = {**cookies, "sessionid": sessionid}
    for name, value in cookies.items():
        if value:
            session.cookies.set(name, value, domain=".instagram.com")
    try:
        session.get("https://www.instagram.com/", headers={"user-agent": DESKTOP_UA}, timeout=30)
    except requests.RequestException:
        pass
    return session


def _api_headers(session: requests.Session, referer: str) -> dict:
    headers = {
        "user-agent": DESKTOP_UA,
        "accept": "*/*",
        "x-ig-app-id": IG_APP_ID,
        "x-requested-with": "XMLHttpRequest",
        "x-asbd-id": "129477",
        "referer": referer,
    }
    csrftoken = session.cookies.get("csrftoken")
    if csrftoken:
        headers["x-csrftoken"] = csrftoken
    return headers


def fetch_web_profile_info(session: requests.Session, username: str) -> tuple[dict | None, dict | None]:
    """Richest source (bio + posts + reel metadata) but requires a logged-in
    session for reliable access. Returns ``(user, full_payload)`` or ``(None, None)``."""
    try:
        response = session.get(
            f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
            headers=_api_headers(session, f"https://www.instagram.com/{username}/"),
            timeout=30,
        )
    except requests.RequestException:
        return None, None
    if response.status_code != 200:
        return None, None
    try:
        payload = response.json()
    except ValueError:
        return None, None
    user = payload.get("data", {}).get("user") if isinstance(payload.get("data"), dict) else None
    if not user:
        return None, None
    return user, payload


def fetch_comments(session: requests.Session, media_id: str, shortcode: str, limit: int) -> list[dict]:
    """Fetch real comment text for a post via the media comments API.

    This is the working alternative to scraping comment text from HTML, which
    Instagram no longer exposes anonymously. Requires an authenticated session.
    """
    if not media_id:
        return []
    url = (
        f"https://www.instagram.com/api/v1/media/{media_id}/comments/"
        "?can_support_threading=true&permalink_enabled=false"
    )
    try:
        response = session.get(
            url,
            headers=_api_headers(session, f"https://www.instagram.com/p/{shortcode}/"),
            timeout=30,
        )
    except requests.RequestException:
        return []
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or "application/json" not in content_type:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []

    raw_comments = payload.get("comments")
    if raw_comments is None:
        # Some responses nest the list under a preview key.
        raw_comments = payload.get("preview_comments") or []

    comments = []
    for raw in raw_comments[:limit]:
        user = raw.get("user", {}) or {}
        comments.append(
            {
                "username": user.get("username"),
                "text": raw.get("text", ""),
                "like_count": raw.get("comment_like_count"),
                "timestamp": timestamp_to_str(raw.get("created_at") or raw.get("created_at_utc")),
            }
        )
    return comments


def profile_from_web_api(user: dict, username: str) -> dict:
    posts = []
    for edge in user.get("edge_owner_to_timeline_media", {}).get("edges", []):
        posts.append(normalize_post(edge.get("node", {})))
    return {
        "username": user.get("username") or username,
        "full_name": user.get("full_name") or "",
        "biography": user.get("biography") or "",
        "external_url": user.get("external_url"),
        "category": user.get("category_name"),
        "is_verified": bool(user.get("is_verified")),
        "is_private": bool(user.get("is_private")),
        "is_business": bool(user.get("is_business_account")),
        "follower_count": user.get("edge_followed_by", {}).get("count"),
        "following_count": user.get("edge_follow", {}).get("count"),
        "media_count": user.get("edge_owner_to_timeline_media", {}).get("count"),
        "profile_pic_url": user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
        "id": user.get("id"),
        "posts": posts,
        "source": "web_profile_info",
    }


def fetch_profile_from_embed(username: str) -> dict:
    last_error: Exception | None = None
    for headers in (
        MOBILE_PROFILE_HEADERS,
        {"user-agent": DESKTOP_UA, "accept-language": "en-US,en;q=0.9"},
        BROWSER_HEADERS,
        {"user-agent": SIMPLE_UA, "accept-language": "en-US,en;q=0.9"},
    ):
        try:
            response = requests.get(
                f"https://www.instagram.com/{username}/embed/",
                headers=headers,
                timeout=30,
            )
        except requests.RequestException as exc:
            last_error = exc
            continue
        if response.status_code == 404:
            raise ValueError(f"Profile '{username}' was not found.")
        if response.status_code != 200:
            last_error = RuntimeError(f"Instagram embed HTTP {response.status_code}")
            continue

        page = response.text
        if "Sorry, this page isn't available." in page:
            raise ValueError(f"Profile '{username}' was not found.")

        profile = {
            "username": extract_embed_value(page, "username") or username,
            "full_name": extract_embed_value(page, "full_name") or "",
            "biography": extract_embed_value(page, "biography") or "",
            "is_verified": extract_embed_value(page, "is_verified") == "true",
            "is_private": extract_embed_value(page, "is_private") == "true",
            "profile_pic_url": extract_profile_pic_url(page),
            "id": extract_embed_value(page, "id"),
            "source": "embed",
        }

        followers = extract_embed_value(page, "followers_count")
        posts_count = extract_embed_value(page, "posts_count")
        profile["follower_count"] = (
            int(followers) if followers and followers.isdigit() else extract_graphql_count(page, "edge_followed_by")
        )
        profile["media_count"] = (
            int(posts_count)
            if posts_count and posts_count.isdigit()
            else extract_graphql_count(page, "edge_owner_to_timeline_media")
        )
        profile["following_count"] = extract_graphql_count(page, "edge_follow")

        posts = []
        owner_id = None
        context = load_context_json(page)
        if context:
            media = find_key(context, "graphql_media") or []
            for item in media:
                node = item.get("shortcode_media", item) if isinstance(item, dict) else {}
                if node:
                    posts.append(normalize_post(node))
                    owner = node.get("owner") or {}
                    if not owner_id and owner.get("id"):
                        owner_id = owner["id"]
        if owner_id:
            profile["id"] = owner_id
        profile["posts"] = posts

        if profile["follower_count"] is None and not posts and not profile.get("profile_pic_url"):
            last_error = RuntimeError(
                "Could not read profile data from Instagram embed. "
                "The embed endpoint may be empty; a profile-page fallback will be attempted."
            )
            continue

        return _sanitize_instagram_profile(profile)

    if last_error:
        raise last_error
    raise RuntimeError(
        "Could not read profile data from Instagram embed. "
        "The embed endpoint may be empty; a profile-page fallback will be attempted."
    )


def fetch_post_details(shortcode: str) -> dict | None:
    """Fetch a single post's embed to obtain reel/video metadata that the
    profile-level embed omits (video URL, view count, duration)."""
    try:
        response = requests.get(
            f"https://www.instagram.com/p/{shortcode}/embed/captioned/",
            headers={"user-agent": SIMPLE_UA, "accept-language": "en-US,en;q=0.9"},
            timeout=30,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    context = load_context_json(response.text)
    if not context:
        return None
    node = find_key(context, "shortcode_media")
    return normalize_post(node) if node else None


def enrich_from_profile_page(profile: dict, username: str) -> dict:
    try:
        session = requests.Session()
        session.get("https://www.instagram.com/", headers=BROWSER_HEADERS, timeout=30)
        response = session.get(
            f"https://www.instagram.com/{username}/",
            headers={**BROWSER_HEADERS, "referer": "https://www.instagram.com/", "sec-fetch-site": "same-origin"},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException:
        return profile

    page = response.text
    meta = {}
    for key, pattern in {
        "description": r'property="og:description"[^>]+content="([^"]*)"',
        "title": r'property="og:title"[^>]+content="([^"]*)"',
        "image": r'property="og:image"[^>]+content="([^"]*)"',
    }.items():
        match = re.search(pattern, page)
        if match:
            meta[key] = html.unescape(match.group(1))
    if "description" in meta:
        meta.update(parse_meta_counts(meta["description"]))

    if not profile.get("full_name") and meta.get("title"):
        name_match = re.match(r"^(.+?)\s+\(@", meta["title"])
        profile["full_name"] = name_match.group(1).strip() if name_match else meta["title"]
    if profile.get("following_count") is None and meta.get("following") is not None:
        profile["following_count"] = meta["following"]
    if profile.get("media_count") is None and meta.get("posts") is not None:
        profile["media_count"] = meta["posts"]
    if not profile.get("profile_pic_url") and meta.get("image"):
        profile["profile_pic_url"] = meta["image"]
    if not profile.get("biography") and meta.get("description"):
        bio = _bio_from_og_description(meta["description"])
        if bio:
            profile["biography"] = bio
    return profile


def _apply_reel_details(post: dict, details: dict | None) -> None:
    if not details:
        return
    for field in ("video_url", "video_view_count", "video_duration"):
        if details.get(field) is not None:
            post[field] = details[field]
    if details.get("media"):
        post["media"] = details["media"]
    if details.get("type") in ("Video", "Reel"):
        post["type"] = details["type"]
    if not post.get("caption") and details.get("caption"):
        post["caption"] = details["caption"]
        post["hashtags"] = extract_hashtags(details["caption"])
        post["mentions"] = extract_mentions(details["caption"])


def enrich_reels(profile: dict) -> None:
    """Fill in video metadata for recent video posts (parallel HTTP, same fields)."""
    targets: list[dict] = []
    for post in profile.get("posts", []):
        if len(targets) >= MAX_REEL_DETAIL_FETCHES:
            break
        needs_detail = post.get("is_video") or post.get("type") in ("Video", "Reel")
        if not needs_detail or post.get("video_url"):
            continue
        if not post.get("shortcode"):
            continue
        targets.append(post)

    if not targets:
        return

    def _fetch(post: dict) -> tuple[dict, dict | None]:
        return post, fetch_post_details(post["shortcode"])

    workers = min(SAMURAI_SAFE_WORKERS, len(targets))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for post, details in pool.map(_fetch, targets):
            _apply_reel_details(post, details)


def enrich_comments(session: requests.Session, profile: dict) -> None:
    """Attach real comment text to recent posts (parallel HTTP, same fields)."""
    targets: list[dict] = []
    for post in profile.get("posts", []):
        if len(targets) >= MAX_COMMENT_POSTS:
            break
        if not post.get("comment_count"):
            post["comments"] = []
            continue
        if not post.get("shortcode"):
            post["comments"] = []
            continue
        targets.append(post)

    if not targets:
        return

    # requests.Session is not thread-safe — clone cookies per worker.
    cookie_jar = {c.name: c.value for c in session.cookies}

    def _fetch(post: dict) -> tuple[dict, list]:
        worker = requests.Session()
        for name, value in cookie_jar.items():
            worker.cookies.set(name, value, domain=".instagram.com")
        comments = fetch_comments(
            worker,
            post.get("media_id") or post.get("id"),
            post.get("shortcode"),
            COMMENTS_PER_POST,
        )
        return post, comments

    workers = min(SAMURAI_SAFE_WORKERS, len(targets))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for post, comments in pool.map(_fetch, targets):
            post["comments"] = comments


# ---------------------------------------------------------------------------
# Facebook profile scraping (public Open Graph meta tags)
# ---------------------------------------------------------------------------

def _extract_og_tag(page: str, key: str) -> str | None:
    match = re.search(rf'property="{key}"[^>]+content="([^"]*)"', page)
    return html.unescape(match.group(1)) if match else None


def _count_to_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return None


def parse_facebook_description(description: str) -> dict:
    """Parse Facebook og:description for pages and personal profiles."""
    result: dict = {"profile_type": "unknown"}

    page_match = re.search(
        r"^(.+?)\.\s+([\d,.]+)\s+.+?\s*[·•]\s*([\d,.]+)\s+.+?\.\s*(.*)$",
        description,
        re.DOTALL,
    )
    if page_match:
        result.update(
            {
                "profile_type": "page",
                "full_name": page_match.group(1).strip(),
                "like_count": _count_to_int(page_match.group(2)),
                "talking_about_count": _count_to_int(page_match.group(3)),
                "biography": page_match.group(4).strip(),
            }
        )
        return result

    personal_match = re.search(
        r"^(.+?)\s+is on Facebook\.\s*(.*)$",
        description,
        re.DOTALL | re.IGNORECASE,
    )
    if personal_match:
        result.update(
            {
                "profile_type": "personal",
                "full_name": personal_match.group(1).strip(),
                "biography": personal_match.group(2).strip(),
            }
        )
        return result

    return result


def _is_direct_image_url(url: str | None) -> bool:
    return bool(url and "scontent" in url and "lookaside" not in url)


def _generic_facebook_bio(text: str) -> bool:
    lowered = (text or "").lower()
    return "is on facebook" in lowered or "join facebook to connect" in lowered


def extract_facebook_numeric_id(page: str) -> str | None:
    for pattern in (r'"userID":"(\d+)"', r'"pageID":"(\d+)"', r'media_id=(\d+)'):
        match = re.search(pattern, page)
        if match:
            return match.group(1)
    return None


def fetch_facebook_mobile_embed(slug: str) -> dict | None:
    """Public mobile page — returns real profile-picture CDN URLs (scontent)."""
    url = f"https://m.facebook.com/{slug}"
    try:
        response = requests.get(url, headers=MOBILE_FB_HEADERS, timeout=30, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    if "login" in response.url.lower() and "next=" in response.url.lower():
        return None

    page = response.text
    title = _extract_og_tag(page, "og:title")
    description = _extract_og_tag(page, "og:description")
    image = _extract_og_tag(page, "og:image")
    profile_url = _extract_og_tag(page, "og:url") or response.url
    if not title and not description:
        return None
    if "log in to facebook" in (title or "").lower():
        return None

    parsed = parse_facebook_description(description or "")
    canonical_slug = slug
    slug_match = re.search(r"facebook\.com/([^/?#]+)", profile_url, re.I)
    if slug_match:
        canonical_slug = slug_match.group(1)

    biography = parsed.get("biography") or ""
    if _generic_facebook_bio(biography):
        biography = ""

    return {
        "username": canonical_slug,
        "full_name": parsed.get("full_name") or title or canonical_slug,
        "biography": biography,
        "profile_type": parsed.get("profile_type", "unknown"),
        "like_count": parsed.get("like_count"),
        "talking_about_count": parsed.get("talking_about_count"),
        "follower_count": parsed.get("like_count"),
        "profile_pic_url": image if _is_direct_image_url(image) else None,
        "profile_url": profile_url,
        "id": extract_facebook_numeric_id(page),
        "source": "facebook_mobile_embed",
    }


def fetch_facebook_plugin_embed(slug: str) -> dict | None:
    """Public page-plugin iframe — works best for Facebook Pages (not personal profiles)."""
    href = f"https://www.facebook.com/{slug}"
    url = (
        "https://www.facebook.com/plugins/page.php"
        f"?adapt_container_width=true&href={requests.utils.quote(href, safe='')}"
        "&tabs=timeline&width=500&height=700&small_header=false&hide_cover=false&show_facepile=true"
    )
    try:
        response = requests.get(
            url,
            headers={"user-agent": DESKTOP_UA, "accept-language": "en-US,en;q=0.9"},
            timeout=30,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    if not text:
        return None

    follower_count = None
    follower_match = re.search(r"([\d,.]+)\s+followers?", text, re.I)
    like_match = re.search(r"([\d,.]+)\s+likes?", text, re.I)
    if follower_match:
        follower_count = _count_to_int(follower_match.group(1))
    elif like_match:
        follower_count = _count_to_int(like_match.group(1))

    profile_pic_url = None
    page_id = None
    full_name = None
    for link in soup.find_all("a", href=True):
        href_value = link["href"]
        name = link.get_text(" ", strip=True)
        if name and name not in {"Follow Page", "Followed", "Share", "Message"} and not full_name:
            full_name = name
        id_match = re.search(r"facebook\.com/(\d+)", href_value)
        if id_match:
            page_id = id_match.group(1)
    for image in soup.find_all("img", src=True):
        src = image["src"]
        if _is_direct_image_url(src):
            profile_pic_url = src
            break

    if not any([full_name, follower_count, profile_pic_url, page_id]):
        return None

    return {
        "username": slug,
        "full_name": full_name or slug,
        "profile_type": "page",
        "follower_count": follower_count,
        "like_count": follower_count,
        "profile_pic_url": profile_pic_url,
        "id": page_id,
        "source": "facebook_plugin_embed",
    }


def fetch_facebook_crawler_embed(slug: str) -> dict | None:
    """Crawler Open Graph — best for page likes, talking-about count, and bio text."""
    url = f"https://www.facebook.com/{slug}"
    try:
        response = requests.get(url, headers=FB_HEADERS, timeout=30, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        return None
    if "login" in response.url.lower() and "next=" in response.url.lower():
        return None

    page = response.text
    title = _extract_og_tag(page, "og:title")
    description = _extract_og_tag(page, "og:description")
    image = _extract_og_tag(page, "og:image")
    profile_url = _extract_og_tag(page, "og:url") or response.url
    if not title and not description:
        return None
    if "log in to facebook" in (title or "").lower():
        return None

    parsed = parse_facebook_description(description or "")
    canonical_slug = slug
    slug_match = re.search(r"facebook\.com/([^/?#]+)", profile_url, re.I)
    if slug_match:
        canonical_slug = slug_match.group(1)

    biography = parsed.get("biography") or ""
    if _generic_facebook_bio(biography):
        biography = ""

    numeric_id = extract_facebook_numeric_id(page)
    if not numeric_id:
        media_id_match = re.search(r"media_id=(\d+)", image or "")
        numeric_id = media_id_match.group(1) if media_id_match else None

    return {
        "username": canonical_slug,
        "full_name": parsed.get("full_name") or title or canonical_slug,
        "biography": biography,
        "profile_type": parsed.get("profile_type", "unknown"),
        "like_count": parsed.get("like_count"),
        "talking_about_count": parsed.get("talking_about_count"),
        "follower_count": parsed.get("like_count"),
        "profile_pic_url": image,
        "profile_url": profile_url,
        "id": numeric_id,
        "source": "facebook_crawler_embed",
    }


def _decode_fb_json_text(raw: str) -> str:
    text = raw.replace("\\/", "/").replace("\\n", "\n").replace('\\"', '"')
    try:
        text = text.encode("utf-8").decode("unicode_escape")
    except (UnicodeDecodeError, ValueError):
        pass
    return _safe_console_text(html.unescape(text))


def _safe_console_text(value: str | None) -> str:
    if not value:
        return ""
    return value.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")


def _lookaside_media_url(media_id: str, thumbnail: bool = False) -> str:
    url = f"https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id={media_id}"
    if thumbnail:
        url += "&get_thumbnail=1"
    return url


def _is_lookaside_url(url: str) -> bool:
    return "lookaside.fbsbx.com" in (url or "")


INVALID_FB_SLUGS = {
    "people",
    "share",
    "login",
    "watch",
    "pages",
    "groups",
    "marketplace",
    "gaming",
    "help",
    "privacy",
    "public",
    "ajax",
    "recover",
    "security",
    "l.php",
    "directory",
    "plugins",
    "dialog",
    "legal",
    "about",
    "facebook",
}


def _is_valid_facebook_slug(slug: str) -> bool:
    if not slug or len(slug) < 4:
        return False
    lowered = slug.lower()
    if lowered in INVALID_FB_SLUGS:
        return False
    if lowered.startswith("profile.php"):
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9.\-_]+", slug))


def _is_facebook_login_redirect(response: requests.Response) -> bool:
    return "login" in response.url.lower() and "next=" in response.url.lower()


def _extract_raw_media_ids_from_page(page: str) -> set[str]:
    """Collect media_id values from Googlebot HTML using multiple patterns."""
    media_ids: set[str] = set()
    patterns = (
        r"lookaside/crawler/media/\?media_id=(\d+)",
        r'"media_id"\s*:\s*"(\d+)"',
        r"media_id=(\d+)",
        r'"photo_id"\s*:\s*"(\d+)"',
        r'"video_id"\s*:\s*"(\d+)"',
    )
    for pattern in patterns:
        media_ids.update(re.findall(pattern, page))
    return media_ids


def _lookaside_preview_url(media_id: str, *, is_video: bool = False) -> str:
    if is_video:
        return _lookaside_media_url(media_id, thumbnail=True)
    return _lookaside_media_url(media_id, thumbnail=True)


def _verified_lookaside_item(
    media_id: str,
    probed: dict,
    *,
    owner_slug: str = "",
    is_target: bool = True,
    source: str = "lookaside_probe",
) -> dict:
    is_video = bool(probed.get("is_video"))
    thumb = _lookaside_media_url(media_id, thumbnail=True)
    full = _lookaside_media_url(media_id)
    return {
        "media_id": media_id,
        "url": full,
        "thumbnail": thumb,
        "preview_url": _lookaside_preview_url(media_id, is_video=is_video),
        "type": "video" if is_video else "image",
        "source": source,
        "owner_username": owner_slug,
        "profile_url": _facebook_profile_url_from_slug(owner_slug) if owner_slug else None,
        "is_target_profile": is_target,
        "verified": True,
        "content_type": probed.get("content_type"),
        "live_url": full,
    }


def _photos_from_media_ids(
    media_ids: set[str],
    source: str = "googlebot_raw",
    session: requests.Session | None = None,
) -> list[dict]:
    """Build photo dicts only for media_ids that return real image bytes."""
    photos: list[dict] = []
    requester = session or requests.Session()
    for media_id in sorted(media_ids):
        probed = _probe_lookaside_media_id(media_id, requester)
        if not probed or probed.get("is_video"):
            continue
        photos.append(_verified_lookaside_item(media_id, probed, source=source))
    return photos


def _verify_facebook_lookaside_collections(
    photos: list[dict],
    videos: list[dict],
    session: requests.Session,
    *,
    max_probe: int = MAX_FB_PHOTOS,
) -> tuple[list[dict], list[dict]]:
    """Drop lookaside media_ids that return HTML placeholders; keep direct CDN URLs."""
    verified_photos: list[dict] = []
    verified_videos: list[dict] = []
    seen_ids: set[str] = set()
    probed = 0

    def media_id_from(item: dict) -> str | None:
        mid = item.get("media_id")
        if mid:
            return str(mid)
        url = item.get("url") or item.get("live_url") or ""
        match = re.search(r"media_id=(\d+)", url)
        return match.group(1) if match else None

    for photo in photos:
        if photo.get("verified"):
            verified_photos.append(photo)
            mid = media_id_from(photo)
            if mid:
                seen_ids.add(mid)
            continue
        mid = media_id_from(photo)
        if not mid:
            url = photo.get("url") or ""
            if url and not _is_lookaside_url(url):
                verified_photos.append(photo)
            continue
        if mid in seen_ids or probed >= max_probe:
            continue
        seen_ids.add(mid)
        probed += 1
        result = _probe_lookaside_media_id(mid, session)
        if not result or result.get("is_video"):
            continue
        item = _verified_lookaside_item(
            mid,
            result,
            owner_slug=str(photo.get("owner_username") or ""),
            is_target=photo.get("is_target_profile") is not False,
            source=str(photo.get("source") or "lookaside_probe"),
        )
        verified_photos.append(item)

    for video in videos:
        if video.get("verified"):
            verified_videos.append(video)
            continue
        mid = media_id_from(video)
        if not mid:
            url = video.get("url") or ""
            if url and not _is_lookaside_url(url):
                verified_videos.append(video)
            continue
        if mid in seen_ids:
            continue
        result = _probe_lookaside_media_id(mid, session)
        if not result:
            continue
        item = _verified_lookaside_item(
            mid,
            result,
            owner_slug=str(video.get("owner_username") or ""),
            is_target=video.get("is_target_profile") is not False,
            source=str(video.get("source") or "lookaside_probe"),
        )
        if result.get("is_video"):
            item["is_reel"] = video.get("is_reel", False)
            item["title"] = video.get("title") or f"Media {mid}"
            verified_videos.append(item)
        else:
            verified_photos.append(item)

    return verified_photos, verified_videos


def _facebook_media_cache_path(slug: str) -> str:
    return f"{slug_to_filename(slug)}_facebook_media_index.json"


def _load_facebook_media_cache(slug: str) -> list[dict]:
    path = _facebook_media_cache_path(slug)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data.get("verified_media") or []
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_facebook_media_cache(slug: str, items: list[dict]) -> None:
    path = _facebook_media_cache_path(slug)
    payload = {
        "username": slug,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "verified_media": items,
    }
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _probe_lookaside_media_id(
    media_id: str, session: requests.Session | None = None
) -> dict | None:
    """Verify a media_id is downloadable via Facebook lookaside crawler CDN."""
    requester = session or requests.Session()
    headers = {**GOOGLEBOT_HEADERS, "Referer": "https://www.facebook.com/"}
    for url in (
        _lookaside_media_url(media_id),
        _lookaside_media_url(media_id, thumbnail=True),
    ):
        try:
            response = requester.get(url, headers=headers, timeout=30, stream=True)
            if response.status_code != 200:
                continue
            content_type = (response.headers.get("content-type") or "").lower()
            if "text/html" in content_type:
                continue
            content = response.content
            if len(content) < 256 and "image" not in content_type and "video" not in content_type:
                continue
            return {
                "media_id": media_id,
                "url": _lookaside_media_url(media_id),
                "content_type": content_type,
                "size": len(content),
                "is_video": "video" in content_type,
            }
        except requests.RequestException:
            continue
    return None


def _crawl_facebook_page_media_ids(
    slug: str, session: requests.Session
) -> tuple[set[str], str]:
    """Crawl high-yield subpages for lookaside media_id values."""
    media_ids: set[str] = set()
    combined_page = ""
    # /photos and /photos_by are the profile's own album surfaces (not "Others named").
    for path in ("/photos", "/photos_by", "/photos_all", "/reels", "/about_work_and_education", "/about_places"):
        try:
            response = session.get(
                f"https://www.facebook.com/{slug}{path}",
                timeout=30,
                allow_redirects=True,
            )
        except requests.RequestException:
            continue
        if response.status_code != 200 or _is_facebook_login_redirect(response):
            continue
        combined_page += response.text
        media_ids.update(_extract_raw_media_ids_from_page(response.text))
        time.sleep(0.8)
    return media_ids, combined_page


def _extract_others_named_media_ids(page: str) -> set[str]:
    """Media IDs inside 'Others named …' / similar-name widgets (other people)."""
    ids: set[str] = set()
    if not page:
        return ids
    patterns = (
        r"Others named.{0,12000}?(?=Others named|Others with a similar|See more people|Places|Friends|Intro|$)",
        r"people with the same name.{0,12000}?(?=Others named|Others with a similar|See more people|$)",
        r"Others with a similar name.{0,8000}?(?=Others named|See more people|Places|Friends|$)",
    )
    for pattern in patterns:
        for chunk in re.findall(pattern, page, flags=re.I | re.S):
            ids.update(re.findall(r"media_id=(\d+)", chunk))
            ids.update(re.findall(r'"media_id"\s*:\s*"(\d+)"', chunk))
            ids.update(re.findall(r"lookaside/crawler/media/\?media_id=(\d+)", chunk))
    return ids


def _extract_foreign_user_avatar_media_ids(page: str, target_slug: str) -> set[str]:
    """Media IDs used as profile_picture for OTHER users (similar-people cards).

    Facebook embeds those avatars on the target profile page; they must never
    appear in the searched user's photo gallery.
    """
    ids: set[str] = set()
    if not page:
        return ids
    target_key = (target_slug or "").lower()
    normalized = page.replace("\\/", "/").replace('\\"', '"')

    # profile_picture uri with media_id, near a User card URL.
    for match in re.finditer(
        r'profile_picture"\s*:\s*\{[^}]{0,400}?media_id=(\d+)',
        normalized,
        flags=re.I,
    ):
        media_id = match.group(1)
        ctx = normalized[max(0, match.start() - 400) : match.end() + 500]
        # Explicit people/pfbid cards are always other profiles.
        if re.search(r"facebook\.com/people/", ctx, flags=re.I):
            ids.add(media_id)
            continue
        for candidate in re.findall(r"facebook\.com/([A-Za-z0-9.\-_]+)", ctx):
            low = candidate.lower()
            if low in INVALID_FB_SLUGS or low == target_key:
                continue
            if low in {"photo", "photos", "watch", "reel", "reels", "videos"}:
                continue
            ids.add(media_id)
            break

    # item_title + profile_picture pattern used by "Others named" lists.
    for match in re.finditer(
        r'item_title".{0,200}?profile_picture".{0,200}?media_id=(\d+)',
        normalized,
        flags=re.I | re.S,
    ):
        ids.add(match.group(1))

    return ids


def _is_default_facebook_avatar_url(url: str) -> bool:
    low = (url or "").lower()
    if not low:
        return True
    # Common FB silhouette / empty avatar asset.
    if "84702798_579370612644419" in low:
        return True
    if low.rstrip("/").endswith("fbcdn.net"):
        return True
    return False


def _profile_uid_from_pages(pages: list[str], slug: str) -> str | None:
    """Resolve numeric Facebook user id for the profile (pb.<uid> album owner)."""
    for page in pages:
        # photo.php?fbid=…&set=pb.<uid>.-2207520000 is the profile's own album.
        match = re.search(r"set=pb\.(\d+)\.-?\d+", page)
        if match:
            return match.group(1)
        # og:image lookaside media_id is often the profile uid.
        og = re.search(
            rf'og:image[^>]+media_id=(\d+)|media_id=(\d+)[^>]+og:image',
            page,
            flags=re.I,
        )
        if og:
            return og.group(1) or og.group(2)
        og2 = re.search(
            r'property="og:image"\s+content="[^"]*media_id=(\d+)"',
            page,
            flags=re.I,
        )
        if og2:
            return og2.group(1)
    return None


def _parse_target_photo_nodes(page: str, slug: str, profile_uid: str) -> list[dict]:
    """Parse __typename Photo nodes that belong to this profile's album only."""
    if not page or not profile_uid:
        return []
    normalized = page.replace("\\/", "/")
    photos: list[dict] = []
    seen: set[str] = set()
    # Photo nodes include id + facebook photo.php URL with set=pb.<uid>
    pattern = re.compile(
        r'"__typename":"Photo","id":"(\d+)".{0,1600}?"url":"(https://www\.facebook\.com/photo\.php\?[^"]+)"',
        flags=re.S,
    )
    for match in pattern.finditer(normalized):
        fbid, photo_url = match.group(1), match.group(2).replace("&amp;", "&")
        if fbid in seen:
            continue
        # Only this profile's album: set=pb.<profile_uid>
        if f"set=pb.{profile_uid}." not in photo_url:
            continue
        seen.add(fbid)
        chunk = match.group(0)
        width = height = None
        dim = re.search(r'"viewer_image":\{"uri":"[^"]+","height":(\d+),"width":(\d+)', chunk)
        if dim:
            height, width = int(dim.group(1)), int(dim.group(2))
        # Prefer lookaside thumbnail URI from the node when present.
        lookaside = None
        uri_match = re.search(
            r'"viewer_image":\{"uri":"(https://lookaside[^"]+)"',
            chunk,
        ) or re.search(r'"image":\{"uri":"(https://lookaside[^"]+)"', chunk)
        if uri_match:
            lookaside = uri_match.group(1).replace("&amp;", "&")

        embed_href = photo_url
        embed_url = (
            "https://www.facebook.com/plugins/post.php?"
            + urlencode({"href": embed_href, "show_text": "false", "width": "500"})
        )
        photos.append(
            {
                "fbid": fbid,
                "media_id": fbid,
                "url": lookaside or photo_url,
                "live_url": lookaside or photo_url,
                "page_url": photo_url,
                "embed_url": embed_url,
                "album_url": f"https://www.facebook.com/{slug}/photos",
                "type": "image",
                "source": "photos_by",
                "owner_username": slug,
                "profile_url": _facebook_profile_url_from_slug(slug),
                "is_target_profile": True,
                "render_as": "facebook_embed",
                "width": width,
                "height": height,
                "verified": True,
            }
        )
    return photos


def fetch_public_target_album_photos(slug: str, *, limit: int = 12) -> list[dict]:
    """Fetch only the searched profile's posted photos (not similar-account avatars).

    Uses Photo nodes on /photos_by with set=pb.<profile_uid>. Direct lookaside
    bytes are often blocked publicly, so each photo includes an embed_url for
    in-app Facebook post embeds + page_url for media-proxy / open links.
    """
    session = requests.Session()
    session.headers.update(GOOGLEBOT_HEADERS)
    pages: list[str] = []

    for path in ("", "/photos_by", "/photos"):
        try:
            response = session.get(
                f"https://www.facebook.com/{slug}{path}",
                timeout=30,
                allow_redirects=True,
            )
        except requests.RequestException:
            continue
        if response.status_code != 200 or _is_facebook_login_redirect(response):
            continue
        pages.append(response.text)
        time.sleep(0.25)

    if not pages:
        return []

    foreign = set()
    for page in pages:
        foreign |= _extract_foreign_user_avatar_media_ids(page, slug)
        foreign |= _extract_others_named_media_ids(page)

    profile_uid = _profile_uid_from_pages(pages, slug)
    photos: list[dict] = []
    seen: set[str] = set()

    for page in pages:
        for item in _parse_target_photo_nodes(page, slug, profile_uid or ""):
            fbid = str(item.get("fbid") or item.get("media_id") or "")
            if not fbid or fbid in seen or fbid in foreign:
                continue
            # Skip tiny avatar-sized foreign cards if dimensions known and tiny.
            width = item.get("width") or 0
            height = item.get("height") or 0
            if width and height and width <= 80 and height <= 80:
                continue
            seen.add(fbid)
            # If lookaside serves real image bytes, attach for media-proxy grid.
            probed = _probe_lookaside_media_id(fbid, session)
            if probed and not probed.get("is_video") and "image" in (probed.get("content_type") or ""):
                item["url"] = _lookaside_media_url(fbid)
                item["live_url"] = item["url"]
                item["display_url"] = _lookaside_media_url(fbid, thumbnail=True)
                item["preview_url"] = item["display_url"]
                item["content_type"] = probed.get("content_type")
                item["render_as"] = "image"
            photos.append(item)
            if len(photos) >= limit:
                return photos

    return photos[:limit]


def _merge_target_album_photos(existing: list[dict], album: list[dict]) -> list[dict]:
    """Prefer album (target-owned) photos; upgrade ownership when media_id matches."""
    by_id: dict[str, dict] = {}
    ordered: list[dict] = []

    def _mid(item: dict) -> str:
        media_id = item.get("media_id")
        if media_id:
            return str(media_id)
        url = item.get("url") or item.get("live_url") or ""
        match = re.search(r"media_id=(\d+)", url)
        return match.group(1) if match else ""

    for photo in existing:
        item = dict(photo)
        key = _mid(item) or item.get("url") or item.get("live_url") or ""
        if key and key in by_id:
            continue
        if key:
            by_id[key] = item
        ordered.append(item)

    for photo in album:
        item = dict(photo)
        item["is_target_profile"] = True
        item["owner_username"] = item.get("owner_username") or photo.get("owner_username")
        key = _mid(item) or item.get("url") or ""
        if key and key in by_id:
            existing_item = by_id[key]
            existing_item["is_target_profile"] = True
            existing_item["owner_username"] = item.get("owner_username") or existing_item.get("owner_username")
            existing_item["source"] = item.get("source") or existing_item.get("source")
            existing_item["album_url"] = item.get("album_url") or existing_item.get("album_url")
            if item.get("verified"):
                existing_item["verified"] = True
            continue
        if key:
            by_id[key] = item
        ordered.append(item)

    # Profile picture first, then target album photos, then the rest.
    profile_pics = [p for p in ordered if p.get("type") == "profile_picture"]
    target_posts = [
        p for p in ordered
        if p.get("type") != "profile_picture" and p.get("is_target_profile") is True
    ]
    other = [
        p for p in ordered
        if p.get("type") != "profile_picture" and p.get("is_target_profile") is not True
    ]
    return [*profile_pics, *target_posts, *other]


def _discover_similar_slugs_for_locked(
    slug: str,
    full_name: str,
    raw_pages: list[str],
    owner_map: dict[str, str],
) -> list[str]:
    """Similar slugs only from target profile HTML — never name-guess other accounts."""
    similar_slugs: list[str] = []
    for item in _extract_similar_slugs_from_pages(raw_pages, slug):
        if item not in similar_slugs:
            similar_slugs.append(item)
    for entry in fetch_facebook_directory_profiles(full_name, slug):
        username = entry.get("username")
        if username and username not in similar_slugs:
            similar_slugs.append(username)
    for owner in owner_map.values():
        if owner.lower() != slug.lower() and owner not in similar_slugs:
            similar_slugs.append(owner)
    return similar_slugs


def discover_locked_facebook_media(
    slug: str,
    full_name: str,
    raw_pages: list[str],
    session: requests.Session | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    CID locked-profile technique (strict ownership):
    - Target photos: media_ids found only on the exact searched username's pages
    - Similar photos: media_ids from profiles explicitly linked in target HTML
    """
    requester = session or requests.Session()
    requester.headers.update(GOOGLEBOT_HEADERS)
    target_slug_l = slug.lower()

    owner_map: dict[str, str] = {}
    for page in raw_pages:
        owner_map.update(_extract_media_owner_map(page, slug))

    target_page_ids: set[str] = set()
    for page in raw_pages:
        target_page_ids.update(_extract_raw_media_ids_from_page(page))

    extra_ids, target_page = _crawl_facebook_page_media_ids(slug, requester)
    target_page_ids |= extra_ids
    if target_page:
        owner_map.update(_extract_media_owner_map(target_page, slug))
        raw_pages = raw_pages + [target_page]
        target_page_ids.update(_extract_raw_media_ids_from_page(target_page))

    target_ids: set[str] = set()
    for media_id in target_page_ids:
        owner = owner_map.get(media_id, "")
        if not owner or owner.lower() == target_slug_l:
            target_ids.add(media_id)

    similar_slugs = _discover_similar_slugs_for_locked(slug, full_name, raw_pages, owner_map)
    similar_ids_by_owner: dict[str, set[str]] = {}
    for sim_slug in similar_slugs[:8]:
        if sim_slug.lower() == target_slug_l:
            continue
        sim_ids, sim_page = _crawl_facebook_page_media_ids(sim_slug, requester)
        if sim_ids:
            similar_ids_by_owner[sim_slug] = sim_ids
        if sim_page:
            owner_map.update(_extract_media_owner_map(sim_page, slug))

    photos: list[dict] = []
    videos: list[dict] = []
    verified_cache: list[dict] = []
    seen_ids: set[str] = set()

    def add_verified(media_id: str, owner: str) -> None:
        if media_id in seen_ids:
            return
        seen_ids.add(media_id)
        probed = _probe_lookaside_media_id(media_id, requester)
        if not probed:
            return
        verified_cache.append({**probed, "owner_username": owner})
        is_target = owner.lower() == target_slug_l
        item = {
            "media_id": media_id,
            "url": _lookaside_media_url(media_id),
            "type": "video" if probed["is_video"] else "image",
            "source": "lookaside_probe",
            "owner_username": owner,
            "profile_url": _facebook_profile_url_from_slug(owner),
            "is_target_profile": is_target,
            "content_type": probed.get("content_type"),
            "live_url": _lookaside_media_url(media_id),
        }
        if probed["is_video"]:
            videos.append(
                {
                    **item,
                    "title": f"Media {media_id}",
                    "is_reel": False,
                    "thumbnail": _lookaside_media_url(media_id, thumbnail=True),
                }
            )
        else:
            photos.append(item)
        time.sleep(0.35)

    for media_id in sorted(target_ids, key=lambda value: int(value) if value.isdigit() else 0):
        add_verified(media_id, slug)

    for sim_slug, sim_ids in similar_ids_by_owner.items():
        for media_id in sorted(sim_ids, key=lambda value: int(value) if value.isdigit() else 0):
            add_verified(media_id, sim_slug)

    target_verified = [entry for entry in verified_cache if entry.get("owner_username", "").lower() == target_slug_l]
    if target_verified:
        _save_facebook_media_cache(slug, target_verified)

    return photos, videos, verified_cache


def _title_to_profile_name(title: str) -> str:
    name = title.split("•")[0].split("|")[0].strip()
    name = re.sub(r"\s+Reels$", "", name, flags=re.I).strip()
    lowered = name.lower()
    if not name or lowered in {"facebook", "error facebook"} or "log in" in lowered:
        return ""
    return name


def _is_facebook_login_blocked(profile: dict, requested_slug: str) -> bool:
    """True when Facebook returned a login page instead of the requested profile."""
    personal = profile.get("personal_details") or {}
    if personal.get("Profile Status") or personal.get("Similar Profiles"):
        return False
    if profile.get("photos") or profile.get("similar_profiles"):
        return False
    full_name = (profile.get("full_name") or "").strip()
    if full_name and full_name.lower() not in {
        requested_slug.lower(),
        "facebook",
        "log in to facebook | facebook",
    }:
        return False

    profile_url = (profile.get("profile_url") or "").lower()
    full_name = (profile.get("full_name") or "").lower()
    username = (profile.get("username") or "").lower()
    requested = requested_slug.lower()
    if "facebook.com/login" in profile_url:
        return True
    if "log in to facebook" in full_name or full_name.startswith("facebook"):
        return True
    if username in INVALID_FB_SLUGS and username != requested:
        return True
    if username == "login" and username != requested:
        return True
    return False


def _facebook_login_blocked_message(slug: str) -> str:
    return (
        f"Facebook blocked the request for '{slug}' (redirected to login page). "
        "This usually means too many requests from this IP. "
        "Wait 10–30 minutes and try again, or set FB_C_USER + FB_XS session cookies."
    )


def _facebook_profile_url_from_slug(slug: str) -> str:
    if slug.startswith("profile.php"):
        return f"https://www.facebook.com/{slug}"
    return f"https://www.facebook.com/{slug}/"


def _instagram_profile_url(username: str) -> str:
    clean = username.strip().lstrip("@").split("/")[0].split("?")[0]
    return f"https://www.instagram.com/{clean}/"


def _directory_path_from_name(full_name: str) -> str | None:
    parts = [part for part in re.split(r"\s+", full_name.strip()) if part]
    if len(parts) < 2:
        return None
    first_initial = parts[0][0].lower()
    last_initial = parts[-1][0].lower()
    if not first_initial.isalpha() or not last_initial.isalpha():
        return None
    return f"/directory/people/{first_initial}/{parts[0].lower()}/{last_initial}/"


def _extract_media_owner_map(page: str, target_slug: str) -> dict[str, str]:
    """Map lookaside media_id -> Facebook username slug from nearby HTML context.

    Media inside "Others named …" carousels must not be attributed to the target
    profile just because the page URL mentions the target slug nearby.
    """
    owners: dict[str, str] = {}
    target_key = (target_slug or "").lower()
    for media_id in dict.fromkeys(re.findall(r"media_id=(\d+)", page)):
        index = page.find(f"media_id={media_id}")
        if index < 0:
            continue
        context = page[max(0, index - 900) : index + 500].replace("\\/", "/")
        others_named = bool(
            re.search(
                r"Others named|people with the same name|Similar Profiles|See more people",
                context,
                re.I,
            )
        )
        slugs = re.findall(r"facebook\.com/([A-Za-z0-9.\-_]+)", context)
        owner = None
        for candidate in reversed(slugs):
            if not _is_valid_facebook_slug(candidate):
                continue
            # In the "Others named" widget, skip the target slug — those thumbnails
            # belong to other people with the same display name.
            if others_named and candidate.lower() == target_key:
                continue
            owner = candidate
            break
        if owner:
            owners[media_id] = owner
        elif others_named:
            # Explicitly mark as non-target so callers do not default to the seed.
            owners[media_id] = ""
    return owners


def _extract_similar_slugs_from_pages(pages: list[str], target_slug: str) -> list[str]:
    target = target_slug.lower()
    found: list[str] = []
    for page in pages:
        for owner in _extract_media_owner_map(page, target_slug).values():
            if owner.lower() != target and owner not in found:
                found.append(owner)
        for match in re.finditer(
            r'"profile_url"\s*:\s*"((?:https?:)?\\?/\\?/(?:www\.)?facebook\.com/[^"\\]+)"',
            page,
        ):
            url = _decode_fb_json_text(match.group(1)).replace("\\/", "/")
            if not url.startswith("http"):
                url = "https://" + url.lstrip("/")
            slug_match = re.search(r"facebook\.com/(?:pages/[^/]+/)?([A-Za-z0-9.\-_]+)", url, re.I)
            if slug_match:
                slug = slug_match.group(1)
                if (
                    slug.lower() != target
                    and slug not in found
                    and _is_valid_facebook_slug(slug)
                ):
                    found.append(slug)
    return found


def _probe_facebook_profile_brief(slug: str, *, fast: bool = False) -> dict | None:
    """Lightweight Facebook profile probe using public embed surfaces."""
    timeout = FAST_HTTP_TIMEOUT if fast else 20
    mobile = plugin = crawler = None
    try:
        mobile = fetch_facebook_mobile_embed(slug)
    except Exception:
        pass
    if not mobile:
        try:
            plugin = fetch_facebook_plugin_embed(slug)
        except Exception:
            pass
    if not mobile and not plugin:
        try:
            crawler = fetch_facebook_crawler_embed(slug)
        except Exception:
            pass
    merged = merge_facebook_public_profiles(mobile, plugin, crawler)
    full_name = (merged.get("full_name") or "").strip()
    if not full_name or full_name.lower() in {"facebook", "log in to facebook", slug.lower()}:
        try:
            response = requests.get(
                f"https://www.facebook.com/{slug}",
                headers=GOOGLEBOT_HEADERS,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        page = response.text
        title_match = re.search(r"<title>([^<]+)</title>", page, re.I)
        title = html.unescape(title_match.group(1)) if title_match else ""
        title = title.replace("&#064;", "@")
        full_name = title.split("•")[0].split("|")[0].strip()
        if full_name.lower() in {"facebook", "log in to facebook"}:
            return None
        numeric_id = extract_facebook_numeric_id(page)
        return {
            "username": slug,
            "full_name": full_name,
            "profile_url": _facebook_profile_url_from_slug(slug),
            "id": numeric_id,
            "profile_pic_url": None,
        }

    return {
        "username": slug,
        "full_name": full_name,
        "profile_url": merged.get("profile_url") or _facebook_profile_url_from_slug(slug),
        "id": merged.get("id"),
        "profile_pic_url": merged.get("profile_pic_url"),
    }


def _instagram_username_exists(username: str) -> bool:
    """Quick check that an Instagram handle resolves (not 404 / unavailable)."""
    try:
        response = requests.get(
            f"https://www.instagram.com/{username}/",
            headers=MOBILE_PROFILE_HEADERS,
            timeout=12,
            allow_redirects=True,
        )
    except requests.RequestException:
        return False
    if response.status_code == 404:
        return False
    page = response.text
    if "Sorry, this page isn't available." in page:
        return False
    low = page.lower()
    handle = username.lower()
    return handle in low or f"@{handle}" in low or f"/{handle}/" in low


def _probe_instagram_profile_brief(username: str) -> dict | None:
    """Fetch avatar + up to 2 posts for a similar Instagram handle."""
    if not _instagram_username_exists(username):
        return None
    try:
        profile = fetch_profile_from_embed(username)
    except ValueError:
        return None
    except RuntimeError:
        try:
            profile = fetch_profile_from_public_page(username)
        except Exception:
            return None

    profile = _sanitize_instagram_profile(profile)
    if profile.get("is_private") and not profile.get("profile_pic_url") and not profile.get("posts"):
        return {
            "username": profile.get("username") or username,
            "full_name": profile.get("full_name") or username,
            "profile_pic_url": None,
            "posts": [],
            "is_private": True,
        }

    if not profile.get("profile_pic_url") and not profile.get("posts") and profile.get("follower_count") is None:
        return None

    return {
        "username": profile.get("username") or username,
        "full_name": profile.get("full_name") or username,
        "profile_pic_url": profile.get("profile_pic_url"),
        "posts": list(profile.get("posts") or [])[:2],
        "is_private": profile.get("is_private", False),
    }


def fetch_facebook_directory_profiles(full_name: str, target_slug: str) -> list[dict]:
    path = _directory_path_from_name(full_name)
    if not path:
        return []
    try:
        response = requests.get(
            f"https://www.facebook.com{path}",
            headers=GOOGLEBOT_HEADERS,
            timeout=25,
        )
    except requests.RequestException:
        return []
    if response.status_code != 200:
        return []

    profiles: list[dict] = []
    seen: set[str] = set()
    page = response.text
    for match in re.finditer(r"facebook\.com/([A-Za-z0-9.\-_]+)", page.replace("\\/", "/")):
        slug = match.group(1)
        if slug.lower() == target_slug.lower():
            continue
        if not _is_valid_facebook_slug(slug) or slug in seen:
            continue
        seen.add(slug)
        profiles.append(
            {
                "username": slug,
                "profile_url": _facebook_profile_url_from_slug(slug),
                "source": "facebook_directory",
            }
        )
        if len(profiles) >= 15:
            break
    return profiles


def _is_facebook_login_wall_text(text: str) -> bool:
    low = (text or "").lower()
    if len(low) < 12:
        return False
    markers = (
        "log in to facebook",
        "email address or mobile",
        "email or phone",
        "forgotten password",
        "create new account",
        "explore the things you love",
    )
    return any(marker in low for marker in markers)


def fetch_facebook_others_named_by_search(
    full_name: str,
    target_slug: str,
    *,
    limit: int = 8,
) -> list[dict]:
    """Find profiles with the same display name (Facebook 'Others named …' equivalent)."""
    clean_name = (full_name or "").strip()
    if len(clean_name) < 3:
        return []

    query = f'site:facebook.com "{clean_name}"'
    hits: list[dict] = []
    try:
        from ddgs import DDGS

        for backend in ("auto", "bing", "yahoo"):
            try:
                hits = [
                    h for h in DDGS().text(query, max_results=limit + 8, backend=backend)
                    if isinstance(h, dict)
                ]
            except Exception:
                hits = []
            if hits:
                break
    except ImportError:
        hits = []

    if not hits:
        try:
            response = requests.get(
                "https://www.bing.com/search",
                params={"q": query},
                headers={"User-Agent": DESKTOP_UA, "accept-language": "en-US,en;q=0.9"},
                timeout=20,
            )
        except requests.RequestException:
            response = None
        if response and response.status_code == 200:
            from urllib.parse import unquote

            for match in re.finditer(r'<a href="(https?://[^"]+)"[^>]*>([^<]{2,80})</a>', response.text):
                hits.append({"url": unquote(match.group(1)), "title": match.group(2).strip()})

    skip = {
        "login", "home", "watch", "recover", "help", "pages", "groups", "search",
        "sharer", "share", "l.php", "ajax", "directory", "people", "public",
        "profile.php", "about", "photos", "videos", "friends", "reels",
    }
    slugs: list[str] = []
    for hit in hits:
        url = str(hit.get("href") or hit.get("url") or "").strip()
        if "facebook.com" not in url.lower():
            continue
        slug_match = re.search(
            r"facebook\.com/(?:profile\.php\?id=)?([A-Za-z0-9.\-_]+)",
            url,
            re.I,
        )
        if not slug_match:
            continue
        slug = slug_match.group(1).strip("/")
        if slug.lower() in skip or slug.lower() == target_slug.lower():
            continue
        if slug not in slugs:
            slugs.append(slug)

    name_parts = [p.lower() for p in re.split(r"\s+", clean_name) if len(p) > 2]
    profiles: list[dict] = []
    for slug in slugs:
        if len(profiles) >= limit:
            break
        brief = _probe_facebook_profile_brief(slug, fast=True)
        title_hint = next(
            (str(h.get("title") or "") for h in hits if slug in str(h.get("url") or h.get("href") or "")),
            "",
        )
        brief_name = (brief or {}).get("full_name") or title_hint or clean_name
        brief_name_low = brief_name.lower()
        if name_parts and not any(part in brief_name_low or part in slug.lower() for part in name_parts):
            continue
        profiles.append(
            {
                "username": slug,
                "full_name": brief_name,
                "profile_url": (brief or {}).get("profile_url") or _facebook_profile_url_from_slug(slug),
                "profile_pic_url": (brief or {}).get("profile_pic_url"),
                "id": (brief or {}).get("id"),
                "source": "others_named",
                "exists": brief is not None,
            }
        )
    return profiles


def _fetch_facebook_profile_post_previews(slug: str, limit: int = 2) -> list[dict]:
    """Lightweight post/media preview for similar-profile cards."""
    try:
        response = requests.get(
            f"https://www.facebook.com/{slug}",
            headers=GOOGLEBOT_HEADERS,
            timeout=20,
            allow_redirects=True,
        )
    except requests.RequestException:
        return []
    if response.status_code != 200:
        return []

    page = response.text
    previews: list[dict] = []
    for post in parse_mobile_timeline_posts(page)[: limit + 2]:
        text = (post.get("text") or "").strip()
        if _is_facebook_login_wall_text(text):
            continue
        previews.append(
            {
                "text": text[:240],
                "type": "post",
                "source": "similar_preview",
            }
        )
        if len(previews) >= limit:
            break
    if len(previews) < limit:
        photos, videos = _extract_googlebot_media(page)
        for item in photos + videos:
            if len(previews) >= limit:
                break
            url = item.get("url")
            if not url:
                continue
            previews.append(
                {
                    "url": url,
                    "thumbnail": url,
                    "type": "video" if item in videos else "image",
                    "source": "similar_preview",
                }
            )
    return previews[:limit]


def _build_facebook_similar_profiles(
    photos: list[dict],
    pages: list[str],
    target_slug: str,
    full_name: str = "",
    *,
    fast: bool = False,
    seed_username: str | None = None,
) -> list[dict]:
    """Similar profiles — prefer Facebook 'Others named …' over username variants."""
    similar_limit = FAST_SIMILAR_PROFILE_LIMIT if fast else 8
    similar_slugs: list[str] = []
    profiles: list[dict] = []
    seen_slugs: set[str] = {target_slug.lower()}

    def add_slug(slug: str) -> bool:
        if not slug or not _is_valid_facebook_slug_candidate(slug):
            return False
        key = slug.lower()
        if key in seen_slugs:
            return False
        seen_slugs.add(key)
        similar_slugs.append(slug)
        return True

    for slug in _extract_similar_slugs_from_pages(pages, target_slug):
        add_slug(slug)

    if full_name:
        for entry in fetch_facebook_directory_profiles(full_name, target_slug):
            add_slug(entry.get("username") or "")
        for entry in fetch_facebook_others_named_by_search(
            full_name, target_slug, limit=similar_limit
        ):
            slug = entry.get("username") or ""
            if not slug or slug.lower() in seen_slugs:
                continue
            seen_slugs.add(slug.lower())
            card = dict(entry)
            card.setdefault("profile_url", _facebook_profile_url_from_slug(slug))
            owner_photos = [
                photo
                for photo in photos
                if (photo.get("owner_username") or "").lower() == slug.lower()
            ]
            if owner_photos:
                card["photos"] = owner_photos[:2]
                card["photo_count"] = len(owner_photos)
            profiles.append(card)

    for photo in photos:
        owner = photo.get("owner_username") or ""
        if owner and owner.lower() != target_slug.lower():
            add_slug(owner)

    if len(profiles) < similar_limit and seed_username:
        for entry in build_similar_username_profiles(
            seed_username,
            platform="facebook",
            fast=fast,
            limit=max(2, similar_limit - len(profiles)),
            exclude=target_slug,
            verify_exists=False,
            enrich=False,
        ):
            slug = entry.get("username") or ""
            if slug.lower() in seen_slugs:
                continue
            seen_slugs.add(slug.lower())
            entry["source"] = entry.get("source") or "username_variation"
            profiles.append(entry)

    def _similar_card(slug: str) -> dict:
        brief = _probe_facebook_profile_brief(slug, fast=fast)
        similar_photos = [
            photo
            for photo in photos
            if (photo.get("owner_username") or "").lower() == slug.lower()
        ]
        post_previews: list[dict] = []
        if not similar_photos and not fast:
            post_previews = _fetch_facebook_profile_post_previews(slug, limit=2)
        return {
            "username": slug,
            "full_name": (brief or {}).get("full_name") or slug,
            "profile_url": (brief or {}).get("profile_url") or _facebook_profile_url_from_slug(slug),
            "id": (brief or {}).get("id"),
            "profile_pic_url": (brief or {}).get("profile_pic_url"),
            "photos": similar_photos[:2] or post_previews,
            "posts": post_previews,
            "photo_count": len(similar_photos) or len(post_previews),
            "source": "others_named_similar",
        }

    existing_usernames = {(p.get("username") or "").lower() for p in profiles}
    remaining = [
        slug
        for slug in similar_slugs
        if slug.lower() not in existing_usernames
    ][: max(0, similar_limit - len(profiles))]

    if fast and remaining:
        with ThreadPoolExecutor(max_workers=min(4, len(remaining))) as pool:
            futures = [pool.submit(_similar_card, slug) for slug in remaining]
            for fut in as_completed(futures):
                try:
                    profiles.append(fut.result())
                except Exception:
                    continue
    else:
        for slug in remaining:
            profiles.append(_similar_card(slug))

    return profiles[:similar_limit]


def enrich_facebook_photo_ownership(
    photos: list[dict],
    pages: list[str],
    target_slug: str,
    full_name: str = "",
    *,
    fast: bool = False,
    seed_username: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Attach profile_url per photo and build similar_profiles list."""
    owner_maps: dict[str, str] = {}
    for page in pages:
        owner_maps.update(_extract_media_owner_map(page, target_slug))

    target_key = (target_slug or "").lower()
    enriched: list[dict] = []
    for photo in photos:
        item = dict(photo)
        media_id = item.get("media_id")
        if not media_id and item.get("url"):
            media_match = re.search(r"media_id=(\d+)", item["url"])
            media_id = media_match.group(1) if media_match else None
            if media_id:
                item["media_id"] = media_id

        # Strict ownership: only the searched profile's own media.
        # "Others named …" thumbnails must never enter the target gallery.
        mid_key = str(media_id) if media_id else ""
        mapped_owner = owner_maps.get(mid_key) if mid_key else None

        if item.get("type") == "profile_picture":
            owner_slug = target_slug
            is_target = True
        elif mapped_owner is not None:
            # Present in owner map (including "" = others-named / unknown non-target).
            owner_slug = mapped_owner
            is_target = bool(owner_slug) and owner_slug.lower() == target_key
        elif item.get("owner_username") and str(item.get("owner_username")).lower() != target_key:
            owner_slug = str(item["owner_username"])
            is_target = False
        elif item.get("is_target_profile") is False:
            owner_slug = str(item.get("owner_username") or "")
            is_target = False
        elif item.get("source") in {"facebook_graph_picture", "profile_picture"}:
            owner_slug = target_slug
            is_target = True
        else:
            # Unproven lookaside/page media — do not claim for the searched user.
            owner_slug = str(item.get("owner_username") or "")
            is_target = False

        item["owner_username"] = owner_slug or (target_slug if is_target else "")
        if item["owner_username"]:
            item["profile_url"] = _facebook_profile_url_from_slug(item["owner_username"])
        item["is_target_profile"] = is_target
        if item.get("url"):
            item["live_url"] = item["url"]
        enriched.append(item)

    similar_profiles = _build_facebook_similar_profiles(
        enriched,
        pages,
        target_slug,
        full_name=full_name,
        fast=fast,
        seed_username=seed_username,
    )
    return enriched, similar_profiles


def _extract_googlebot_media(page: str) -> tuple[list[dict], list[dict]]:
    """Extract downloadable photos and videos via lookaside media_id + scontent CDN URLs."""
    photos: list[dict] = []
    videos: list[dict] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()

    json_url_keys = (
        "browser_native_hd_url",
        "image_uri",
        "viewer_image",
        "photo_image",
        "thumbnailImage",
        "preferred_thumbnail",
        "uri",
    )
    for key in json_url_keys:
        pattern = rf'"{key}"\s*:\s*\{{?"uri"\s*:\s*"((?:[^"\\]|\\.)*)"|"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"'
        for match in re.finditer(pattern, page):
            raw = match.group(1) or match.group(2) or ""
            clean = _decode_fb_json_text(raw)
            if not clean.startswith("http") or clean in seen_urls or "static" in clean:
                continue
            seen_urls.add(clean)
            if "video" in key.lower() or clean.endswith(".mp4"):
                videos.append(
                    {
                        "url": clean,
                        "title": key,
                        "is_reel": "reel" in key.lower(),
                        "source": "googlebot_json",
                    }
                )
            else:
                photos.append({"url": clean, "type": "image", "source": f"googlebot_{key}"})

    for media_id in re.findall(r"lookaside/crawler/media/\?media_id=(\d+)", page):
        if media_id in seen_ids:
            continue
        seen_ids.add(media_id)
        url = _lookaside_media_url(media_id)
        thumb_url = _lookaside_media_url(media_id, thumbnail=True)
        photos.append(
            {
                "media_id": media_id,
                "url": url,
                "thumbnail": thumb_url,
                "type": "lookaside",
                "source": "googlebot_lookaside",
            }
        )
        videos.append(
            {
                "media_id": media_id,
                "url": url,
                "thumbnail": thumb_url,
                "title": f"Media {media_id}",
                "is_reel": False,
                "source": "googlebot_lookaside",
            }
        )

    for url in dict.fromkeys(re.findall(r"https:\\/\\/scontent[^\"\\]+|https://scontent[^\"\\&]+", page)):
        clean = _decode_fb_json_text(url)
        if "static" in clean or clean in seen_urls:
            continue
        seen_urls.add(clean)
        photos.append({"url": clean, "type": "image", "source": "googlebot_scontent"})

    for reel_id in dict.fromkeys(re.findall(r"/reel/(\d+)", page)):
        videos.append(
            {
                "media_id": reel_id,
                "url": f"https://www.facebook.com/reel/{reel_id}",
                "title": f"Reel {reel_id}",
                "is_reel": True,
                "source": "googlebot_reel_link",
            }
        )

    return photos, videos


def fetch_facebook_graph_picture(slug: str) -> str | None:
    """Graph API picture endpoint works without auth for many public profiles."""
    for candidate in (slug,):
        url = f"https://graph.facebook.com/{candidate}/picture?redirect=false&type=large"
        try:
            response = requests.get(url, timeout=20)
            if response.status_code != 200:
                continue
            data = response.json()
            pic = (data.get("data") or {}).get("url")
            if pic and pic.startswith("http"):
                return pic
        except (requests.RequestException, ValueError, json.JSONDecodeError):
            continue
    return None


def fetch_facebook_oembed(slug: str) -> dict | None:
    """Facebook oEmbed may expose title/thumbnail for pages."""
    url = f"https://www.facebook.com/oembed.php?url=https://www.facebook.com/{slug}"
    try:
        response = requests.get(url, headers=FB_HEADERS, timeout=20)
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, dict):
            return None
        result: dict = {"source": "facebook_oembed"}
        if data.get("author_name"):
            result["full_name"] = data["author_name"]
        if data.get("thumbnail_url"):
            result["profile_pic_url"] = data["thumbnail_url"]
            result["photos"] = [{"url": data["thumbnail_url"], "type": "oembed_thumbnail"}]
        if data.get("html"):
            result["oembed_html"] = data["html"][:2000]
        return result if len(result) > 1 else None
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        return None


def _parse_compact_count(label: str) -> int | None:
    """Parse labels like '121M followers', '1.2K friends', '500 friends'."""
    if not label:
        return None
    match = re.search(r"([\d,.]+)\s*([KMB])?", label.replace(",", ""), re.I)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    suffix = (match.group(2) or "").upper()
    multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
    return int(value * multiplier)


def _extract_profile_social_context(page: str) -> dict:
    """Extract friends/followers label and counts from Googlebot profile_social_context."""
    result: dict = {}
    if '"profile_social_context":null' in page:
        result["profile_social_context"] = None
        return result

    block = re.search(
        r'"profile_social_context"\s*:\s*(\{.*?\})\s*,\s*"is_eligible_for_comet_floating_action_bar"',
        page,
        re.S,
    )
    if not block:
        return result

    chunk = block.group(1)
    for match in re.finditer(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', chunk):
        text = _decode_fb_json_text(match.group(1)).strip()
        if not text:
            continue
        lowered = text.lower()
        if "friend" in lowered:
            result["friends_label"] = text
            count = _parse_compact_count(text)
            if count is not None:
                result["friend_count"] = count
        elif "follower" in lowered:
            result["followers_label"] = text
            count = _parse_compact_count(text)
            if count is not None:
                result["follower_count"] = count
    return result


def parse_googlebot_profile_page(page: str) -> dict:
    """Parse profile_fields, timeline posts, and photos from Googlebot HTML."""
    personal_details: dict[str, str] = {}
    timeline_posts: list[dict] = []
    photos: list[dict] = []

    locked = re.search(r'"text":"([^"]*locked his profile[^"]*)"|"text":"([^"]*locked her profile[^"]*)"|"text":"([^"]*locked their profile[^"]*)"', page, re.I)
    if locked:
        status = next(g for g in locked.groups() if g)
        personal_details["Profile Status"] = _decode_fb_json_text(status)

    section_headers = {
        "Work",
        "University",
        "High School",
        "College",
        "Education",
        "Basic info",
        "Categories",
        "Company",
        "Websites and social links",
        "Contact info",
        "Places lived",
        "Current city",
        "Hometown",
        "Relationship status",
        "Languages",
    }
    skip_labels = {
        "Photos",
        "Friends",
        "About",
        "Posts",
        "Reels",
        "Videos",
        "Events",
        "Groups",
        "More",
        "Menu",
        "Sports",
        "Music",
        "Films",
        "TV shows",
        "Books",
        "Reviews",
        "Check-ins",
        "Notes",
        "Community",
        "See all",
        "See more",
    }
    current_section = "General"
    for match in re.finditer(
        r'"title"\s*:\s*\{[^}]*"text"\s*:\s*"((?:[^"\\]|\\.)*)"',
        page,
    ):
        text = _decode_fb_json_text(match.group(1)).strip()
        if not text or "delight_ranges" in text or text in skip_labels:
            continue
        if text in section_headers:
            current_section = text
            continue
        if text.startswith("Others named"):
            personal_details["Similar Profiles"] = text
            continue
        if text.startswith("http") or ".com" in text or ".me/" in text:
            key = f"{current_section} Link" if current_section != "General" else "Link"
            personal_details[key] = text
        elif "no " in text.lower() and "to show" in text.lower():
            personal_details[current_section] = text
        elif len(text) > 2 and current_section != "General":
            personal_details[current_section] = text

    for match in re.finditer(
        r'"message"\s*:\s*\{"text"\s*:\s*"((?:[^"\\]|\\.)*)"',
        page,
    ):
        message = _decode_fb_json_text(match.group(1)).strip()
        if len(message) < 20:
            continue
        timeline_posts.append({"text": message[:2000], "type": "post", "source": "googlebot"})
        if len(timeline_posts) >= MAX_FB_POSTS:
            break

    gb_photos, gb_videos = _extract_googlebot_media(page)
    for photo in gb_photos:
        if photo["url"] not in {p.get("url") for p in photos}:
            photos.append(photo)

    json_fields = extract_profile_fields_from_json(page)
    for key, value in json_fields.get("personal_details", {}).items():
        if key not in personal_details:
            personal_details[key] = value

    social = _extract_profile_social_context(page)
    result = {
        "personal_details": personal_details,
        "timeline_posts": timeline_posts,
        "photos": photos,
        "videos": gb_videos,
        "reels": [video for video in gb_videos if video.get("is_reel")],
    }
    if social.get("friend_count") is not None:
        result["friend_count"] = social["friend_count"]
    if social.get("friends_label"):
        result["friends_label"] = social["friends_label"]
    if social.get("follower_count") is not None:
        result["follower_count"] = social["follower_count"]
    if social.get("followers_label"):
        result["followers_label"] = social["followers_label"]
    if social.get("profile_social_context") is None and '"profile_social_context":null' in page:
        result["friend_count_hidden"] = True
    if json_fields.get("friend_count_hint") and result.get("friend_count") is None:
        try:
            result["friend_count"] = int(json_fields["friend_count_hint"])
        except (TypeError, ValueError):
            pass
    return result


def fetch_facebook_googlebot_main(slug: str) -> dict | None:
    """Single-page Googlebot fetch — used by fast investigation mode."""
    url = f"https://www.facebook.com/{slug}"
    try:
        response = requests.get(url, headers=GOOGLEBOT_HEADERS, timeout=FAST_HTTP_TIMEOUT, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200 or _is_facebook_login_redirect(response):
        return None

    page = response.text
    parsed = parse_googlebot_profile_page(page)
    title_match = re.search(r"<title>([^<]+)</title>", page, re.I)
    full_name = _title_to_profile_name(title_match.group(1)) if title_match else ""
    if not any([full_name, parsed["personal_details"], parsed["timeline_posts"], parsed["photos"], parsed.get("videos")]):
        return None

    return {
        "username": slug,
        "full_name": full_name or slug,
        "biography": "",
        "profile_type": "personal",
        "profile_pic_url": parsed.get("profile_pic_url"),
        "profile_url": f"https://www.facebook.com/{slug}/",
        "personal_details": parsed["personal_details"],
        "timeline_posts": parsed["timeline_posts"],
        "photos": parsed["photos"],
        "videos": parsed.get("videos") or [],
        "reels": parsed.get("reels") or [],
        "raw_pages": [page],
        "data_sources": ["googlebot_main"],
    }


def fetch_facebook_googlebot_embed(slug: str) -> dict | None:
    """Fetch work/education/contact + timeline + photos/reels via Googlebot-visible JSON."""
    # About subpages first — main /photos /friends often trigger login redirects on locked profiles.
    paths = (
        "/about_work_and_education",
        "/about_contact_and_basic_info",
        "/about_places",
        "/photos_by",
        "/reels",
        "/about",
        "",
        "/photos",
        "/videos",
        "/friends",
    )
    personal_details: dict[str, str] = {}
    timeline_posts: list[dict] = []
    photos: list[dict] = []
    videos: list[dict] = []
    friend_count: int | None = None
    friends_label: str | None = None
    raw_pages: list[str] = []
    seen_photo_urls: set[str] = set()
    seen_video_keys: set[str] = set()
    seen_media_ids: set[str] = set()
    found = False
    full_name = ""

    session = requests.Session()
    session.headers.update(GOOGLEBOT_HEADERS)

    for path in paths:
        url = f"https://www.facebook.com/{slug}{path}"
        try:
            response = session.get(url, timeout=30, allow_redirects=True)
        except requests.RequestException:
            continue
        if response.status_code != 200 or _is_facebook_login_redirect(response):
            continue

        page = response.text
        raw_pages.append(page)

        title_match = re.search(r"<title>([^<]+)</title>", page, re.I)
        if title_match and not full_name:
            title_name = _title_to_profile_name(title_match.group(1))
            if title_name:
                full_name = title_name

        for media_id in _extract_raw_media_ids_from_page(page):
            if media_id in seen_media_ids:
                continue
            seen_media_ids.add(media_id)
            photo = {
                "media_id": media_id,
                "url": _lookaside_media_url(media_id),
                "thumbnail": _lookaside_media_url(media_id, thumbnail=True),
                "type": "image",
                "source": "googlebot_raw",
            }
            if photo["url"] not in seen_photo_urls:
                photos.append(photo)
                seen_photo_urls.add(photo["url"])

        parsed = parse_googlebot_profile_page(page)
        if not any(
            [
                parsed["personal_details"],
                parsed["timeline_posts"],
                parsed["photos"],
                parsed.get("videos"),
                seen_media_ids,
            ]
        ):
            time.sleep(1.0)
            continue
        found = True
        personal_details.update(parsed["personal_details"])
        if parsed.get("friend_count") is not None:
            friend_count = parsed["friend_count"]
        if parsed.get("friends_label"):
            friends_label = parsed["friends_label"]
        for post in parsed["timeline_posts"]:
            if post["text"] not in {p.get("text") for p in timeline_posts}:
                timeline_posts.append(post)
        for photo in parsed["photos"]:
            photo_url = photo.get("url")
            if photo_url and photo_url not in seen_photo_urls:
                photos.append(photo)
                seen_photo_urls.add(photo_url)
        for video in parsed.get("videos", []):
            key = video.get("media_id") or video.get("url")
            if key and key not in seen_video_keys:
                videos.append(video)
                seen_video_keys.add(key)
        time.sleep(1.0)

    for page in raw_pages:
        personal_details = _merge_personal_details(
            personal_details, parse_googlebot_profile_page(page).get("personal_details")
        )
        for media_id in _extract_raw_media_ids_from_page(page):
            if media_id in seen_media_ids:
                continue
            seen_media_ids.add(media_id)
            photo_url = _lookaside_media_url(media_id)
            if photo_url in seen_photo_urls:
                continue
            photos.append(
                {
                    "media_id": media_id,
                    "url": photo_url,
                    "thumbnail": _lookaside_media_url(media_id, thumbnail=True),
                    "type": "image",
                    "source": "googlebot_raw_pass",
                }
            )
            seen_photo_urls.add(photo_url)
            found = True

    if not found and not raw_pages:
        return None
    if not found and raw_pages:
        found = True

    locked_hint = any(
        "locked" in str(value).lower()
        for value in (personal_details or {}).values()
    )
    probe_meta: list[dict] = []
    if locked_hint:
        probe_photos, probe_videos, probe_meta = discover_locked_facebook_media(
            slug, full_name or slug, raw_pages, session=session
        )
        if probe_photos or probe_videos:
            personal_details.setdefault(
                "CID Media Recovery",
                f"lookaside_probe recovered {len(probe_photos)} images, {len(probe_videos)} videos",
            )
            seen_photo_urls = {photo.get("url") for photo in photos if photo.get("url")}
            for photo in probe_photos:
                if photo.get("url") not in seen_photo_urls:
                    photos.append(photo)
                    seen_photo_urls.add(photo["url"])
            for video in probe_videos:
                key = video.get("media_id") or video.get("url")
                if key and key not in seen_video_keys:
                    videos.append(video)
                    seen_video_keys.add(key)

    photos, videos = _verify_facebook_lookaside_collections(photos, videos, session)

    photos, similar_profiles = enrich_facebook_photo_ownership(
        photos, raw_pages, slug, full_name=full_name
    )

    result = {
        "username": slug,
        "full_name": full_name or slug,
        "personal_details": personal_details,
        "timeline_posts": timeline_posts[:MAX_FB_POSTS],
        "photos": photos[:MAX_FB_PHOTOS],
        "videos": videos[:MAX_FB_VIDEOS],
        "reels": [video for video in videos if video.get("is_reel")][:MAX_FB_VIDEOS],
        "similar_profiles": similar_profiles,
        "raw_pages": raw_pages,
        "lookaside_probe": probe_meta,
        "source": "facebook_googlebot_embed",
    }
    if probe_meta:
        result["data_sources"] = ["facebook_googlebot_embed", "facebook_lookaside_probe"]
    if friend_count is not None:
        result["friend_count"] = friend_count
    if friends_label:
        result["friends_label"] = friends_label
    return result


def merge_facebook_public_profiles(*profiles: dict | None) -> dict:
    merged: dict = {
        "friends": [],
        "photos": [],
        "videos": [],
        "reels": [],
        "timeline_posts": [],
        "personal_details": {},
        "similar_profiles": [],
        "data_sources": [],
        "raw_pages": [],
    }
    valid = [profile for profile in profiles if profile]
    if not valid:
        return merged

    for profile in valid:
        source = profile.get("source")
        if source:
            merged["data_sources"].append(source)

        for field in ("username", "full_name", "profile_url", "id", "profile_type"):
            if not merged.get(field) and profile.get(field):
                merged[field] = profile[field]

        if profile.get("full_name") and merged.get("full_name") in (None, merged.get("username")):
            merged["full_name"] = profile["full_name"]

        for field in ("like_count", "talking_about_count", "follower_count", "friend_count"):
            if merged.get(field) is None and profile.get(field) is not None:
                merged[field] = profile[field]

        if profile.get("friends_label") and not merged.get("friends_label"):
            merged["friends_label"] = profile["friends_label"]

        if profile.get("follower_count") and merged.get("like_count") is None:
            merged["like_count"] = profile["follower_count"]

        bio = profile.get("biography") or ""
        if bio and not _generic_facebook_bio(bio):
            merged["biography"] = bio

        pic = profile.get("profile_pic_url")
        if _is_direct_image_url(pic):
            merged["profile_pic_url"] = pic
        elif not merged.get("profile_pic_url") and pic:
            merged["profile_pic_url"] = pic

        merged["personal_details"] = _merge_personal_details(
            merged.get("personal_details"), profile.get("personal_details")
        )
        merged["timeline_posts"] = _merge_unique_items(
            merged.get("timeline_posts", []), profile.get("timeline_posts", []), "text"
        )
        merged["photos"] = _merge_unique_items(
            merged.get("photos", []), profile.get("photos", []), "url"
        )
        merged["videos"] = _merge_unique_items(
            merged.get("videos", []), profile.get("videos", []), "url"
        )
        merged["reels"] = _merge_unique_items(
            merged.get("reels", []), profile.get("reels", []), "url"
        )
        for similar in profile.get("similar_profiles", []):
            username = similar.get("username")
            if not username:
                continue
            existing = {s.get("username") for s in merged["similar_profiles"]}
            if username not in existing:
                merged["similar_profiles"].append(similar)

        for page in profile.get("raw_pages") or []:
            if page and page not in merged["raw_pages"]:
                merged["raw_pages"].append(page)

    merged["data_sources"] = list(dict.fromkeys(merged["data_sources"]))
    merged["source"] = "facebook_embed"
    return merged


def load_facebook_cookies() -> dict[str, str] | None:
    """Load Facebook cookies from env vars or a JSON / Netscape cookies file."""
    cookie_file = os.environ.get("FB_COOKIES_FILE", "").strip()
    if cookie_file and os.path.isfile(cookie_file):
        try:
            with open(cookie_file, encoding="utf-8") as handle:
                raw = handle.read().strip()
            if raw.startswith("{"):
                data = json.loads(raw)
                if isinstance(data, dict) and data.get("c_user") and data.get("xs"):
                    return {str(k): str(v) for k, v in data.items()}
            cookies = _parse_netscape_cookies(raw)
            if cookies.get("c_user") and cookies.get("xs"):
                return cookies
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    raw = os.environ.get("FB_COOKIES", "").strip()
    if raw:
        cookies: dict[str, str] = {}
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                name, value = part.split("=", 1)
                cookies[name.strip()] = value.strip()
        if cookies.get("c_user") and cookies.get("xs"):
            return cookies

    c_user = os.environ.get("FB_C_USER", "").strip()
    xs = os.environ.get("FB_XS", "").strip()
    if c_user and xs:
        return {"c_user": c_user, "xs": xs}
    return None


def _parse_netscape_cookies(text: str) -> dict[str, str]:
    """Parse Netscape/Mozilla cookies.txt (e.g. from 'Get cookies.txt LOCALLY')."""
    cookies: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name, value = parts[5], parts[6]
            cookies[name] = value
    return cookies


def _instagram_cookie_file_paths() -> list[str]:
    paths: list[str] = []
    env_path = os.environ.get("IG_COOKIES_FILE", "").strip()
    if env_path:
        paths.append(env_path)
    samurai_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ("cookies.txt", "instagram_cookies.txt", ".cookies.txt"):
        paths.append(os.path.join(samurai_dir, name))
    return paths


def load_instagram_cookies() -> dict[str, str] | None:
    """Load Instagram session cookies from env vars or a cookies file."""
    cookies: dict[str, str] = {}

    sessionid = os.environ.get("IG_SESSIONID", "").strip()
    if sessionid:
        cookies["sessionid"] = sessionid

    for extra in ("ds_user_id", "csrftoken", "mid", "ig_did"):
        val = os.environ.get(f"IG_{extra.upper()}", "").strip()
        if val:
            cookies[extra] = val

    raw_inline = os.environ.get("IG_COOKIES", "").strip()
    if raw_inline:
        for part in raw_inline.split(";"):
            part = part.strip()
            if "=" in part:
                name, value = part.split("=", 1)
                cookies[name.strip()] = value.strip()

    for path in _instagram_cookie_file_paths():
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                raw = handle.read().strip()
        except OSError:
            continue
        if not raw:
            continue
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, str) and value:
                            cookies[str(key)] = value
            except (ValueError, json.JSONDecodeError):
                pass
        else:
            cookies.update(_parse_netscape_cookies(raw))
        if cookies.get("sessionid"):
            break

    return cookies if cookies.get("sessionid") else None


def instagram_sessionid() -> str | None:
    cookies = load_instagram_cookies()
    return cookies.get("sessionid") if cookies else None


def make_facebook_session() -> requests.Session | None:
    cookies = load_facebook_cookies()
    if not cookies:
        return None
    session = requests.Session()
    session.headers.update(MBASIC_HEADERS)
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".facebook.com")
    for warmup in (
        "https://www.facebook.com/",
        "https://m.facebook.com/",
        "https://mbasic.facebook.com/",
    ):
        try:
            session.get(warmup, timeout=30)
        except requests.RequestException:
            pass
    return session


def fetch_facebook_surface_page(
    session: requests.Session, slug: str, path: str = "", surface: str = "mbasic"
) -> str | None:
    """Fetch profile sub-pages via mbasic, mobile, or desktop surfaces."""
    if not path.startswith("/") and path:
        path = f"/{path}"
    hosts = {
        "mbasic": "mbasic.facebook.com",
        "mobile": "m.facebook.com",
        "www": "www.facebook.com",
    }
    host = hosts.get(surface, "mbasic.facebook.com")
    headers = MBASIC_HEADERS if surface == "mbasic" else MOBILE_FB_HEADERS
    if surface == "www":
        headers = {**BROWSER_HEADERS, "referer": "https://www.facebook.com/"}
    url = f"https://{host}/{slug}{path}"
    try:
        response = session.get(url, headers=headers, timeout=30, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    if "login.php" in response.url and "next=" in response.url:
        return None
    return response.text


def fetch_mbasic_page(session: requests.Session, slug: str, path: str = "") -> str | None:
    return fetch_facebook_surface_page(session, slug, path, surface="mbasic")


def _mbasic_next_path(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        text = link.get_text(" ", strip=True).lower()
        if any(token in text for token in ("see more", "more photos", "more friends", "more videos")):
            return link["href"]
    return None


def parse_mbasic_about_details(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    personal_details: dict[str, str] = {}
    biography = ""

    for block in soup.select("div"):
        text = block.get_text(" ", strip=True)
        if text and 20 < len(text) < 500 and "likes" not in text.lower():
            if not biography and not block.find_parent("table"):
                biography = text

    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True)
        value = cells[1].get_text(" ", strip=True)
        if label and value and label.lower() not in ("", "photos", "friends"):
            personal_details[label] = value

    profile_pic_url = None
    for image in soup.find_all("img", src=True):
        src = image["src"]
        if "emoji" in src or "rsrc.php" in src:
            continue
        if "scontent" in src or "fbcdn" in src or "lookaside" in src:
            profile_pic_url = src
            break

    return {
        "personal_details": personal_details,
        "biography": biography,
        "profile_pic_url": profile_pic_url,
    }


def parse_mbasic_friends(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    friends: list[dict] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        name = link.get_text(" ", strip=True)
        if not name or len(name) < 2 or len(name) > 80:
            continue
        lowered = name.lower()
        if lowered in seen or lowered in {"friends", "see more", "find friends", "message"}:
            continue
        if not (
            "fref=" in href
            or "profile.php?id=" in href
            or re.fullmatch(r"/[A-Za-z0-9.\-_]+/?", href)
        ):
            continue
        slug_match = re.search(r"facebook\.com/([A-Za-z0-9.\-_]+)", href)
        profile_slug = slug_match.group(1) if slug_match else None
        if not profile_slug and "profile.php?id=" in href:
            profile_slug = href.split("profile.php?id=")[-1].split("&")[0]
        friends.append(
            {
                "name": name,
                "username": profile_slug,
                "profile_url": urljoin("https://www.facebook.com", href),
            }
        )
        seen.add(lowered)
    return friends


def parse_mbasic_photos(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    photos: list[dict] = []
    seen_urls: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "photo" not in href.lower():
            continue
        image = link.find("img", src=True)
        if not image:
            continue
        src = image["src"]
        if src in seen_urls or "emoji" in src:
            continue
        seen_urls.add(src)
        photos.append(
            {
                "url": src,
                "page_url": urljoin("https://mbasic.facebook.com", href),
            }
        )
    return photos


def parse_mbasic_videos(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    videos: list[dict] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        lowered = href.lower()
        if not any(token in lowered for token in ("video", "reel", "watch")):
            continue
        title = link.get_text(" ", strip=True) or "Video"
        key = href.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        videos.append(
            {
                "title": title,
                "url": urljoin("https://www.facebook.com", href),
                "is_reel": "reel" in lowered,
            }
        )
    return videos


def parse_mobile_about_sections(html: str) -> dict:
    """Parse m.facebook.com / www about pages into labeled sections."""
    soup = BeautifulSoup(html, "html.parser")
    personal_details: dict[str, str] = {}
    biography = ""

    section_labels = (
        "Overview",
        "Work",
        "Education",
        "Places lived",
        "Contact",
        "Basic info",
        "Family",
        "Life events",
        "Details about",
    )
    for header in soup.find_all(["h1", "h2", "h3", "h4", "strong", "span"]):
        label = header.get_text(" ", strip=True)
        if not label or len(label) > 80:
            continue
        if not any(label.lower().startswith(s.lower()) for s in section_labels):
            continue
        sibling_text = []
        for sib in header.find_all_next(["div", "span", "a"], limit=8):
            text = sib.get_text(" ", strip=True)
            if text and text != label and len(text) < 300:
                sibling_text.append(text)
            if len(sibling_text) >= 3:
                break
        if sibling_text:
            personal_details[label] = " | ".join(dict.fromkeys(sibling_text))

    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            label = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            if label and value:
                personal_details[label] = value

    intro = soup.find("div", attrs={"data-gt": True}) or soup.find("div", id=re.compile("intro", re.I))
    if intro:
        biography = intro.get_text(" ", strip=True)[:1000]

    profile_pic_url = None
    for image in soup.find_all("img", src=True):
        src = image["src"]
        if _is_direct_image_url(src):
            profile_pic_url = src
            break

    return {
        "personal_details": personal_details,
        "biography": biography,
        "profile_pic_url": profile_pic_url,
    }


def parse_mobile_timeline_posts(html: str) -> list[dict]:
    """Extract visible timeline posts from mobile/desktop HTML."""
    soup = BeautifulSoup(html, "html.parser")
    posts: list[dict] = []
    seen: set[str] = set()

    for article in soup.find_all(["article", "div"], limit=200):
        text = article.get_text(" ", strip=True)
        if not text or len(text) < 20:
            continue
        link = article.find("a", href=True)
        post_url = None
        if link and any(token in link["href"] for token in ("story", "posts", "photo", "permalink")):
            post_url = urljoin("https://www.facebook.com", link["href"])
        key = text[:120]
        if key in seen:
            continue
        seen.add(key)
        image = None
        for img in article.find_all("img", src=True):
            if _is_direct_image_url(img["src"]):
                image = img["src"]
                break
        posts.append(
            {
                "text": text[:2000],
                "url": post_url,
                "image_url": image,
                "type": "post",
            }
        )
        if len(posts) >= MAX_FB_POSTS:
            break
    return posts


def _extract_json_blobs(html: str) -> list:
    blobs = []
    for match in re.finditer(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.S):
        try:
            blobs.append(json.loads(match.group(1)))
        except (json.JSONDecodeError, ValueError):
            continue
    return blobs


def _walk_json_collect(obj, found: dict, depth: int = 0) -> None:
    if depth > 12:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = str(key).lower()
            if key_lower in {
                "work",
                "education",
                "hometown",
                "current_city",
                "relationship_status",
                "website",
                "email",
                "phone",
                "birthday",
                "gender",
                "religion",
                "political",
                "locale",
                "bio",
                "about",
            } and isinstance(value, (str, int, float)) and value:
                found[key] = str(value)
            if key_lower in {"profile_pic_url", "profile_picture", "profile_pic_uri"} and isinstance(value, str):
                if value.startswith("http"):
                    found["profile_pic_url_json"] = value
            if key_lower in {"friends", "friend_count", "subscriber_count"} and isinstance(value, (int, str)):
                found[f"json_{key_lower}"] = value
            _walk_json_collect(value, found, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:80]:
            _walk_json_collect(item, found, depth + 1)


def extract_profile_fields_from_json(html: str) -> dict:
    found: dict[str, str] = {}
    for blob in _extract_json_blobs(html):
        _walk_json_collect(blob, found)
    personal_details = {}
    for key, value in found.items():
        if key.startswith("json_"):
            continue
        if key == "profile_pic_url_json":
            continue
        personal_details[key.replace("_", " ").title()] = value
    return {
        "personal_details": personal_details,
        "profile_pic_url": found.get("profile_pic_url_json"),
        "friend_count_hint": found.get("json_friend_count") or found.get("json_friends"),
    }


def fetch_wayback_intel(profile_url: str) -> dict:
    """OSINT: check Internet Archive for historical public snapshots."""
    try:
        response = requests.get(
            "https://archive.org/wayback/available",
            params={"url": profile_url},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return {"available": False, "snapshots": []}

    snapshots = payload.get("archived_snapshots", {})
    closest = snapshots.get("closest")
    if not closest or not closest.get("available"):
        return {"available": False, "snapshots": []}

    return {
        "available": True,
        "snapshots": [
            {
                "timestamp": closest.get("timestamp"),
                "url": closest.get("url"),
                "status": closest.get("status"),
            }
        ],
        "note": "Historical public snapshots may contain old posts or about info no longer visible.",
    }


COMMON_USERNAME_SUFFIXES = ("27", "07", "1", "11", "99", "123", "007", "2", "21", "23")
COMMON_NAME_TAILS = (
    "yadav", "kumar", "singh", "sharma", "dev", "raj", "reddy", "patel", "gupta", "verma",
)


def _normalize_seed_for_facebook(seed: str) -> str:
    """Normalize IG-style handles before Facebook slug conversion."""
    s = seed.strip().lstrip("@").lower()
    s = re.sub(r"_+\.", ".", s)
    s = re.sub(r"\._+", ".", s)
    s = re.sub(r"_+", "", s)
    s = re.sub(r"\.{2,}", ".", s)
    return s.strip("._")


def _is_valid_facebook_slug_candidate(slug: str) -> bool:
    clean = slug.strip().lstrip("@")
    if len(clean) < 3:
        return False
    if ".." in clean or clean.startswith(".") or clean.endswith("."):
        return False
    if not re.fullmatch(r"[A-Za-z0-9.\-_]+", clean):
        return False
    if "." in clean:
        parts = [p for p in clean.split(".") if p]
        if not parts or any(len(p) < 1 for p in parts):
            return False
        if any(len(p) < 2 for p in parts if not p.isdigit()):
            return False
    return True


def _facebook_priority_slugs(seed: str) -> list[str]:
    """High-confidence Facebook slugs (first.last27) from compact handles."""
    base = _normalize_seed_for_facebook(seed)
    if not base:
        return []

    slugs: list[str] = []
    seen: set[str] = set()

    def add(slug: str) -> None:
        if not _is_valid_facebook_slug_candidate(slug):
            return
        key = slug.lower()
        if key in seen:
            return
        seen.add(key)
        slugs.append(slug)

    digits_match = re.match(r"^(.+?)(\d+)$", base)
    name_part = digits_match.group(1) if digits_match else base
    digit_suffix = digits_match.group(2) if digits_match else ""

    for tail in COMMON_NAME_TAILS:
        idx = name_part.find(tail)
        if idx < 3:
            continue
        left = name_part[:idx]
        rest = f"{tail}{digit_suffix}"
        add(f"{left}.{rest}")
        add(f"{left}{rest}")
        add(f"{left.capitalize()}{rest.capitalize()}")
        add(f"{left}_{rest}")

    add(base)
    return slugs


def generate_username_variations(seed: str, *, limit: int = 8) -> list[str]:
    """Build plausible handle variants from a searched username (e.g. manojyadavnr)."""
    raw = seed.strip().lstrip("@")
    base = re.sub(r"[^a-z0-9._]", "", raw.lower())
    if len(base) < 3:
        return []

    variations: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        c = candidate.strip().lstrip("@")
        if not c or len(c) < 3:
            return
        if not re.fullmatch(r"[a-z0-9._]+", c, re.I):
            return
        if "." in c:
            parts = c.split(".")
            if any(len(p) < 2 for p in parts):
                return
        if "_" in c:
            parts = c.split("_")
            if any(len(p) < 2 for p in parts):
                return
        key = c.lower()
        if key in seen:
            return
        seen.add(key)
        variations.append(c)

    add(base)

    without_digits = re.sub(r"\d+$", "", base)
    if without_digits != base:
        add(without_digits)

    core = without_digits or base
    trimmed = core
    if len(core) > 6:
        trimmed = re.sub(r"[a-z]{1,2}$", "", core)
        if trimmed and len(trimmed) >= 4 and trimmed != core:
            styled = trimmed
            for tail in COMMON_NAME_TAILS:
                if trimmed.endswith(tail) and len(trimmed) > len(tail) + 1:
                    styled = f"{trimmed[:-len(tail)]}{tail.capitalize()}"
                    break
            add(styled)

    stem = trimmed if trimmed != core and len(trimmed) >= 4 else core

    for tail in COMMON_NAME_TAILS:
        idx = base.find(tail)
        if idx < 3:
            continue
        left = base[:idx]
        add(f"{left}{tail.capitalize()}")
        add(f"{left}.{tail}")
        add(f"{left}_{tail}")

    for suffix in COMMON_USERNAME_SUFFIXES[:6]:
        add(f"{stem}{suffix}")

    for tail in COMMON_NAME_TAILS:
        idx = base.find(tail)
        if idx < 3:
            continue
        left, right = base[:idx], base[idx:]
        add(f"{left}{right.capitalize()}")
        add(f"{left}.{right}")
        add(f"{left}_{right}")
        right_core = re.sub(r"[a-z]{1,2}$", "", right) or right
        if right_core != right:
            add(f"{left}{right_core.capitalize()}")
            add(f"{left}{right_core}")

    for i in range(4, len(base) - 2):
        left, right = base[:i], base[i:]
        if len(left) < 4 or len(right) < 3:
            continue
        add(f"{left}{right.capitalize()}")
        add(f"{left}.{right}")
        add(f"{left}_{right}")

    return variations[:limit]


def build_similar_username_profiles(
    seed_username: str,
    *,
    platform: str = "facebook",
    fast: bool = False,
    limit: int = 8,
    exclude: str | None = None,
    verify_exists: bool = True,
    enrich: bool = True,
) -> list[dict]:
    """Similar accounts derived from the searched handle — not unrelated directory hits."""
    exclude_key = (exclude or "").strip().lower()
    if platform == "facebook":
        candidates = generate_facebook_slug_variations(seed_username, limit=limit + 6)[: limit + 6]
    else:
        candidates = generate_username_variations(seed_username, limit=limit + 4)[: limit + 4]
    profiles: list[dict] = []

    def _instagram_posts_preview(posts: list[dict]) -> list[dict]:
        previews: list[dict] = []
        for post in posts[:2]:
            previews.append(
                {
                    "shortcode": post.get("shortcode"),
                    "url": post.get("url"),
                    "live_url": post.get("url"),
                    "display_url": post.get("display_url"),
                    "thumbnail": post.get("display_url"),
                    "type": post.get("type"),
                    "text": (post.get("caption") or "")[:240],
                    "is_video": post.get("is_video"),
                }
            )
        return previews

    def _append_instagram(username: str, brief: dict | None) -> None:
        if brief is None:
            return
        handle = brief.get("username") or username
        posts = _instagram_posts_preview(brief.get("posts") or [])
        profiles.append(
            {
                "username": handle,
                "full_name": brief.get("full_name") or handle,
                "profile_url": _instagram_profile_url(handle),
                "profile_pic_url": brief.get("profile_pic_url"),
                "posts": posts,
                "photos": posts,
                "photo_count": len(posts),
                "exists": True,
                "is_private": brief.get("is_private", False),
                "source": "username_variation",
            }
        )

    def _append_facebook(username: str, brief: dict | None) -> None:
        entry: dict = {
            "username": username,
            "profile_url": _facebook_profile_url_from_slug(username),
            "source": "username_variation",
            "exists": brief is not None,
        }
        if brief:
            entry["full_name"] = brief.get("full_name") or username
            entry["profile_pic_url"] = brief.get("profile_pic_url")
            entry["id"] = brief.get("id")
        if enrich:
            post_previews = _fetch_facebook_profile_post_previews(username, limit=2)
            entry["posts"] = post_previews
            entry["photos"] = post_previews
            entry["photo_count"] = len(post_previews)
        profiles.append(entry)

    if platform == "instagram" and enrich:
        workers = min(SAMURAI_SAFE_WORKERS, max(1, len(candidates)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_probe_instagram_profile_brief, name): name
                for name in candidates
                if name.lower() != exclude_key
            }
            for fut in as_completed(futures):
                if len(profiles) >= limit:
                    break
                name = futures[fut]
                try:
                    brief = fut.result()
                except Exception:
                    brief = None
                if verify_exists and not brief:
                    continue
                _append_instagram(name, brief)
        return profiles[:limit]

    if platform == "facebook" and enrich:
        workers = min(SAMURAI_SAFE_WORKERS, max(1, len(candidates)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_probe_facebook_profile_brief, name, fast=fast): name
                for name in candidates
                if name.lower() != exclude_key
            }
            for fut in as_completed(futures):
                if len(profiles) >= limit:
                    break
                name = futures[fut]
                try:
                    brief = fut.result()
                except Exception:
                    brief = None
                if verify_exists and not brief:
                    continue
                _append_facebook(name, brief)
        return profiles[:limit]

    for username in candidates:
        if len(profiles) >= limit:
            break
        if username.lower() == exclude_key:
            continue
        if platform == "instagram":
            brief = _probe_instagram_profile_brief(username) if enrich else None
            if verify_exists and not brief:
                continue
            _append_instagram(username, brief or {"username": username, "posts": []})
            continue

        brief = _probe_facebook_profile_brief(username, fast=fast) if enrich else None
        if verify_exists and not brief:
            continue
        _append_facebook(username, brief or {"username": username})

    return profiles[:limit]


def _guess_full_names_from_username(username: str) -> list[str]:
    """Guess display names from compact handles like bharathc -> Bharath C."""
    raw = username.strip().lstrip("@").replace("_", " ").replace(".", " ")
    if " " in raw:
        return [" ".join(part.capitalize() for part in raw.split() if part)]

    u = re.sub(r"[^a-z0-9]", "", raw.lower())
    if len(u) < 4:
        return []

    guesses: list[str] = []
    if len(u) >= 5:
        guesses.append(f"{u[:-1].capitalize()} {u[-1].upper()}")
    for i in range(3, len(u) - 2):
        left, right = u[:i], u[i:]
        if len(right) >= 2:
            guesses.append(f"{left.capitalize()} {right.capitalize()}")
    return list(dict.fromkeys(guesses))


def _facebook_slug_candidates_from_instagram(ig_username: str, ig_profile: dict | None = None) -> list[str]:
    """Build likely Facebook slugs from an Instagram handle and optional profile."""
    base = ig_username.strip().lstrip("@").lower()
    candidates = [
        base,
        base.replace("_", "."),
        base.replace("_", ""),
        base.replace(".", "_"),
    ]
    if "." not in base and len(base) > 4:
        for i in range(2, len(base) - 1):
            candidates.append(f"{base[:i]}.{base[i:]}")
    if len(base) >= 6 and base[-1].isalpha():
        candidates.append(f"{base[:-1]}.{base[-1]}")

    profile = ig_profile or {}
    full_name = (profile.get("full_name") or "").strip()
    for guess in _guess_full_names_from_username(base):
        if guess not in {full_name}:
            full_name = full_name or guess
    if full_name:
        parts = [part for part in re.split(r"\s+", full_name) if part]
        if len(parts) >= 2:
            first, last = parts[0].lower(), parts[-1].lower()
            candidates.extend(
                [
                    f"{first}.{last}",
                    f"{first}{last}",
                    f"{first}_{last}",
                    f"{first[0]}{last}",
                    f"{first}.{last[0]}",
                    f"{first}{last[0]}",
                ]
            )
        elif len(parts) == 1:
            candidates.append(parts[0].lower())

    return list(dict.fromkeys(c for c in candidates if len(c) >= 3))


def generate_facebook_slug_variations(
    seed: str,
    ig_profile: dict | None = None,
    *,
    limit: int = 12,
) -> list[str]:
    """Facebook profile slugs from an Instagram-style username (camelCase, first.last)."""
    base = _normalize_seed_for_facebook(seed)
    candidates: list[str] = []
    seen: set[str] = set()

    def add(slug: str) -> None:
        clean = slug.strip().lstrip("@")
        clean = re.sub(r"\.{2,}", ".", clean)
        if not _is_valid_facebook_slug_candidate(clean):
            return
        key = clean.lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(clean)

    for priority in _facebook_priority_slugs(seed):
        add(priority)

    add(base)
    if "_" in seed:
        add(seed.strip().lstrip("@").lower().replace("_", "."))

    for variant in generate_username_variations(base, limit=limit + 4):
        add(variant)

    for tail in COMMON_NAME_TAILS:
        idx = base.find(tail)
        if idx < 3:
            continue
        left = base[:idx]
        add(f"{left}.{tail}")
        add(f"{left.capitalize()}.{tail.capitalize()}")
        add(f"{left}{tail.capitalize()}")
        add(f"{left}_{tail}")

    profile = ig_profile or {}
    full_name = (profile.get("full_name") or "").strip()
    for guess in _guess_full_names_from_username(base):
        if guess and not full_name:
            full_name = guess
    if full_name:
        parts = [part for part in re.split(r"\s+", full_name) if part]
        if len(parts) >= 2:
            first, last = parts[0].lower(), parts[-1].lower()
            add(f"{first}.{last}")
            add(f"{first}{last}")
            add(f"{first}_{last}")
            add(f"{parts[0]}{parts[-1].capitalize()}")

    return candidates[:limit]


def find_facebook_profile_by_username(
    seed: str,
    ig_profile: dict | None = None,
    *,
    seed_username: str | None = None,
) -> tuple[str | None, dict | None]:
    """Resolve a Facebook profile directly from username using FB slug conventions."""
    priority = _facebook_priority_slugs(seed)
    extra = generate_facebook_slug_variations(seed, ig_profile, limit=15)
    candidates: list[str] = []
    seen: set[str] = set()
    for slug in [*priority, *extra]:
        key = slug.lower()
        if key in seen or not _is_valid_facebook_slug_candidate(slug):
            continue
        seen.add(key)
        candidates.append(slug)
    if not candidates:
        return None, None

    def _profile_looks_real(profile: dict, slug: str) -> bool:
        name = (profile.get("full_name") or "").strip()
        if not name:
            return False
        low = name.lower()
        return low not in {"", "facebook", "log in to facebook", slug.lower()}

    for slug in candidates[:8]:
        try:
            profile = fetch_facebook_profile(
                slug,
                fast=False,
                seed_username=seed_username or seed,
            )
            if _profile_looks_real(profile, slug):
                return slug, profile
        except Exception:
            continue

    for slug in candidates[:6]:
        brief = _probe_facebook_profile_brief(slug, fast=True)
        if not brief:
            continue
        try:
            profile = fetch_facebook_profile(
                slug,
                fast=True,
                seed_username=seed_username or seed,
            )
            if _profile_looks_real(profile, slug):
                return slug, profile
        except Exception:
            return slug, build_minimal_facebook_profile(
                slug,
                seed_username=seed_username or seed,
                full_name=brief.get("full_name"),
                profile_pic_url=brief.get("profile_pic_url"),
                profile_id=brief.get("id"),
            )
    return None, None


def _facebook_directory_candidates(full_name: str, username: str, target_slug: str, limit: int = 12) -> list[str]:
    names = [full_name] if full_name else []
    names.extend(_guess_full_names_from_username(username))
    slugs: list[str] = []
    seen: set[str] = set()
    for name in dict.fromkeys(names):
        for entry in fetch_facebook_directory_profiles(name, target_slug):
            slug = entry.get("username")
            if not slug or slug.lower() in seen:
                continue
            seen.add(slug.lower())
            slugs.append(slug)
            if len(slugs) >= limit:
                return slugs
    return slugs


def _probe_facebook_slug_for_instagram(slug: str, ig_profile: dict, *, fast: bool = False) -> dict | None:
    """Check if a Facebook slug likely belongs to the Instagram profile."""
    timeout = FAST_HTTP_TIMEOUT if fast else 25
    try:
        response = requests.get(
            f"https://www.facebook.com/{slug}",
            headers=GOOGLEBOT_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None

    page = response.text
    title_match = re.search(r"<title>([^<]+)</title>", page, re.I)
    title = html.unescape(title_match.group(1)) if title_match else ""
    title = title.replace("&#064;", "@")
    if not title or "log in to facebook" in title.lower():
        return None

    fb_title_name = title.split("•")[0].split("|")[0].strip()
    fb_name = fb_title_name.lower()
    if fb_name in {"facebook", "meta", "error"} or len(fb_title_name) < 2:
        return None

    brief = _probe_facebook_profile_brief(slug, fast=fast)
    if not brief:
        return None
    embed_name = (brief.get("full_name") or "").strip()
    if not embed_name or embed_name.lower() in {"facebook", slug.lower()}:
        return None

    canonical = response.url.rstrip("/").split("facebook.com/")[-1].split("?")[0]
    if canonical.lower() in {"login", "home", "watch", "marketplace", "groups", "gaming"}:
        return None
    if not re.fullmatch(r"[A-Za-z0-9.\-_]+", canonical):
        return None
    handle_in_title = re.search(r"@([A-Za-z0-9.\-_]+)", title)
    ig_name = (ig_profile.get("full_name") or "").strip().lower()
    fb_name = embed_name.lower()
    title_tokens = [t for t in re.split(r"\s+", fb_name) if len(t) > 2]

    score = 0
    reasons: list[str] = []
    if canonical.lower() == slug.lower():
        score += 1
        reasons.append("slug_resolves")
    if handle_in_title and ig_profile.get("username", "").replace(".", "").replace("_", "") == handle_in_title.group(1).replace(".", "").replace("_", ""):
        score += 3
        reasons.append("instagram_handle_in_facebook_title")
    if ig_name and title_tokens and title_tokens[0] in ig_name:
        score += 2
        reasons.append("first_name_match")
    if ig_name and all(part in fb_name for part in ig_name.split()[:2] if len(part) > 2):
        score += 2
        reasons.append("full_name_match")
    if slug.replace(".", "").replace("_", "") == ig_profile.get("username", "").replace(".", "").replace("_", ""):
        score += 2
        reasons.append("username_normalized_match")

    if score < 2:
        return None

    numeric_id = brief.get("id") or extract_facebook_numeric_id(page)
    canonical = (brief.get("username") or slug).strip()

    return {
        "facebook_username": canonical,
        "facebook_url": brief.get("profile_url") or f"https://www.facebook.com/{canonical}/",
        "facebook_full_name": embed_name,
        "facebook_id": numeric_id,
        "profile_type": None,
        "profile_pic_url": brief.get("profile_pic_url"),
        "match_score": score,
        "match_reasons": reasons,
        "title_seen": title[:120],
        "source": "instagram_to_facebook_probe",
    }


def _parallel_probe_facebook_slugs(slugs: list[str], ig_profile: dict) -> list[dict]:
    """Probe Facebook slug candidates concurrently; stop after a confident match."""
    matches: list[dict] = []
    seen_slugs: set[str] = set()
    best_score = 0
    workers = min(SAMURAI_SAFE_WORKERS, max(1, len(slugs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_probe_facebook_slug_for_instagram, slug, ig_profile, fast=True): slug
            for slug in slugs
        }
        for fut in as_completed(futures):
            try:
                result = fut.result()
            except Exception:
                continue
            if not result:
                continue
            key = result["facebook_username"].lower()
            if key in seen_slugs:
                continue
            seen_slugs.add(key)
            matches.append(result)
            best_score = max(best_score, int(result.get("match_score") or 0))
            if best_score >= FAST_CONFIDENT_MATCH_SCORE:
                break
    return matches


def find_facebook_from_instagram_profile(ig_profile: dict, *, fast: bool = False) -> dict:
    """Cross-platform lookup using an already-collected Instagram profile."""
    ig_profile = dict(ig_profile or {})
    ig_profile.setdefault("platform", "instagram")
    parsed = ig_profile.get("username") or ""
    if not parsed:
        raise ValueError("Instagram profile is missing a username")

    candidates: list[str] = []
    for text in (ig_profile.get("biography") or "", ig_profile.get("external_url") or ""):
        for match in re.finditer(r"facebook\.com/(?:profile\.php\?id=)?([A-Za-z0-9.\-_]+)", text, re.I):
            candidates.append(match.group(1))
    candidates.extend(_facebook_slug_candidates_from_instagram(parsed, ig_profile))
    if not fast:
        candidates.extend(_facebook_directory_candidates(ig_profile.get("full_name") or "", parsed, parsed))
    candidates = list(dict.fromkeys(candidates))

    probe_limit = FAST_FB_PROBE_LIMIT if fast else 12
    probe_slugs = candidates[:probe_limit]

    # Always probe in parallel (same candidates/fields as before).
    matches = _parallel_probe_facebook_slugs(probe_slugs, ig_profile) if probe_slugs else []

    matches.sort(key=lambda item: item.get("match_score", 0), reverse=True)
    best = matches[0] if matches else None

    return {
        "instagram": {
            "username": ig_profile.get("username"),
            "full_name": ig_profile.get("full_name"),
            "profile_url": f"https://www.instagram.com/{ig_profile.get('username')}/",
            "id": ig_profile.get("id"),
            "biography": ig_profile.get("biography") or "",
            "external_url": ig_profile.get("external_url"),
            "follower_count": ig_profile.get("follower_count"),
            "is_private": ig_profile.get("is_private"),
        },
        "facebook_matches": matches,
        "best_match": best,
        "note": (
            None
            if best
            else "No confident Facebook match. User may use a different Facebook username or no public Facebook profile."
        ),
    }


def find_facebook_from_instagram(ig_username: str) -> dict:
    """Reverse cross-platform lookup: Instagram username -> likely Facebook account(s)."""
    parsed = parse_username(ig_username)
    if not parsed:
        raise ValueError(f"Invalid Instagram username: {ig_username}")
    sessionid = instagram_sessionid()
    ig_profile = collect_profile(parsed, sessionid)
    return find_facebook_from_instagram_profile(ig_profile)


def fetch_cross_platform_instagram(slug: str) -> dict | None:
    """Try linked Instagram account when Facebook profile is locked or sparse."""
    guesses = list(
        dict.fromkeys(
            [
                slug.replace(".", ""),
                slug.replace(".", "_"),
                slug.split(".")[0],
            ]
        )
    )
    sessionid = instagram_sessionid()
    for guess in guesses:
        if len(guess) < 3:
            continue
        try:
            profile = collect_profile(guess, sessionid)
        except (ValueError, requests.RequestException, RuntimeError):
            continue
        if not profile.get("username"):
            continue
        return {
            "username": profile.get("username"),
            "full_name": profile.get("full_name"),
            "profile_url": f"https://www.instagram.com/{profile.get('username')}/",
            "profile_pic_url": profile.get("profile_pic_url"),
            "follower_count": profile.get("follower_count"),
            "following_count": profile.get("following_count"),
            "media_count": profile.get("media_count"),
            "is_private": profile.get("is_private"),
            "is_verified": profile.get("is_verified"),
            "biography": profile.get("biography") or "",
            "external_url": profile.get("external_url"),
            "recent_posts_count": len(profile.get("posts", [])),
            "source": "instagram_cross_platform",
        }
    return None


def build_investigation_intel(profile: dict) -> dict:
    """CID-oriented identifiers, OSINT pointers, and official Meta channels."""
    username = profile.get("username") or ""
    numeric_id = profile.get("id")
    profile_url = profile.get("profile_url") or f"https://www.facebook.com/{username}"

    identifiers = {
        "facebook_username": username,
        "facebook_numeric_id": numeric_id,
        "profile_url": profile_url,
        "profile_id_url": f"https://www.facebook.com/profile.php?id={numeric_id}" if numeric_id else None,
        "mobile_url": f"https://m.facebook.com/{username}",
        "photos_url": f"https://www.facebook.com/{username}/photos",
        "friends_url": f"https://www.facebook.com/{username}/friends",
        "about_url": f"https://www.facebook.com/{username}/about",
    }

    cross_platform = {
        "instagram_username_guess": username.replace(".", ""),
        "instagram_url": f"https://www.instagram.com/{username.replace('.', '')}/",
        "note": "Cross-check same handle on Instagram and other platforms in this tool.",
    }

    official_channels = {
        "meta_lers_portal": "https://www.facebook.com/records",
        "meta_law_enforcement_guidelines": "https://www.meta.com/safety/communities/law/guidelines/",
        "preservation_and_records": (
            "Authorized agencies can submit preservation and records requests via Meta LERS "
            "using government email. Include numeric user ID and date range."
        ),
    }

    collection_methods = {
        "public_embed": "Mobile + plugin + crawler embeds (no login).",
        "authenticated_osint": (
            "Investigator Facebook session (FB_C_USER + FB_XS) unlocks friends, photos, "
            "timeline, about — only what that account is permitted to view."
        ),
        "official_records": "Private messages, IP logs, deleted content require Meta LERS legal process.",
        "archive_osint": "Wayback Machine may retain older public page snapshots.",
    }

    legal_notice = (
        "Use only under applicable law and agency authorization. Unauthorized access to "
        "computer systems or personal data may be criminal. This tool collects publicly "
        "visible or session-visible data; it does not replace Meta law-enforcement requests."
    )

    return {
        "identifiers": identifiers,
        "cross_platform": cross_platform,
        "official_channels": official_channels,
        "collection_methods": collection_methods,
        "legal_notice": legal_notice,
        "wayback": profile.get("wayback") or {},
    }


def _merge_unique_items(existing: list[dict], new_items: list[dict], key: str) -> list[dict]:
    seen = {str(item.get(key)) for item in existing if item.get(key)}
    merged = list(existing)
    for item in new_items:
        value = item.get(key)
        if value and str(value) in seen:
            continue
        if value:
            seen.add(str(value))
        merged.append(item)
    return merged


def _merge_personal_details(base: dict, extra: dict) -> dict:
    merged = dict(base or {})
    for label, value in (extra or {}).items():
        if label and value and label not in merged:
            merged[label] = value
    return merged


def _fetch_surface_html(session: requests.Session, slug: str, path: str) -> str | None:
    """Try mbasic, then mobile, then www for authenticated sub-pages."""
    for surface in ("mbasic", "mobile", "www"):
        html = fetch_facebook_surface_page(session, slug, path, surface=surface)
        if html:
            return html
    return None


def fetch_facebook_friends(session: requests.Session, slug: str, limit: int) -> list[dict]:
    friends: list[dict] = []
    for surface in ("mbasic", "mobile"):
        path = "/friends"
        pages = 0
        while path and len(friends) < limit and pages < 10:
            html = fetch_facebook_surface_page(session, slug, path, surface=surface)
            if not html:
                break
            batch = parse_mbasic_friends(html)
            for friend in batch:
                if friend["name"].lower() not in {f["name"].lower() for f in friends}:
                    friends.append(friend)
                if len(friends) >= limit:
                    break
            next_path = _mbasic_next_path(html)
            path = next_path if next_path and next_path != path else None
            pages += 1
            time.sleep(FB_FETCH_DELAY)
        if friends:
            break
    return friends[:limit]


def fetch_facebook_photos(session: requests.Session, slug: str, limit: int) -> list[dict]:
    photos: list[dict] = []
    for surface in ("mbasic", "mobile"):
        for path in ("/photos", "/photos_by", "/photos_of"):
            page_path = path
            pages = 0
            while page_path and len(photos) < limit and pages < 8:
                html = fetch_facebook_surface_page(session, slug, page_path, surface=surface)
                if not html:
                    break
                batch = parse_mbasic_photos(html)
                for photo in batch:
                    if photo["url"] not in {p["url"] for p in photos}:
                        photos.append(photo)
                    if len(photos) >= limit:
                        break
                next_path = _mbasic_next_path(html)
                page_path = next_path if next_path and next_path != page_path else None
                pages += 1
                time.sleep(FB_FETCH_DELAY)
            if photos:
                break
        if photos:
            break
    return photos[:limit]


def fetch_facebook_videos(session: requests.Session, slug: str, limit: int) -> list[dict]:
    videos: list[dict] = []
    for surface in ("mbasic", "mobile"):
        for path in ("/videos", "/reels"):
            page_path = path
            pages = 0
            while page_path and len(videos) < limit and pages < 8:
                html = fetch_facebook_surface_page(session, slug, page_path, surface=surface)
                if not html:
                    break
                batch = parse_mbasic_videos(html)
                for video in batch:
                    if video["url"] not in {v["url"] for v in videos}:
                        videos.append(video)
                    if len(videos) >= limit:
                        break
                next_path = _mbasic_next_path(html)
                page_path = next_path if next_path and next_path != page_path else None
                pages += 1
                time.sleep(FB_FETCH_DELAY)
            if videos:
                break
        if videos:
            break
    return videos[:limit]


def enrich_facebook_with_session(profile: dict, session: requests.Session) -> dict:
    """Authenticated multi-surface collection: mbasic + mobile + www JSON."""
    slug = profile["username"]
    auth_sources = []

    for path in ("/about", "?v=info"):
        about_html = _fetch_surface_html(session, slug, path)
        if not about_html:
            continue
        mbasic_about = parse_mbasic_about_details(about_html)
        mobile_about = parse_mobile_about_sections(about_html)
        json_about = extract_profile_fields_from_json(about_html)
        profile["personal_details"] = _merge_personal_details(
            profile.get("personal_details"),
            _merge_personal_details(
                mbasic_about.get("personal_details", {}),
                _merge_personal_details(
                    mobile_about.get("personal_details", {}),
                    json_about.get("personal_details", {}),
                ),
            ),
        )
        for bio in (
            mobile_about.get("biography"),
            mbasic_about.get("biography"),
        ):
            if bio and not _generic_facebook_bio(bio):
                profile["biography"] = bio
        for pic in (
            mobile_about.get("profile_pic_url"),
            mbasic_about.get("profile_pic_url"),
            json_about.get("profile_pic_url"),
        ):
            if _is_direct_image_url(pic):
                profile["profile_pic_url"] = pic
        auth_sources.append("about")
        break

    www_html = fetch_facebook_surface_page(session, slug, "", surface="www")
    if www_html:
        json_fields = extract_profile_fields_from_json(www_html)
        profile["personal_details"] = _merge_personal_details(
            profile.get("personal_details"), json_fields.get("personal_details", {})
        )
        if json_fields.get("friend_count_hint") and not profile.get("friend_count"):
            try:
                profile["friend_count"] = int(json_fields["friend_count_hint"])
            except (ValueError, TypeError):
                pass
        if _is_direct_image_url(json_fields.get("profile_pic_url")):
            profile["profile_pic_url"] = json_fields["profile_pic_url"]
        profile["timeline_posts"] = parse_mobile_timeline_posts(www_html)
        auth_sources.append("www_json")

    mobile_timeline = fetch_facebook_surface_page(session, slug, "", surface="mobile")
    if mobile_timeline:
        mobile_posts = parse_mobile_timeline_posts(mobile_timeline)
        profile["timeline_posts"] = _merge_unique_items(
            profile.get("timeline_posts", []), mobile_posts, "text"
        )
        auth_sources.append("mobile_timeline")

    profile["friends"] = fetch_facebook_friends(session, slug, MAX_FB_FRIENDS)
    if profile["friends"]:
        auth_sources.append("friends")
    profile["friend_count"] = profile.get("friend_count") or len(profile["friends"])

    profile["photos"] = _merge_unique_items(
        profile.get("photos", []),
        fetch_facebook_photos(session, slug, MAX_FB_PHOTOS),
        "url",
    )
    if len(profile["photos"]) > 1:
        auth_sources.append("photos")

    profile["videos"] = fetch_facebook_videos(session, slug, MAX_FB_VIDEOS)
    profile["reels"] = [video for video in profile["videos"] if video.get("is_reel")]
    if profile["videos"]:
        auth_sources.append("videos")

    profile["authenticated"] = True
    profile["auth_sources"] = list(dict.fromkeys(auth_sources))
    profile["source"] = "facebook_authenticated"
    profile.pop("login_required_for", None)
    profile.pop("public_limits", None)
    return profile


def _similar_profile_photo_urls(profile: dict) -> set[str]:
    urls: set[str] = set()
    for similar in profile.get("similar_profiles") or []:
        for photo in similar.get("photos") or []:
            url = photo.get("url")
            if url:
                urls.add(url)
    return urls


def _partition_facebook_media(
    profile: dict, target_slug: str
) -> tuple[list[dict], dict[str, list[dict]], set[str]]:
    """Split photos into target vs similar-account buckets."""
    similar_urls = _similar_profile_photo_urls(profile)
    target_slug_l = target_slug.lower()
    url_to_owner: dict[str, str] = {}
    for similar in profile.get("similar_profiles") or []:
        sim_user = (similar.get("username") or "").strip()
        if not sim_user:
            continue
        for photo in similar.get("photos") or []:
            url = photo.get("url")
            if url:
                url_to_owner[url] = sim_user

    target_photos: list[dict] = []
    similar_by_owner: dict[str, list[dict]] = {}
    seen_urls: set[str] = set()

    def add_similar(owner: str, photo: dict) -> None:
        url = photo.get("url")
        if not url or url in seen_urls:
            return
        owner_key = owner or "unknown"
        if owner_key.lower() == target_slug_l:
            return
        similar_by_owner.setdefault(owner_key, []).append(photo)
        seen_urls.add(url)

    def add_target(photo: dict) -> None:
        url = photo.get("url")
        if not url or url in seen_urls:
            return
        target_photos.append(photo)
        seen_urls.add(url)

    for photo in profile.get("photos") or []:
        url = photo.get("url")
        owner = (photo.get("owner_username") or url_to_owner.get(url or "", "")).strip()
        if url in url_to_owner:
            add_similar(url_to_owner[url], photo)
        elif url in similar_urls:
            add_similar(owner or "similar", photo)
        elif photo.get("is_target_profile") is False:
            add_similar(owner or "similar", photo)
        elif owner.lower() == target_slug_l:
            add_target(photo)
        elif photo.get("is_target_profile") is True:
            add_target(photo)

    for similar in profile.get("similar_profiles") or []:
        sim_user = (similar.get("username") or "").strip()
        if not sim_user or sim_user.lower() == target_slug_l:
            continue
        for photo in similar.get("photos") or []:
            add_similar(sim_user, dict(photo))

    return target_photos, similar_by_owner, similar_urls


def _is_target_facebook_media(item: dict, target_slug: str, similar_urls: set[str] | None = None) -> bool:
    """True when media belongs to the searched username (not a similar profile)."""
    url = item.get("url") or ""
    if similar_urls and url in similar_urls:
        return False
    if item.get("is_target_profile") is True:
        return True
    if item.get("is_target_profile") is False:
        return False
    owner = (item.get("owner_username") or "").lower()
    if owner:
        return owner == target_slug.lower()
    profile_url = item.get("profile_url") or ""
    if profile_url:
        match = re.search(r"facebook\.com/([^/?#]+)", profile_url)
        if match:
            return match.group(1).lower() == target_slug.lower()
    return False


def _download_fb_photo_batch(
    photos: list[dict],
    photos_dir: str,
    gb_session: requests.Session,
    requester: requests.Session,
    auth_requester: requests.Session | None,
    downloaded_urls: set[str],
) -> tuple[int, int]:
    """Download a list of photos; returns (images_ok, failed)."""
    images = failed = 0
    os.makedirs(photos_dir, exist_ok=True)
    for index, photo in enumerate(photos, start=1):
        url = photo.get("url")
        if not url or url in downloaded_urls:
            continue
        ext = _safe_extension(url, "image")
        dest = os.path.join(photos_dir, f"{index:02d}{ext}")
        ok, _ = _download_fb_media_url(gb_session, url, dest, auth_requester)
        if not ok:
            ok = download_file_with_session(requester, url, dest)
        if ok:
            photo["local_path"] = os.path.abspath(dest)
            images += 1
            downloaded_urls.add(url)
        else:
            failed += 1
        time.sleep(0.2)
    return images, failed


def _download_fb_video_batch(
    videos: list[dict],
    photos_dir: str,
    reels_dir: str,
    gb_session: requests.Session,
    requester: requests.Session,
    auth_requester: requests.Session | None,
    downloaded_urls: set[str],
) -> tuple[int, int, int]:
    """Download videos/reels; returns (images_ok, videos_ok, failed)."""
    images = video_count = failed = 0
    os.makedirs(photos_dir, exist_ok=True)
    os.makedirs(reels_dir, exist_ok=True)
    for index, video in enumerate(videos, start=1):
        media_url = video.get("url")
        if not media_url or not str(media_url).startswith("http"):
            continue
        if media_url in downloaded_urls and not _is_lookaside_url(media_url):
            continue

        if _is_lookaside_url(media_url):
            try:
                with gb_session.get(
                    media_url, headers=GOOGLEBOT_HEADERS, stream=True, timeout=60
                ) as response:
                    if response.status_code != 200:
                        failed += 1
                        continue
                    content_type = response.headers.get("content-type", "")
                    if "text/html" in content_type:
                        failed += 1
                        continue
                    ext = _extension_from_content_type(content_type, ".bin")
                    if ext in {".mp4"} or "video" in content_type:
                        dest = os.path.join(reels_dir, f"{index:02d}{ext}")
                    else:
                        dest = os.path.join(photos_dir, f"media_{index:02d}{ext}")
                    with open(dest, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=65536):
                            if chunk:
                                handle.write(chunk)
                    video["local_path"] = os.path.abspath(dest)
                    video["content_type"] = content_type
                    downloaded_urls.add(media_url)
                    if ext == ".mp4" or "video" in content_type:
                        video_count += 1
                    else:
                        images += 1
            except (requests.RequestException, OSError):
                failed += 1
            time.sleep(0.2)
            continue

        thumb = video.get("thumbnail")
        target = media_url if media_url.endswith(".mp4") else (thumb or media_url)
        if not target or not str(target).startswith("http"):
            continue
        dest = os.path.join(reels_dir, f"{index:02d}{_safe_extension(target, 'video')}")
        ok, _ = _download_fb_media_url(gb_session, target, dest, auth_requester)
        if not ok:
            ok = download_file_with_session(requester, target, dest)
        if ok:
            video["local_path"] = os.path.abspath(dest)
            video_count += 1
            downloaded_urls.add(target)
        else:
            failed += 1
        time.sleep(0.2)
    return images, video_count, failed


def download_facebook_media(profile: dict, slug: str, session: requests.Session | None = None) -> dict:
    base = slug_to_filename(slug)
    folder = f"{base}_facebook_media"
    similar_root = f"{base}_similar_profiles"
    photos_dir = os.path.join(folder, "photos")
    reels_dir = os.path.join(folder, "reels")
    os.makedirs(photos_dir, exist_ok=True)
    os.makedirs(reels_dir, exist_ok=True)
    os.makedirs(similar_root, exist_ok=True)

    if _is_facebook_login_blocked(profile, slug) and not profile.get("photos"):
        return {
            "folder": os.path.abspath(folder),
            "similar_profiles_folder": os.path.abspath(similar_root),
            "profile_picture": None,
            "images": 0,
            "videos": 0,
            "failed": 0,
            "similar_profiles": [],
            "blocked": True,
            "error": _facebook_login_blocked_message(slug),
        }

    headers = MBASIC_HEADERS.copy()
    if session:
        requester = session
        auth_requester = session
    else:
        requester = requests.Session()
        requester.headers.update(headers)
        auth_requester = None

    gb_session = requests.Session()
    images = videos = failed = 0
    profile_pic_path = None
    downloaded_urls: set[str] = set()
    target_slug = slug

    target_photos, similar_by_owner, similar_urls = _partition_facebook_media(profile, target_slug)

    pic_url = profile.get("profile_pic_url")
    if pic_url:
        dest = os.path.join(folder, "profile_picture.jpg")
        ok, _ = _download_fb_media_url(gb_session, pic_url, dest, auth_requester)
        if not ok:
            ok = download_file_with_session(requester, pic_url, dest)
        if ok:
            profile_pic_path = os.path.abspath(dest)
            images += 1
            downloaded_urls.add(pic_url)
        else:
            failed += 1

    img_ok, fail_ok = _download_fb_photo_batch(
        target_photos, photos_dir, gb_session, requester, auth_requester, downloaded_urls
    )
    images += img_ok
    failed += fail_ok

    video_items = profile.get("videos", []) or []
    reel_items = profile.get("reels", []) or []
    merged_videos: list[dict] = []
    seen_video_keys: set[str] = set()
    for item in video_items + reel_items:
        if not _is_target_facebook_media(item, target_slug, similar_urls):
            owner = (item.get("owner_username") or "similar").strip()
            similar_by_owner.setdefault(owner, [])
            continue
        key = item.get("media_id") or item.get("url") or ""
        if key in seen_video_keys:
            continue
        seen_video_keys.add(key)
        merged_videos.append(item)

    img_ok, vid_ok, fail_ok = _download_fb_video_batch(
        merged_videos, photos_dir, reels_dir, gb_session, requester, auth_requester, downloaded_urls
    )
    images += img_ok
    videos += vid_ok
    failed += fail_ok

    similar_downloads: list[dict] = []
    similar_meta = {
        (s.get("username") or "").lower(): s for s in (profile.get("similar_profiles") or [])
    }

    for owner, owner_photos in similar_by_owner.items():
        if owner.lower() == target_slug.lower() or not owner_photos:
            continue
        meta = similar_meta.get(owner.lower(), {})
        sim_folder = os.path.join(similar_root, slug_to_filename(owner))
        sim_photos_dir = os.path.join(sim_folder, "photos")
        sim_reels_dir = os.path.join(sim_folder, "reels")
        os.makedirs(sim_photos_dir, exist_ok=True)
        os.makedirs(sim_reels_dir, exist_ok=True)

        sim_pic = meta.get("profile_pic_url")
        sim_pic_path = None
        if sim_pic and sim_pic not in downloaded_urls:
            sim_pic_dest = os.path.join(sim_folder, "profile_picture.jpg")
            ok, _ = _download_fb_media_url(gb_session, sim_pic, sim_pic_dest, auth_requester)
            if not ok:
                ok = download_file_with_session(requester, sim_pic, sim_pic_dest)
            if ok:
                sim_pic_path = os.path.abspath(sim_pic_dest)
                downloaded_urls.add(sim_pic)

        sim_img, sim_fail = _download_fb_photo_batch(
            owner_photos, sim_photos_dir, gb_session, requester, auth_requester, downloaded_urls
        )
        failed += sim_fail

        similar_downloads.append(
            {
                "username": owner,
                "full_name": meta.get("full_name") or owner,
                "profile_url": meta.get("profile_url") or _facebook_profile_url_from_slug(owner),
                "folder": os.path.abspath(sim_folder),
                "profile_picture": sim_pic_path,
                "images": sim_img + (1 if sim_pic_path else 0),
                "failed": sim_fail,
            }
        )

    info_path = os.path.join(similar_root, "_info.txt")
    if similar_downloads:
        if os.path.isfile(info_path):
            os.remove(info_path)
    else:
        with open(info_path, "w", encoding="utf-8") as handle:
            handle.write(
                "No similar profile photos were found for this search.\n"
                "Similar accounts appear when Facebook shows 'Others named ...' on the profile page.\n"
            )

    return {
        "folder": os.path.abspath(folder),
        "similar_profiles_folder": os.path.abspath(similar_root),
        "profile_picture": profile_pic_path,
        "images": images,
        "videos": videos,
        "failed": failed,
        "similar_profiles": similar_downloads,
    }


def _enrich_locked_profile_osint(profile: dict, slug: str) -> dict:
    """Add cross-platform Instagram intel when Facebook profile is locked."""
    locked = "locked" in profile.get("personal_details", {}).get("Profile Status", "").lower()
    if not locked or profile.get("authenticated"):
        return profile
    ig_intel = fetch_cross_platform_instagram(slug)
    if ig_intel:
        profile["cross_platform_instagram"] = ig_intel
    profile["login_required_for"] = [
        "Facebook friends list (profile locked — requires FB session or Meta LERS)",
        "Facebook timeline posts and photo albums (profile locked)",
        "Facebook reels feed (profile locked)",
        "Facebook contact info and bio (profile locked)",
    ]
    if ig_intel:
        profile["login_required_for"].append(
            f"Instagram @{ig_intel.get('username')} may have additional public data (see cross_platform_instagram)"
        )
    return profile


def fetch_facebook_profile(slug: str, *, fast: bool = False, seed_username: str | None = None) -> dict:
    """Combine Facebook's public embed surfaces (mobile, plugin, crawler, googlebot, oembed).

    Full mode fetches every source in parallel (same fields as before, less wall time).
    Fast mode uses fewer sources, also in parallel.
    """
    if fast:
        embed_jobs = {
            "mobile": fetch_facebook_mobile_embed,
            "plugin": fetch_facebook_plugin_embed,
            "crawler": fetch_facebook_crawler_embed,
        }
    else:
        embed_jobs = {
            "mobile": fetch_facebook_mobile_embed,
            "plugin": fetch_facebook_plugin_embed,
            "crawler": fetch_facebook_crawler_embed,
            "googlebot": fetch_facebook_googlebot_embed,
            "oembed": fetch_facebook_oembed,
        }

    embed_results: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=min(SAMURAI_SAFE_WORKERS, len(embed_jobs))) as pool:
        futures = {pool.submit(fn, slug): name for name, fn in embed_jobs.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                embed_results[name] = fut.result()
            except Exception:
                embed_results[name] = None

    mobile = embed_results.get("mobile")
    plugin = embed_results.get("plugin")
    crawler = embed_results.get("crawler")
    googlebot = embed_results.get("googlebot")
    oembed = embed_results.get("oembed")
    if fast and not any([mobile, plugin, crawler]):
        googlebot = fetch_facebook_googlebot_main(slug)

    if not any([mobile, plugin, crawler, googlebot, oembed]):
        raise ValueError(
            f"Could not read Facebook profile data for '{slug}'. "
            "The profile may be private, restricted, or unavailable."
        )

    merged = merge_facebook_public_profiles(mobile, plugin, crawler, googlebot, oembed)
    profile = {
        "platform": "facebook",
        "username": merged.get("username") or slug,
        "full_name": merged.get("full_name") or slug,
        "biography": merged.get("biography") or "",
        "profile_type": merged.get("profile_type", "unknown"),
        "like_count": merged.get("like_count"),
        "talking_about_count": merged.get("talking_about_count"),
        "follower_count": merged.get("follower_count") or merged.get("like_count"),
        "profile_pic_url": merged.get("profile_pic_url"),
        "profile_url": merged.get("profile_url") or f"https://www.facebook.com/{slug}",
        "id": merged.get("id"),
        "friends": merged.get("friends", []),
        "photos": merged.get("photos", []),
        "videos": merged.get("videos", []),
        "reels": merged.get("reels", []),
        "timeline_posts": merged.get("timeline_posts", []),
        "personal_details": merged.get("personal_details", {}),
        "data_sources": merged.get("data_sources", []),
        "source": "facebook_embed",
        "friend_count": merged.get("friend_count"),
        "friends_label": merged.get("friends_label"),
        "similar_profiles": merged.get("similar_profiles", []),
    }

    profile_url = profile.get("profile_url") or f"https://www.facebook.com/{slug}"
    profile["friends_url"] = f"{profile_url.rstrip('/')}/friends"
    profile["photos_url"] = f"{profile_url.rstrip('/')}/photos"
    profile["reels_url"] = f"{profile_url.rstrip('/')}/reels"

    pic_url = profile.get("profile_pic_url")
    if not _is_direct_image_url(pic_url) and not fast:
        graph_pic = fetch_facebook_graph_picture(slug)
        if graph_pic:
            profile["profile_pic_url"] = graph_pic
            profile.setdefault("data_sources", []).append("facebook_graph_picture")
    pic_url = profile.get("profile_pic_url")
    if _is_direct_image_url(pic_url) and not any(
        p.get("url") == pic_url for p in profile.get("photos", [])
    ):
        profile["photos"] = [
            {
                "url": pic_url,
                "type": "profile_picture",
                "owner_username": slug,
                "profile_url": _facebook_profile_url_from_slug(slug),
                "is_target_profile": True,
                "live_url": pic_url,
            }
        ] + profile["photos"]

    try:
        raw_pages = list(merged.get("raw_pages") or [])
        if not raw_pages and not fast:
            main_response = requests.get(
                f"https://www.facebook.com/{slug}",
                headers=GOOGLEBOT_HEADERS,
                timeout=30,
                allow_redirects=True,
            )
            if main_response.status_code == 200 and not _is_facebook_login_redirect(main_response):
                raw_pages = [main_response.text]
    except requests.RequestException:
        raw_pages = list(merged.get("raw_pages") or [])

    if profile.get("photos") and profile.get("similar_profiles") and not raw_pages:
        raw_pages = list(merged.get("raw_pages") or [])

    profile["photos"], similar_profiles = enrich_facebook_photo_ownership(
        profile.get("photos", []),
        raw_pages,
        slug,
        full_name=profile.get("full_name") or "",
        fast=fast,
        seed_username=seed_username,
    )
    profile["similar_profiles"] = similar_profiles or merged.get("similar_profiles", [])
    profile["raw_pages"] = raw_pages

    profile["username"] = slug
    profile["profile_url"] = f"https://www.facebook.com/{slug}/"
    if crawler and crawler.get("full_name") and profile.get("full_name") in (None, slug):
        profile["full_name"] = crawler["full_name"]
    if googlebot and googlebot.get("full_name") and profile.get("full_name") in (None, slug):
        profile["full_name"] = googlebot["full_name"]
    if _is_facebook_login_blocked(profile, slug):
        raise ValueError(_facebook_login_blocked_message(slug))

    # Photos gallery = profile picture + /photos album only.
    # Never keep main-page googlebot media (it mixes "Others named …" thumbnails).
    if not fast:
        try:
            album_photos = fetch_public_target_album_photos(slug, limit=min(12, MAX_FB_PHOTOS))
            profile_pics = [
                p for p in (profile.get("photos") or [])
                if p.get("type") == "profile_picture"
                or p.get("source") in {"facebook_graph_picture", "profile_picture"}
            ]
            for pic in profile_pics:
                pic["is_target_profile"] = True
                pic["owner_username"] = slug
            # Album photos already blacklisted against "Others named" and verified as images.
            profile["photos"] = [*profile_pics, *album_photos]
            # Anything else from the main page is foreign / unreliable — drop it.
            profile.setdefault("data_sources", []).append("photos_page")
        except Exception:
            # Fall back to profile picture only rather than wrong people's photos.
            profile["photos"] = [
                p for p in (profile.get("photos") or [])
                if p.get("type") == "profile_picture"
            ]
            for pic in profile["photos"]:
                pic["is_target_profile"] = True
                pic["owner_username"] = slug

    locked = profile.get("personal_details", {}).get("Profile Status", "")
    if locked and "locked" in locked.lower():
        profile["public_limits"] = [
            f"Profile status: {locked}. Work, education, photos, and timeline are hidden by the user.",
            "Googlebot embed confirms section labels but post albums/reels are not exposed for locked profiles.",
            "Lookaside media_ids in crawler HTML may still yield profile/cover images (Googlebot UA required).",
            "For full post photos/reels use FB session (FB_C_USER + FB_XS) or Meta LERS.",
        ]
        if not fast:
            profile = _enrich_locked_profile_osint(profile, slug)
    elif profile["profile_type"] == "personal" and not profile.get("timeline_posts"):
        target_photo_count = sum(
            1 for p in (profile.get("photos") or []) if p.get("is_target_profile") is True
        )
        if target_photo_count <= 1:
            profile["public_limits"] = [
                "Personal profiles hide timeline/photos unless public or unlocked.",
                "Googlebot embed may still reveal work/education labels when set to Public.",
                "Set FB_C_USER + FB_XS for friends and full albums.",
            ]
    return profile


def collect_facebook_profile(slug: str) -> dict:
    profile = fetch_facebook_profile(slug)
    profile.setdefault("friends", [])
    profile.setdefault("photos", [])
    profile.setdefault("videos", [])
    profile.setdefault("reels", [])
    profile.setdefault("personal_details", {})
    profile["authenticated"] = False

    session = make_facebook_session()
    if session:
        try:
            profile = enrich_facebook_with_session(profile, session)
        except requests.RequestException:
            console.print(
                "[yellow]Logged-in Facebook fetch failed. Using public data only.[/yellow]"
            )
    else:
        profile["login_required_for"] = [
            "friends list",
            "post/timeline photos",
            "videos and reels feed",
            "work, education, and contact details",
        ]

    profile["download_summary"] = download_facebook_media(profile, slug, session)
    profile["wayback"] = fetch_wayback_intel(profile.get("profile_url") or f"https://www.facebook.com/{slug}")
    profile["investigation"] = build_investigation_intel(profile)
    profile = _enrich_locked_profile_osint(profile, slug)
    return profile


def collect_profile(username: str, sessionid: str | None = None, *, fast: bool = False) -> dict:
    active_sessionid = sessionid or instagram_sessionid()
    session = make_session(active_sessionid)
    try:
        session.get("https://www.instagram.com/", headers=BROWSER_HEADERS, timeout=20)
    except requests.RequestException:
        pass
    user, api_payload = fetch_web_profile_info(session, username)
    if user:
        profile = profile_from_web_api(user, username)
        if api_payload:
            profile["instagram_api_response"] = api_payload
    else:
        # Embed + public page in parallel (same sources, less wait).
        profile = None
        embed_error: Exception | None = None
        page_error: Exception | None = None
        with ThreadPoolExecutor(max_workers=2) as pool:
            embed_fut = pool.submit(fetch_profile_from_embed, username)
            page_fut = pool.submit(fetch_profile_from_public_page, username)
            try:
                profile = embed_fut.result()
            except Exception as exc:
                embed_error = exc
                profile = None
            try:
                page_profile = page_fut.result()
            except Exception as exc:
                page_error = exc
                page_profile = None
        if page_profile:
            profile = (
                _merge_profile_fields(profile, page_profile)
                if profile and _has_usable_public_profile(profile)
                else page_profile
            )
        if profile is None or not _has_usable_public_profile(profile or {}):
            raise (page_error or embed_error or RuntimeError(f"Could not load Instagram profile for {username}"))
        if profile.get("source") == "embed":
            profile = enrich_from_profile_page(profile, username)
    enrich_posts_from_user_feed(profile, session)
    if not fast:
        # Reels + comments in parallel — same data, less wall-clock time.
        with ThreadPoolExecutor(max_workers=2) as pool:
            reel_fut = pool.submit(enrich_reels, profile)
            if active_sessionid:
                profile["comments_available"] = True
                comment_fut = pool.submit(enrich_comments, session, profile)
            else:
                profile["comments_available"] = False
                comment_fut = pool.submit(_enrich_public_comments_parallel, profile)
            reel_fut.result()
            comment_fut.result()
    else:
        profile["comments_available"] = bool(active_sessionid)
        for post in profile.get("posts", []):
            if "comments" not in post:
                post["comments"] = []
    return profile


def _enrich_public_comments_parallel(profile: dict) -> None:
    """Public embed comment snippets — same as sequential path, fetched in parallel."""
    targets: list[dict] = []
    for post in profile.get("posts", []):
        if post.get("comments"):
            continue
        if not post.get("shortcode") or not post.get("comment_count"):
            post["comments"] = []
            continue
        targets.append(post)
        if len(targets) >= MAX_COMMENT_POSTS:
            break

    if not targets:
        return

    def _fetch(post: dict) -> tuple[dict, list]:
        details = fetch_post_details(post["shortcode"])
        return post, (details.get("comments") if details else None) or []

    workers = min(SAMURAI_SAFE_WORKERS, len(targets))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for post, comments in pool.map(_fetch, targets):
            post["comments"] = comments


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_profile(profile: dict) -> None:
    lines = [
        f"[bold]Username:[/bold] {profile['username']}",
        f"[bold]Full Name:[/bold] {profile.get('full_name') or 'N/A'}",
        f"[bold]Verified:[/bold] {profile.get('is_verified', False)}",
        f"[bold]Private:[/bold] {profile.get('is_private', False)}",
        f"[bold]Followers:[/bold] {profile.get('follower_count')}",
        f"[bold]Following:[/bold] {profile.get('following_count', 'N/A')}",
        f"[bold]Posts:[/bold] {profile.get('media_count', 'N/A')}",
    ]
    if profile.get("category"):
        lines.append(f"[bold]Category:[/bold] {profile['category']}")
    if profile.get("external_url"):
        lines.append(f"[bold]Website:[/bold] {profile['external_url']}")
    lines.append(f"[bold]ID:[/bold] {profile.get('id', 'N/A')}")
    console.print(Panel("\n".join(lines), title="Profile", border_style="cyan"))

    bio = profile.get("biography")
    if bio:
        console.print(Panel(bio, title="Bio", border_style="magenta"))
    elif profile.get("source") == "embed":
        console.print(
            "[yellow]Bio is not available without logging in. "
            "Provide a session ID (see notes) to unlock it.[/yellow]"
        )

    bio_tags = extract_hashtags(bio)
    bio_mentions = extract_mentions(bio)
    if bio_tags:
        console.print("[bold]Bio hashtags:[/bold]", " ".join(f"#{t}" for t in bio_tags))
    if bio_mentions:
        console.print("[bold]Bio mentions:[/bold]", " ".join(f"@{m}" for m in bio_mentions))


def render_facebook_profile(profile: dict) -> None:
    lines = [
        f"[bold]Platform:[/bold] Facebook",
        f"[bold]Username / Slug:[/bold] {profile.get('username')}",
        f"[bold]Full Name:[/bold] {profile.get('full_name') or 'N/A'}",
        f"[bold]Profile Type:[/bold] {profile.get('profile_type', 'unknown')}",
        f"[bold]Likes / Followers:[/bold] {_fmt(profile.get('like_count') or profile.get('follower_count'))}",
        f"[bold]Talking About:[/bold] {_fmt(profile.get('talking_about_count'))}",
        f"[bold]Friends Found:[/bold] {_fmt(profile.get('friend_count', len(profile.get('friends', []))))}",
        f"[bold]Photos Found:[/bold] {len(profile.get('photos', []))}",
        f"[bold]Videos/Reels Found:[/bold] {len(profile.get('videos', []))}",
        f"[bold]Profile URL:[/bold] {profile.get('profile_url', 'N/A')}",
    ]
    if profile.get("friends_label"):
        lines.append(f"[bold]Friends Label:[/bold] {profile['friends_label']}")
    if profile.get("friends_url"):
        lines.append(f"[bold]Friends URL:[/bold] {profile['friends_url']}")
    lines.extend(
        [
        f"[bold]ID:[/bold] {profile.get('id', 'N/A')}",
        f"[bold]Logged In:[/bold] {profile.get('authenticated', False)}",
        ]
    )
    data_sources = profile.get("data_sources") or []
    if data_sources:
        lines.append(f"[bold]Public Embed Sources:[/bold] {', '.join(data_sources)}")
    auth_sources = profile.get("auth_sources") or []
    if auth_sources:
        lines.append(f"[bold]Auth Sources:[/bold] {', '.join(auth_sources)}")
    console.print(Panel("\n".join(lines), title="Facebook Profile", border_style="cyan"))

    bio = profile.get("biography")
    if bio:
        console.print(Panel(bio, title="About", border_style="magenta"))

    for note in profile.get("public_limits") or []:
        console.print(f"[yellow]{note}[/yellow]")

    personal = profile.get("personal_details") or {}
    if personal:
        table = Table(title="Personal Details", show_lines=True, header_style="bold magenta")
        table.add_column("Field", width=24)
        table.add_column("Value", overflow="fold")
        for label, value in personal.items():
            table.add_row(_safe_console_text(label), _safe_console_text(str(value)))
        console.print(table)
    elif not profile.get("authenticated"):
        console.print(
            "[yellow]Friends, photos, reels, and personal details require an investigator session.[/yellow]\n"
            "[dim]Set FB_C_USER + FB_XS or FB_COOKIES_FILE (export from browser while logged in).[/dim]\n"
            "[dim]For private/deleted data use Meta LERS: https://www.facebook.com/records[/dim]"
        )

    timeline = profile.get("timeline_posts", [])
    if timeline:
        table = Table(title=f"Timeline Posts ({len(timeline)})", show_lines=True, header_style="bold green")
        table.add_column("#", justify="right", width=4)
        table.add_column("Text", overflow="fold")
        table.add_column("URL", overflow="fold")
        for index, post in enumerate(timeline[:20], start=1):
            table.add_row(
                str(index),
                _safe_console_text((post.get("text") or "—")[:200]),
                _safe_console_text(post.get("url") or "—"),
            )
        console.print(table)

    investigation = profile.get("investigation") or {}
    if investigation:
        intel_lines = [
            f"[bold]Numeric ID:[/bold] {investigation.get('identifiers', {}).get('facebook_numeric_id', 'N/A')}",
            f"[bold]ID URL:[/bold] {investigation.get('identifiers', {}).get('profile_id_url', 'N/A')}",
            f"[bold]Instagram guess:[/bold] {investigation.get('cross_platform', {}).get('instagram_url', 'N/A')}",
            f"[bold]Meta LERS:[/bold] {investigation.get('official_channels', {}).get('meta_lers_portal', 'N/A')}",
        ]
        wayback = investigation.get("wayback") or profile.get("wayback") or {}
        if wayback.get("available"):
            snap = (wayback.get("snapshots") or [{}])[0]
            intel_lines.append(f"[bold]Wayback snapshot:[/bold] {snap.get('url', 'N/A')}")
        console.print(Panel("\n".join(intel_lines), title="Investigation Intel (CID)", border_style="bright_blue"))
        console.print(f"[dim]{investigation.get('legal_notice', '')}[/dim]")

    friends = profile.get("friends", [])
    if friends:
        table = Table(title=f"Friends ({len(friends)})", show_lines=False, header_style="bold green")
        table.add_column("#", justify="right", width=4)
        table.add_column("Name", width=28)
        table.add_column("Profile", overflow="fold")
        for index, friend in enumerate(friends[:50], start=1):
            table.add_row(str(index), friend.get("name") or "—", friend.get("profile_url") or "—")
        if len(friends) > 50:
            console.print(f"[dim]Showing first 50 of {len(friends)} friends.[/dim]")
        console.print(table)

    photos = profile.get("photos", [])
    if photos:
        table = Table(title=f"Photos ({len(photos)})", show_lines=False, header_style="bold blue")
        table.add_column("#", justify="right", width=4)
        table.add_column("Owner", width=18, overflow="fold")
        table.add_column("Profile URL", overflow="fold")
        table.add_column("Image URL", overflow="fold")
        table.add_column("Saved", width=8)
        for index, photo in enumerate(photos[:30], start=1):
            table.add_row(
                str(index),
                photo.get("owner_username") or profile.get("username") or "—",
                photo.get("profile_url") or "—",
                (photo.get("url") or photo.get("live_url") or "—")[:80],
                "yes" if photo.get("local_path") else "—",
            )
        console.print(table)

    similar = profile.get("similar_profiles") or []
    if similar:
        table = Table(title=f"Similar Profiles ({len(similar)})", show_lines=False, header_style="bold yellow")
        table.add_column("Name", width=22, overflow="fold")
        table.add_column("Username", width=20, overflow="fold")
        table.add_column("Profile URL", overflow="fold")
        table.add_column("Photos", justify="right", width=6)
        for entry in similar[:20]:
            table.add_row(
                entry.get("full_name") or "—",
                entry.get("username") or "—",
                entry.get("profile_url") or "—",
                str(entry.get("photo_count", len(entry.get("photos", [])))),
            )
        console.print(table)

    videos = profile.get("videos", [])
    if videos:
        table = Table(title=f"Videos / Reels ({len(videos)})", show_lines=False, header_style="bold blue")
        table.add_column("Title", width=24, overflow="fold")
        table.add_column("Type", width=8)
        table.add_column("URL", overflow="fold")
        for video in videos[:30]:
            table.add_row(
                video.get("title") or "—",
                "Reel" if video.get("is_reel") else "Video",
                video.get("url") or "—",
            )
        console.print(table)

    if profile.get("profile_pic_url"):
        console.print(f"[bold]Profile Picture:[/bold] {profile['profile_pic_url']}")

    summary = profile.get("download_summary")
    if summary:
        render_download_summary(summary)


def render_posts(profile: dict) -> None:
    posts = profile.get("posts", [])
    if not posts:
        console.print("[yellow]No recent posts could be retrieved (account may be private).[/yellow]")
        return

    table = Table(title=f"Recent Posts ({len(posts)})", show_lines=True, header_style="bold green")
    table.add_column("#", justify="right", width=3)
    table.add_column("Type", width=8)
    table.add_column("Date", width=17)
    table.add_column("Likes", justify="right", width=9)
    table.add_column("Comments", justify="right", width=9)
    table.add_column("Caption / Hashtags", overflow="fold")

    for index, post in enumerate(posts, start=1):
        caption = (post.get("caption") or "").replace("\n", " ").strip()
        snippet = caption[:140] + ("..." if len(caption) > 140 else "")
        tags = post.get("hashtags") or []
        tag_line = ("\n[cyan]" + " ".join(f"#{t}" for t in tags) + "[/cyan]") if tags else ""
        table.add_row(
            str(index),
            post.get("type", ""),
            post.get("timestamp") or "—",
            _fmt(post.get("like_count")),
            _fmt(post.get("comment_count")),
            (snippet or "[dim]No caption[/dim]") + tag_line,
        )
    console.print(table)


def render_reels(profile: dict) -> None:
    reels = [p for p in profile.get("posts", []) if p.get("type") in ("Reel", "Video") or p.get("is_video")]
    if not reels:
        return

    table = Table(title=f"Reels / Videos ({len(reels)})", show_lines=True, header_style="bold blue")
    table.add_column("Shortcode", width=14)
    table.add_column("Views", justify="right", width=12)
    table.add_column("Duration", justify="right", width=9)
    table.add_column("Comments", justify="right", width=9)
    table.add_column("URL", overflow="fold")

    for reel in reels:
        duration = reel.get("video_duration")
        duration_str = f"{float(duration):.1f}s" if duration else "—"
        table.add_row(
            reel.get("shortcode") or "—",
            _fmt(reel.get("video_view_count")),
            duration_str,
            _fmt(reel.get("comment_count")),
            reel.get("url") or "—",
        )
    console.print(table)


def render_comments(profile: dict) -> None:
    posts_with_comments = [p for p in profile.get("posts", []) if p.get("comments")]
    if not posts_with_comments:
        return
    for post in posts_with_comments:
        table = Table(
            title=f"Comments on {post.get('shortcode')} ({len(post['comments'])} shown)",
            show_lines=False,
            header_style="bold magenta",
        )
        table.add_column("User", width=20, overflow="fold")
        table.add_column("Comment", overflow="fold")
        table.add_column("Likes", justify="right", width=6)
        for comment in post["comments"]:
            table.add_row(
                comment.get("username") or "—",
                (comment.get("text") or "").strip() or "[dim](empty)[/dim]",
                _fmt(comment.get("like_count")),
            )
        console.print(table)


def render_comment_note(profile: dict) -> None:
    total = sum(p.get("comment_count") or 0 for p in profile.get("posts", []))
    if not profile.get("posts"):
        return
    if profile.get("comments_available"):
        console.print(
            f"[dim]Comment counts shown per post (total across shown posts: {total}). "
            f"Real comment text fetched via the authenticated comments API.[/dim]"
        )
    else:
        console.print(
            f"[dim]Comment counts shown per post (total across shown posts: {total}). "
            f"Set IG_SESSIONID to also fetch the actual comment text.[/dim]"
        )


def _fmt(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


# ---------------------------------------------------------------------------
# Media download (images + videos from public posts)
# ---------------------------------------------------------------------------

def _safe_extension(url: str, kind: str) -> str:
    path = url.split("?", 1)[0]
    ext = os.path.splitext(path)[1].lower()
    if kind == "video":
        return ext if ext in (".mp4", ".mov") else ".mp4"
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
        # Instagram serves HEIC source files as JPEG over the display URL.
        return ".jpg" if ext == ".heic" else ext
    return ".jpg"


def download_file(url: str, dest: str) -> bool:
    return download_file_with_session(requests.Session(), url, dest)


def download_file_with_session(
    session: requests.Session,
    url: str,
    dest: str,
    headers: dict[str, str] | None = None,
) -> bool:
    try:
        request_headers = headers or {"user-agent": DESKTOP_UA, "accept": "*/*"}
        with session.get(url, headers=request_headers, stream=True, timeout=60) as response:
            if response.status_code != 200:
                return False
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type and not dest.endswith(".html"):
                return False
            with open(dest, "wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        handle.write(chunk)
        return True
    except (requests.RequestException, OSError):
        return False


def _download_fb_media_url(
    session: requests.Session,
    url: str,
    dest: str,
    auth_session: requests.Session | None = None,
) -> tuple[bool, str | None]:
    """Download Facebook media; lookaside URLs need Googlebot UA."""
    if _is_lookaside_url(url):
        headers = {**GOOGLEBOT_HEADERS, "Referer": "https://www.facebook.com/"}
        if download_file_with_session(session, url, dest, headers):
            return True, None
        if "media_id=" in url and "get_thumbnail" not in url:
            thumb_url = f"{url}&get_thumbnail=1" if "?" in url else f"{url}?get_thumbnail=1"
            if download_file_with_session(session, thumb_url, dest, headers):
                return True, None
        return False, None

    if download_file_with_session(session, url, dest):
        return True, None
    if auth_session and auth_session is not session:
        if download_file_with_session(auth_session, url, dest):
            return True, None
    return False, None


def _extension_from_content_type(content_type: str, fallback: str) -> str:
    content_type = (content_type or "").lower()
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "mp4" in content_type or "video" in content_type:
        return ".mp4"
    return fallback


def download_media(profile: dict, username: str) -> dict:
    """Download every image/video from the collected recent posts into
    ``<username>_media/``. Returns a small summary dict."""
    folder = f"{username}_media"
    os.makedirs(folder, exist_ok=True)

    images = videos = failed = 0
    for post_index, post in enumerate(profile.get("posts", []), start=1):
        shortcode = post.get("shortcode") or f"post{post_index}"
        media_items = post.get("media") or []
        multi = len(media_items) > 1
        for media_index, item in enumerate(media_items, start=1):
            url = item.get("url")
            kind = item.get("kind", "image")
            if not url:
                failed += 1
                continue
            suffix = f"_{media_index}" if multi else ""
            filename = f"{post_index:02d}_{shortcode}{suffix}{_safe_extension(url, kind)}"
            dest = os.path.join(folder, filename)
            if download_file(url, dest):
                item["local_path"] = os.path.abspath(dest)
                if kind == "video":
                    videos += 1
                else:
                    images += 1
            else:
                failed += 1
            time.sleep(0.2)

    return {
        "folder": os.path.abspath(folder),
        "images": images,
        "videos": videos,
        "failed": failed,
    }


def render_download_summary(summary: dict) -> None:
    if summary.get("blocked"):
        console.print(
            Panel(
                f"[red]{summary.get('error', 'Facebook blocked this request.')}[/red]\n\n"
                "No media was downloaded. Wait 10–30 minutes and try again,\n"
                "or set FB_C_USER + FB_XS cookies for authenticated access.",
                title="Download Blocked",
                border_style="red",
            )
        )
        return

    profile_pic = summary.get("profile_picture")
    extra = f"\n[bold]Profile Picture:[/bold] {profile_pic}" if profile_pic else ""
    similar_folder = summary.get("similar_profiles_folder")
    similar_line = (
        f"\n[bold]Similar Profiles Folder:[/bold] {similar_folder}"
        if similar_folder
        else ""
    )
    similar_details = ""
    for entry in summary.get("similar_profiles") or []:
        similar_details += (
            f"\n  • {entry.get('username')} — {entry.get('images', 0)} images"
            f" → {entry.get('folder')}"
        )
    console.print(
        Panel(
            f"[bold]Target Folder:[/bold] {summary['folder']}\n"
            f"[bold]Images:[/bold] {summary['images']}    "
            f"[bold]Videos:[/bold] {summary['videos']}    "
            f"[bold]Failed:[/bold] {summary['failed']}"
            f"{similar_line}"
            f"{similar_details}"
            f"{extra}",
            title="Downloaded Media",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def build_instagram_json_payload(profile: dict, *, include_similar: bool = False) -> dict:
    profile = _sanitize_instagram_profile(profile)
    bio = profile.get("biography") or ""
    username = profile.get("username") or ""
    profile_url = f"https://www.instagram.com/{username}/" if username else ""
    profile_pic = profile.get("profile_pic_url")
    if _is_instagram_branding_url(profile_pic):
        profile_pic = None

    posts = []
    for post in profile.get("posts", []):
        media_items = []
        for item in post.get("media") or []:
            media_entry = dict(item)
            url = media_entry.get("url") or media_entry.get("thumbnail")
            if url:
                media_entry["live_url"] = url
                media_entry.setdefault("display_url", url)
                media_entry.setdefault("thumbnail", url)
            media_items.append(media_entry)

        entry = {
            "shortcode": post.get("shortcode"),
            "url": post.get("url"),
            "live_url": post.get("url"),
            "type": post.get("type"),
            "is_video": post.get("is_video", False),
            "timestamp": post.get("timestamp"),
            "like_count": post.get("like_count"),
            "comment_count": post.get("comment_count"),
            "caption": post.get("caption") or "",
            "hashtags": post.get("hashtags") or [],
            "mentions": post.get("mentions") or [],
            "display_url": post.get("display_url"),
            "display_live_url": post.get("display_url"),
            "media": media_items,
            "comments": post.get("comments") or [],
        }
        if post.get("is_video") or post.get("type") in ("Reel", "Video"):
            entry["video"] = {
                "view_count": post.get("video_view_count"),
                "duration_seconds": post.get("video_duration"),
                "video_url": post.get("video_url"),
                "video_live_url": post.get("video_url"),
            }
        posts.append(entry)

    reels = [p for p in posts if p.get("type") in ("Reel", "Video") or p.get("is_video")]
    photo_posts = [p for p in posts if p not in reels]
    is_private = profile.get("is_private", False)
    has_session = bool(profile.get("comments_available"))

    payload = {
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "platform": "instagram",
        "source": profile.get("source"),
        "authenticated": has_session,
        "links": {
            "profile": profile_url,
            "profile_picture": profile_pic,
            "posts": f"{profile_url}posts/" if profile_url else None,
            "reels": f"{profile_url}reels/" if profile_url else None,
            "embed": f"{profile_url}embed/" if profile_url else None,
        },
        "profile": {
            "username": username,
            "full_name": profile.get("full_name") or "",
            "id": profile.get("id"),
            "biography": bio,
            "bio_hashtags": extract_hashtags(bio),
            "bio_mentions": extract_mentions(bio),
            "category": profile.get("category"),
            "external_url": profile.get("external_url"),
            "is_verified": profile.get("is_verified", False),
            "is_private": is_private,
            "is_business": profile.get("is_business", False),
            "follower_count": profile.get("follower_count"),
            "following_count": profile.get("following_count"),
            "media_count": profile.get("media_count"),
            "profile_url": profile_url,
            "profile_pic_url": profile_pic,
        },
        "stats": {
            "recent_posts_collected": len(photo_posts),
            "reels_collected": len(reels),
            "total_comment_count_recent": sum(p.get("comment_count") or 0 for p in posts),
            "total_like_count_recent": sum(p.get("like_count") or 0 for p in posts),
        },
        "recent_posts": photo_posts,
        "reels": reels,
        "data_availability": {
            "is_private": is_private,
            "available": {
                "profile_name": bool(profile.get("full_name")),
                "follower_count": profile.get("follower_count") is not None,
                "profile_picture": bool(profile_pic),
                "recent_posts": len(photo_posts) > 0,
                "reels": len(reels) > 0,
                "biography": bool(bio),
                "comment_text": has_session,
            },
            "not_available": {
                "posts": is_private and len(photo_posts) == 0 and len(reels) == 0,
                "biography": not bio and not has_session,
                "comment_text": not has_session,
            },
        },
        "notes": {
            "comment_text": None
            if has_session
            else "Comment text requires IG_SESSIONID env var; only counts are shown.",
            "biography": None
            if bio
            else "Bio may be unavailable without IG_SESSIONID for some accounts.",
            "session_help": (
                "Set IG_SESSIONID to unlock bio and comment text."
                if not has_session
                else None
            ),
        },
    }
    api_response = profile.get("instagram_api_response")
    if api_response:
        payload["api_response"] = api_response

    has_media = len(photo_posts) > 0 or len(reels) > 0
    if include_similar:
        seed = profile.get("seed_username") or username
        payload["similar_profiles"] = build_similar_username_profiles(
            seed,
            platform="instagram",
            fast=True,
            limit=6,
            exclude=username,
            verify_exists=True,
            enrich=True,
        )
    if profile.get("scrape_limited") and not has_media:
        payload["scrape_limited"] = True
        payload["notes"]["media_preview"] = (
            "Direct image URLs are limited for this account from the server. "
            "Posts and profile are shown below via Instagram embed (same as viewing on instagram.com)."
        )
    return payload


def _facebook_data_availability(profile: dict) -> dict:
    personal = profile.get("personal_details") or {}
    locked = "locked" in personal.get("Profile Status", "").lower()
    friend_count = profile.get("friend_count")
    friends = profile.get("friends") or []
    timeline = profile.get("timeline_posts") or []
    photos = profile.get("photos") or []
    reel_items = profile.get("reels") or []
    edu_keys = ("Work", "University", "High School", "College", "Education")
    has_real_education = any(
        personal.get(k)
        and "no " not in personal.get(k, "").lower()
        and "to show" not in personal.get(k, "").lower()
        for k in edu_keys
    )
    has_reel_links = any(r.get("is_reel") for r in reel_items)

    return {
        "profile_locked": locked,
        "authenticated": profile.get("authenticated", False),
        "available_without_login": {
            "full_name": bool(profile.get("full_name")),
            "username": bool(profile.get("username")),
            "numeric_id": bool(profile.get("id")),
            "profile_picture": bool(profile.get("profile_pic_url")),
            "profile_status": bool(personal.get("Profile Status")),
            "personal_details_sections": bool(personal),
            "gender": "Gender" in personal,
            "work_education_section_labels": any(k in personal for k in edu_keys),
            "work_education_values": has_real_education,
            "lookaside_media_urls": any("lookaside" in (p.get("url") or "") for p in photos),
            "scontent_photos": any("scontent" in (p.get("url") or "") for p in photos),
            "investigation_intel": bool(profile.get("investigation")),
            "wayback_check": bool(profile.get("wayback")),
        },
        "not_available_without_login": {
            "friend_count": friend_count is None and not friends,
            "friends_list": len(friends) == 0,
            "timeline_posts": len(timeline) == 0,
            "post_photo_albums": locked or len([p for p in photos if p.get("type") not in ("profile_picture",)]) == 0,
            "reels_feed": not has_reel_links,
            "work_education_actual_values": not has_real_education,
            "contact_info": not any(
                k.lower() in str(personal).lower()
                for k in ("email", "phone", "contact", "website")
            ),
            "bio": not bool(profile.get("biography")),
        },
        "counts": {
            "photos_found": len(photos),
            "videos_found": len(profile.get("videos") or []),
            "reels_found": len(profile.get("reels") or []),
            "timeline_posts_found": len(timeline),
            "friends_found": len(friends),
            "friend_count": friend_count,
        },
        "locked_profile_note": (
            "Profile is locked. CID lookaside_probe crawls Googlebot-visible subpages and similar-named "
            "profiles, then verifies downloadable media via lookaside.fbsbx.com. Friends, timeline, and "
            "full albums still require FB_C_USER+FB_XS session or Meta LERS."
            if locked
            else None
        ),
        "cid_techniques": {
            "googlebot_subpages": True,
            "lookaside_media_probe": bool(profile.get("lookaside_probe")),
            "similar_profile_crawl": bool(profile.get("similar_profiles")),
            "media_cache_file": _facebook_media_cache_path(profile.get("username") or ""),
        },
    }


def build_json_payload(profile: dict) -> dict:
    """Return a clean, ordered, JSON-serializable view of the scraped data."""
    if profile.get("platform") == "facebook":
        return build_facebook_json_payload(profile)
    return build_instagram_json_payload(profile)


def build_minimal_facebook_profile(
    slug: str,
    *,
    seed_username: str | None = None,
    full_name: str | None = None,
    profile_pic_url: str | None = None,
    profile_id: str | None = None,
) -> dict:
    """Stub Facebook profile when embed fetch is blocked but slug is known."""
    profile_url = _facebook_profile_url_from_slug(slug)
    return {
        "platform": "facebook",
        "username": slug,
        "full_name": full_name or slug,
        "biography": "",
        "profile_url": profile_url,
        "profile_pic_url": profile_pic_url,
        "id": profile_id,
        "photos": [],
        "videos": [],
        "reels": [],
        "timeline_posts": [],
        "friends": [],
        "personal_details": {},
        "source": "facebook_username_guess",
        "authenticated": False,
        "embed_only": True,
        "seed_username": seed_username,
        "friends_url": f"{profile_url.rstrip('/')}/friends",
        "photos_url": f"{profile_url.rstrip('/')}/photos",
        "reels_url": f"{profile_url.rstrip('/')}/reels",
    }


def build_facebook_json_payload(profile: dict) -> dict:
    bio = profile.get("biography") or ""
    profile_url = profile.get("profile_url") or ""
    investigation = profile.get("investigation") or {}
    identifiers = investigation.get("identifiers") or {}
    friend_count = profile.get("friend_count")
    friends = profile.get("friends") or []
    if friend_count is None and friends:
        friend_count = len(friends)
    target_slug = profile.get("username") or ""

    photos = []
    target_key = (target_slug or "").lower()
    for photo in profile.get("photos") or []:
        item = dict(photo)
        if item.get("url"):
            item["live_url"] = item["url"]
        owner = item.get("owner_username") or ""
        source = str(item.get("source") or "")
        # Keep proven target media only; never re-attribute unknown/similar photos.
        if item.get("type") == "profile_picture" or source in {
            "photos_page", "photos_box", "photos_by", "facebook_graph_picture", "profile_picture",
        }:
            owner = owner or target_slug
            item["is_target_profile"] = True
        elif item.get("is_target_profile") is True and (not owner or owner.lower() == target_key):
            owner = owner or target_slug
            item["is_target_profile"] = True
        elif owner and owner.lower() == target_key and item.get("is_target_profile") is not False:
            item["is_target_profile"] = True
        else:
            item["is_target_profile"] = False
        item["owner_username"] = owner
        if owner:
            item["profile_url"] = item.get("profile_url") or _facebook_profile_url_from_slug(owner)
        if item.get("is_target_profile") and not item.get("album_url") and target_slug:
            item["album_url"] = f"https://www.facebook.com/{target_slug}/photos"
        photos.append(item)

    _own_sources = {"photos_page", "photos_box", "photos_by", "facebook_graph_picture", "profile_picture"}
    target_photos = [
        photo for photo in photos
        if photo.get("is_target_profile") is True
        and (
            photo.get("type") == "profile_picture"
            or photo.get("source") in _own_sources
        )
    ]
    # Public payload: only the searched profile's own media (no similar-people thumbnails).
    photos = [
        photo for photo in photos
        if photo.get("is_target_profile") is True
        and (
            photo.get("type") == "profile_picture"
            or photo.get("source") in _own_sources
        )
    ]
    similar_profiles = profile.get("similar_profiles") or []

    videos = []
    for video in profile.get("videos") or []:
        item = dict(video)
        if item.get("url"):
            item["live_url"] = item["url"]
            item["profile_url"] = profile_url
        if item.get("thumbnail"):
            item["thumbnail_live_url"] = item["thumbnail"]
        videos.append(item)

    reels = []
    for reel in profile.get("reels") or []:
        item = dict(reel)
        if item.get("url"):
            item["live_url"] = item["url"]
            item["profile_url"] = profile_url
        reels.append(item)

    target_profile = {
        "username": profile.get("username"),
        "full_name": profile.get("full_name") or "",
        "profile_type": profile.get("profile_type"),
        "id": profile.get("id"),
        "biography": bio,
        "gender": (profile.get("personal_details") or {}).get("Gender"),
        "profile_status": (profile.get("personal_details") or {}).get("Profile Status"),
        "like_count": profile.get("like_count"),
        "talking_about_count": profile.get("talking_about_count"),
        "friend_count": friend_count,
        "friends_label": profile.get("friends_label"),
        "friend_count_available": friend_count is not None,
        "profile_url": profile_url,
        "profile_pic_url": profile.get("profile_pic_url"),
        "profile_picture_local": (profile.get("download_summary") or {}).get("profile_picture"),
        "personal_details": profile.get("personal_details") or {},
        "photos": target_photos,
        "videos": videos,
        "reels": reels,
        "timeline_posts": profile.get("timeline_posts") or [],
        "friends": friends,
        "links": {
            "profile": profile_url,
            "profile_picture": profile.get("profile_pic_url"),
            "friends": profile.get("friends_url") or f"{profile_url.rstrip('/')}/friends",
            "photos": profile.get("photos_url") or f"{profile_url.rstrip('/')}/photos",
            "reels": profile.get("reels_url") or f"{profile_url.rstrip('/')}/reels",
            "profile_id": identifiers.get("profile_id_url"),
        },
    }

    return {
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "platform": "facebook",
        "source": profile.get("source"),
        "embed_only": bool(profile.get("embed_only")),
        "searched_username": profile.get("seed_username") or profile.get("searched_username"),
        "data_sources": profile.get("data_sources") or [],
        "authenticated": profile.get("authenticated", False),
        "target_profile": target_profile,
        "similar_profiles": similar_profiles,
        "links": {
            "profile": profile_url,
            "profile_picture": profile.get("profile_pic_url"),
            "friends": profile.get("friends_url") or f"{profile_url.rstrip('/')}/friends",
            "photos": profile.get("photos_url") or f"{profile_url.rstrip('/')}/photos",
            "reels": profile.get("reels_url") or f"{profile_url.rstrip('/')}/reels",
            "profile_id": identifiers.get("profile_id_url"),
            "meta_lers": (investigation.get("official_channels") or {}).get(
                "meta_lers_portal", "https://www.facebook.com/records"
            ),
            "instagram_guess": (investigation.get("cross_platform") or {}).get("instagram_url"),
        },
        "profile": target_profile,
        "personal_details": profile.get("personal_details") or {},
        "friends": friends,
        "photos": photos,
        "videos": videos,
        "reels": reels,
        "timeline_posts": profile.get("timeline_posts") or [],
        "auth_sources": profile.get("auth_sources") or [],
        "download_summary": profile.get("download_summary") or {},
        "wayback": profile.get("wayback") or {},
        "investigation": investigation,
        "cross_platform_instagram": profile.get("cross_platform_instagram"),
        "data_availability": _facebook_data_availability(profile),
        "notes": {
            "public_limits": profile.get("public_limits"),
            "login_required_for": profile.get("login_required_for"),
            "friend_count_note": (
                None
                if friend_count is not None
                else (
                    "Friend count hidden for locked/private profiles without login. "
                    "Set FB_C_USER + FB_XS or use Meta LERS."
                    if profile.get("personal_details", {}).get("Profile Status", "").lower().find("locked") >= 0
                    else "Friend count not exposed in public embed HTML for this profile."
                )
            ),
            "embed_info": (
                "Facebook public data uses mobile + plugin + crawler + googlebot embeds. "
                "Friends/photos/timeline need FB session or Meta LERS legal request."
            ),
            "embed_only": (
                "Server could not fetch Facebook media; profile is shown via in-browser Facebook embed."
                if profile.get("embed_only")
                else None
            ),
            "cid_workflow": {
                "step_1": "Collect public embed data (this tool, no login).",
                "step_2": "Use investigator FB session for visible friends/photos/about.",
                "step_3": "Submit preservation + records request at https://www.facebook.com/records",
                "step_4": "Cross-check Instagram and Wayback snapshots.",
            },
            "cookie_help": (
                "Export cookies.txt from browser (Get cookies.txt LOCALLY extension) "
                "and set FB_COOKIES_FILE, or set FB_C_USER + FB_XS."
                if not profile.get("authenticated")
                else None
            ),
        },
    }


def instagram_to_json(profile: dict) -> str:
    return json.dumps(build_instagram_json_payload(profile), ensure_ascii=False, indent=2)


def facebook_to_json(profile: dict) -> str:
    return json.dumps(build_facebook_json_payload(profile), ensure_ascii=False, indent=2)


def to_json(profile: dict) -> str:
    return json.dumps(build_json_payload(profile), ensure_ascii=False, indent=2)


def save_json(profile: dict, username: str) -> str:
    base = slug_to_filename(username)
    if profile.get("platform") == "facebook":
        path = f"{base}_facebook.json"
        payload = build_facebook_json_payload(profile)
    else:
        path = f"{base}.json"
        payload = build_instagram_json_payload(profile)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return os.path.abspath(path)


def run_instagram(username: str) -> None:
    sessionid = instagram_sessionid()

    try:
        with console.status("[cyan]Fetching Instagram profile data...[/cyan]"):
            profile = collect_profile(username, sessionid)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        return
    except requests.RequestException:
        console.print(
            "[red]Network error while contacting Instagram. "
            "Check your connection and try again.[/red]"
        )
        return
    except RuntimeError as error:
        console.print(f"[red]{error}[/red]")
        return

    output_mode = os.environ.get("IG_OUTPUT", "").strip().lower()
    want_download = os.environ.get("IG_DOWNLOAD", "").strip().lower() in ("1", "true", "yes", "on")

    summary = None
    if want_download:
        with console.status("[cyan]Downloading post media (images + videos)...[/cyan]"):
            summary = download_media(profile, profile.get("username") or username)

    if output_mode == "json":
        print(to_json(profile))
    else:
        render_profile(profile)
        render_posts(profile)
        render_reels(profile)
        render_comments(profile)
        render_comment_note(profile)
        if summary:
            render_download_summary(summary)
        else:
            console.print(
                "[dim]Tip: set IG_DOWNLOAD=1 to also download the post images and videos.[/dim]"
            )

    try:
        path = save_json(profile, profile.get("username") or username)
        if output_mode != "json":
            console.print(f"[green]Saved JSON output to[/green] {path}")
    except OSError as error:
        console.print(f"[yellow]Could not write JSON file: {error}[/yellow]")


def run_facebook(slug: str, *, json_only: bool = False, download: bool | None = None) -> dict | None:
    want_download = download
    if want_download is None:
        want_download = os.environ.get("IG_DOWNLOAD", "").strip().lower() in ("1", "true", "yes", "on")

    try:
        with console.status("[cyan]Fetching Facebook public embed data...[/cyan]"):
            if want_download:
                profile = collect_facebook_profile(slug)
            else:
                profile = fetch_facebook_profile(slug)
                profile.setdefault("friends", [])
                profile.setdefault("photos", [])
                profile.setdefault("videos", [])
                profile.setdefault("reels", [])
                profile.setdefault("personal_details", {})
                profile["authenticated"] = False
                profile["investigation"] = build_investigation_intel(profile)
                profile["wayback"] = fetch_wayback_intel(
                    profile.get("profile_url") or f"https://www.facebook.com/{slug}"
                )
                session = make_facebook_session()
                if session:
                    try:
                        profile = enrich_facebook_with_session(profile, session)
                    except requests.RequestException:
                        pass
    except ValueError as error:
        if json_only:
            raise
        console.print(f"[red]{error}[/red]")
        return None
    except requests.RequestException:
        if json_only:
            raise
        console.print(
            "[red]Network error while contacting Facebook. "
            "Check your connection and try again.[/red]"
        )
        return None

    if json_only:
        print(facebook_to_json(profile))
        return profile

    render_facebook_profile(profile)

    try:
        path = save_json(profile, profile.get("username") or slug)
        console.print(f"[green]Saved JSON output to[/green] {path}")
    except OSError as error:
        console.print(f"[yellow]Could not write JSON file: {error}[/yellow]")

    return profile


def profile_data():
    show_banner()
    platform_raw = input("Enter platform (instagram / facebook): ").strip()
    platform = parse_platform(platform_raw)
    if not platform:
        console.print("[red]Please enter 'instagram' or 'facebook'.[/red]")
        return

    raw_value = input("Enter your username or profile link: ").strip()
    if platform == "instagram":
        username = parse_username(raw_value)
        if not username:
            console.print("[red]Please enter a valid Instagram username.[/red]")
            return
        if " " in username and "instagram.com" not in raw_value:
            username = username.replace(" ", "").lower()
        run_instagram(username)
        return

    slug = parse_facebook_slug(raw_value)
    if not slug:
        console.print("[red]Please enter a valid Facebook username or profile link.[/red]")
        return
    run_facebook(slug)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Social Media Public Profile Scraper (Instagram & Facebook)",
    )
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Start JSON API server for Postman/testing")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8080)

    for name in ("facebook", "fb"):
        fb_parser = subparsers.add_parser(name, help="Scrape a Facebook profile")
        fb_parser.add_argument("username", help="Facebook username, slug, or profile URL")
        fb_parser.add_argument("--json", action="store_true", help="Print JSON only (live URLs included)")
        fb_parser.add_argument("--download", action="store_true", help="Download photos/videos to disk")

    for name in ("instagram", "ig"):
        ig_parser = subparsers.add_parser(name, help="Scrape an Instagram profile")
        ig_parser.add_argument("username", help="Instagram username or profile URL")
        ig_parser.add_argument("--json", action="store_true", help="Print JSON only")

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Use interactive prompts instead of command-line arguments",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        from api import run_api_server

        run_api_server(host=args.host, port=args.port)
        return

    if getattr(args, "interactive", False) or not args.command:
        profile_data()
        return

    if args.command in ("facebook", "fb"):
        slug = parse_facebook_slug(args.username)
        if not slug:
            parser.error("Invalid Facebook username or profile link.")
        run_facebook(slug, json_only=args.json, download=args.download)
        return

    if args.command in ("instagram", "ig"):
        username = parse_username(args.username)
        if not username:
            parser.error("Invalid Instagram username.")
        if " " in username and "instagram.com" not in args.username:
            username = username.replace(" ", "").lower()
        if args.json:
            os.environ["IG_OUTPUT"] = "json"
        run_instagram(username)
        return


if __name__ == "__main__":
    main()
