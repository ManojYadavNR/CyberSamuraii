import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Removed: import common
# Removed: common.load_env_file()

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

MAX_REEL_DETAIL_FETCHES = 6
DETAIL_FETCH_DELAY = 0.6
MAX_COMMENT_POSTS = 6
COMMENTS_PER_POST = 15

BROWSER_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": DESKTOP_UA,
}

def parse_username(value: str) -> str:
    value = value.strip().strip("/")
    match = re.search(r"instagram\.com/([A-Za-z0-9._]+)", value)
    if match:
        return match.group(1)
    return value.lstrip("@")

def extract_json_string(text: str, key: str) -> str | None:
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
        value = value.replace(",", "")
        if value and value[-1] in "KMB":
            return None
        try:
            return int(value)
        except ValueError:
            return None

    return {
        "followers": to_int(match.group(1)),
        "following": to_int(match.group(2)),
        "posts": to_int(match.group(3)),
    }

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
    if node.get("is_video") and node.get("video_url"):
        return {"kind": "video", "url": node.get("video_url"), "thumbnail": node.get("display_url")}
    return {"kind": "image", "url": node.get("display_url"), "thumbnail": node.get("display_url")}

def collect_media(node: dict) -> list[dict]:
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
    }

def make_session(sessionid: str | None) -> requests.Session:
    session = requests.Session()
    if sessionid:
        session.cookies.set("sessionid", sessionid, domain=".instagram.com")
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

def fetch_web_profile_info(session: requests.Session, username: str) -> dict | None:
    try:
        response = session.get(
            f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
            headers=_api_headers(session, f"https://www.instagram.com/{username}/"),
            timeout=30,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json().get("data", {}).get("user")
    except ValueError:
        return None

def fetch_comments(session: requests.Session, media_id: str, shortcode: str, limit: int) -> list[dict]:
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
    response = requests.get(
        f"https://www.instagram.com/{username}/embed/",
        headers={"user-agent": SIMPLE_UA, "accept-language": "en-US,en;q=0.9"},
        timeout=30,
    )
    if response.status_code == 404:
        raise ValueError(f"Profile '{username}' was not found.")
    response.raise_for_status()

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

    if profile["follower_count"] is None:
        raise RuntimeError(
            "Could not read profile data from Instagram. "
            "The account may be private, suspended, or temporarily blocked."
        )

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
    return profile

def fetch_post_details(shortcode: str) -> dict | None:
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
    return profile

def enrich_reels(profile: dict) -> None:
    fetched = 0
    for post in profile.get("posts", []):
        if fetched >= MAX_REEL_DETAIL_FETCHES:
            break
        needs_detail = post.get("is_video") or post.get("type") in ("Video", "Reel")
        if not needs_detail or post.get("video_url"):
            continue
        if not post.get("shortcode"):
            continue
        details = fetch_post_details(post["shortcode"])
        fetched += 1
        time.sleep(DETAIL_FETCH_DELAY)
        if not details:
            continue
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

def enrich_comments(session: requests.Session, profile: dict) -> None:
    fetched = 0
    for post in profile.get("posts", []):
        if fetched >= MAX_COMMENT_POSTS:
            break
        if not post.get("comment_count"):
            post["comments"] = []
            continue
        comments = fetch_comments(
            session, post.get("media_id"), post.get("shortcode"), COMMENTS_PER_POST
        )
        post["comments"] = comments
        fetched += 1
        time.sleep(DETAIL_FETCH_DELAY)

def collect_profile(username: str, sessionid: str | None) -> dict:
    session = make_session(sessionid)
    user = fetch_web_profile_info(session, username)
    if user:
        profile = profile_from_web_api(user, username)
    else:
        profile = fetch_profile_from_embed(username)
        profile = enrich_from_profile_page(profile, username)
    enrich_reels(profile)
    if sessionid:
        profile["comments_available"] = True
        enrich_comments(session, profile)
    else:
        profile["comments_available"] = False
    return profile

def instagram_sessionid() -> str | None:
    return os.environ.get("IG_SESSIONID")

def build_json_payload(profile: dict) -> dict:
    bio = profile.get("biography") or ""
    posts = []
    for post in profile.get("posts", []):
        posts.append(
            {
                "shortcode": post.get("shortcode"),
                "url": post.get("url"),
                "type": post.get("type"),
                "is_video": post.get("is_video", False),
                "timestamp": post.get("timestamp"),
                "like_count": post.get("like_count"),
                "comment_count": post.get("comment_count"),
                "caption": post.get("caption") or "",
                "hashtags": post.get("hashtags") or [],
                "mentions": post.get("mentions") or [],
                "video": {
                    "view_count": post.get("video_view_count"),
                    "duration_seconds": post.get("video_duration"),
                    "video_url": post.get("video_url"),
                }
                if (post.get("is_video") or post.get("type") in ("Reel", "Video"))
                else None,
                "display_url": post.get("display_url"),
                "media": post.get("media") or [],
                "comments": post.get("comments") or [],
            }
        )

    reels = [p for p in posts if p["type"] in ("Reel", "Video") or p["is_video"]]

    return {
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "source": profile.get("source"),
        "profile": {
            "username": profile.get("username"),
            "full_name": profile.get("full_name") or "",
            "id": profile.get("id"),
            "biography": bio,
            "bio_hashtags": extract_hashtags(bio),
            "bio_mentions": extract_mentions(bio),
            "category": profile.get("category"),
            "external_url": profile.get("external_url"),
            "is_verified": profile.get("is_verified", False),
            "is_private": profile.get("is_private", False),
            "is_business": profile.get("is_business", False),
            "follower_count": profile.get("follower_count"),
            "following_count": profile.get("following_count"),
            "media_count": profile.get("media_count"),
            "profile_pic_url": profile.get("profile_pic_url"),
        },
        "stats": {
            "recent_posts_collected": len(posts),
            "reels_collected": len(reels),
            "total_comment_count_recent": sum(p.get("comment_count") or 0 for p in posts),
            "total_like_count_recent": sum(p.get("like_count") or 0 for p in posts),
        },
        "recent_posts": posts,
        "reels": reels,
        "notes": {
            "comment_text": None
            if profile.get("comments_available")
            else "Comment text requires a logged-in session (set IG_SESSIONID); only counts are shown.",
            "biography": None
            if bio
            else "Bio is unavailable without a logged-in session (set IG_SESSIONID).",
        },
    }

# We also implement mock functions for the Samurai API bridge so it doesn't crash.
def build_instagram_json_payload(ig_profile: dict | None) -> dict | None:
    if not ig_profile: return None
    return build_json_payload(ig_profile)

def find_facebook_from_instagram_profile(ig_profile: dict) -> dict:
    return {}

def find_facebook_from_instagram(username: str) -> dict:
    return {}

def build_facebook_json_payload(fb_profile: dict | None) -> dict | None:
    return None
