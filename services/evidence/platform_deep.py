"""Generic public page extraction — deep profile scrape for any verified URL."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from services.discovery.attribution import account_handle_matches_seed, context_references_seed, url_references_seed
from services.discovery.validators import (
    extract_emails_from_text,
    is_displayable_media_url,
    is_generic_platform_bio,
    is_image_url,
    is_junk_profile_url,
    is_plausible_profile_photo,
    normalize_domain,
)
from services.evidence.profile_verifier import is_profile_page_available
from services.google_dorking.filters import handle_from_profile_url, sanitize_org_label

FETCH_TIMEOUT = 16.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
OG_TAG_RE = re.compile(
    r'<meta\s+(?:property|name)=["\'](og:[^"\']+|description|twitter:image|twitter:description)["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
JSON_BLOB_RE = re.compile(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
JSON_LD_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
JSON_TEXT_FIELD_RE = re.compile(
    r'"(?:biography|bio|description|about|aboutMe|displayName|full_name|fullName|name|location|company|organization|website|blog|email|mail)":\s*"((?:\\.|[^"\\])*)"',
    re.IGNORECASE,
)
JSON_COUNT_RE = re.compile(
    r'"(?:followers?|following|subscriber?s?|posts?|videos?|public_repos?|repo_count)":\s*(?:")?(\d[\d,]*)',
    re.IGNORECASE,
)
JSON_CAPTION_RE = re.compile(r'"(?:text|caption|content|message|highlight)":"((?:\\.|[^"\\])*)"')
JSON_TIMESTAMP_RE = re.compile(
    r'"(?:created_at|published_at|timestamp|taken_at|created_time|date_time|upload_date|datetime)":\s*"?([^",}\]]+)"?',
    re.IGNORECASE,
)
JSON_NAME_RE = re.compile(r'"(?:full_name|repo_name|project_name|name)":"((?:\\.|[^"\\])*)"')
POST_BODY_KEYS = frozenset({"text", "caption", "content", "message", "body", "title", "snippet"})
TIME_KEYS = frozenset({
    "created_at", "published_at", "timestamp", "taken_at", "datetime", "created_time",
    "upload_date", "date_time", "time", "date",
})
VISIBLE_STAT_RE = re.compile(
    r"([\d][\d,]*)\s+(followers?|following|subscribers?|posts?|videos?|public repos?|repositories)",
    re.IGNORECASE,
)
MAILTO_RE = re.compile(r'href=["\']mailto:([^"\'?]+)', re.IGNORECASE)
VIDEO_URL_RE = re.compile(
    r'https?://(?:[\w.-]+\.)?(?:'
    r'youtube\.com/(?:watch\?v=|shorts/|embed/|live/|channel/|@)|youtu\.be/|'
    r'vimeo\.com/|dailymotion\.com/video|twitch\.tv/(?:videos/|[^/]+$)|'
    r'tiktok\.com/@[^/]+/video/|instagram\.com/(?:p|reel|tv)/|'
    r'facebook\.com/[^/]+/videos/|rumble\.com/[^"\']+'
    r')[^\s"\'<>]*',
    re.IGNORECASE,
)
OG_VIDEO_KEYS = ("og:video", "og:video:secure_url", "og:video:url", "twitter:player", "twitter:player:stream")
TITLE_SPLIT_RE = re.compile(r"\s*[-–|]\s*")
SCHOOL_RE = re.compile(
    r"\b[\w][\w\s&'.-]{1,48}(?:University|College|Institute|School|Academy|Polytechnic)\b",
    re.IGNORECASE,
)


def account_handles_align(expected: str, actual: str) -> bool:
    a = re.sub(r"[^\w]", "", expected.lower())
    b = re.sub(r"[^\w]", "", actual.lower())
    if not a or not b:
        return True
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return shorter in longer and len(shorter) >= max(4, int(len(longer) * 0.72))


def _profile_matches_expected(path_handle: str | None, expected_handle: str | None, url: str) -> bool:
    if not expected_handle:
        return True
    if not path_handle:
        return url_references_seed(url, expected_handle)
    if account_handle_matches_seed(path_handle, expected_handle, url):
        return True
    return account_handles_align(expected_handle, path_handle)


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().replace("www.", "")


def _parse_og_tags(html: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for match in OG_TAG_RE.finditer(html):
        key = match.group(1).lower()
        val = match.group(2).strip()
        if val and key not in tags:
            tags[key] = val
    return tags


def _decode_json_string(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw.replace("\\n", "\n").replace('\\"', '"')


def _normalize_timestamp(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        ts = float(val)
        if ts > 1e12:
            ts /= 1000.0
        if ts > 1e9:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    text = str(val).strip().strip('"')
    return text or None


def _append_post_entry(payload: dict[str, Any], text: str, timestamp: str | None = None) -> None:
    cleaned = " ".join(str(text).split()).strip()
    if len(cleaned) < 4:
        return
    posts: list[Any] = payload.setdefault("recent_posts", [])
    entry: str | dict[str, Any]
    if timestamp:
        entry = {"text": cleaned, "created_at": timestamp}
        times: list[str] = payload.setdefault("posting_times", [])
        if timestamp not in times:
            times.append(timestamp)
    else:
        entry = cleaned
    if entry not in posts:
        posts.append(entry)
    highlights: list[str] = payload.setdefault("highlights", [])
    if cleaned not in highlights and len(highlights) < 8:
        highlights.append(cleaned)


def _extract_post_node(data: dict[str, Any], payload: dict[str, Any]) -> None:
    text_val: str | None = None
    time_val: str | None = None
    for key, val in data.items():
        low = str(key).lower()
        if low in POST_BODY_KEYS and isinstance(val, str) and val.strip():
            if not text_val or len(val.strip()) > len(text_val):
                text_val = val.strip()
        if low in TIME_KEYS:
            normalized = _normalize_timestamp(val)
            if normalized:
                time_val = normalized
    if text_val:
        _append_post_entry(payload, text_val, time_val)


def _payload_base(url: str, *, source: str, platform: str) -> dict[str, Any]:
    return {"url": url, "platform": platform, "enrichment_source": source, "verified": True}


def _looks_like_image_url(url: str) -> bool:
    return is_plausible_profile_photo(url) or is_displayable_media_url(url)


async def _fetch_html(url: str, *, accept_json: bool = False) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/html;q=0.9,*/*;q=0.8" if accept_json else "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return ""
        return resp.text


def _flatten_json_profile(data: Any, payload: dict[str, Any], *, depth: int = 0) -> None:
    if depth > 4:
        return
    if isinstance(data, list):
        for item in data[:20]:
            _flatten_json_profile(item, payload, depth=depth + 1)
        return
    if not isinstance(data, dict):
        return

    _extract_post_node(data, payload)

    mapping = {
        "login": "username", "username": "username", "handle": "username",
        "name": "display_name", "displayname": "display_name", "full_name": "display_name",
        "bio": "bio", "description": "bio", "about": "bio", "summary": "bio",
        "location": "location", "company": "organization", "organization": "organization",
        "blog": "website", "website": "website", "email": "email",
        "avatar_url": "avatar_url", "image": "avatar_url", "picture": "avatar_url",
        "profile_pic_url": "avatar_url", "profile_image": "avatar_url",
    }
    for key, val in data.items():
        low = str(key).lower()
        target = mapping.get(low)
        if target and isinstance(val, str) and val.strip():
            payload.setdefault(target, val.strip())
        if low in ("followers", "following", "public_repos", "subscribers", "posts", "videos"):
            payload.setdefault("public_metadata", {})[low] = val
        if low in ("repos", "repositories", "projects") and isinstance(val, list):
            names = []
            for item in val:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("full_name")
                    if isinstance(name, str):
                        names.append(name.split("/")[-1])
            if names:
                payload["projects"] = list(dict.fromkeys([*payload.get("projects", []), *names[:20]]))

    for child in data.values():
        if isinstance(child, (dict, list)):
            _flatten_json_profile(child, payload, depth=depth + 1)


def _schema_person_fields(data: dict[str, Any], payload: dict[str, Any]) -> None:
    for key, target in (
        ("name", "display_name"),
        ("description", "bio"),
        ("jobTitle", "bio"),
        ("worksFor", "organization"),
        ("email", "email"),
        ("url", "website"),
    ):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            payload.setdefault(target, val.strip())
        elif isinstance(val, dict) and val.get("name"):
            payload.setdefault(target, str(val["name"]).strip())


def _parse_json_ld(html: str, payload: dict[str, Any]) -> None:
    for blob in JSON_LD_RE.findall(html):
        try:
            data = json.loads(blob.strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            payload.setdefault("public_metadata", {})["schema_org"] = item
            if item.get("@type") in ("Person", "ProfilePage", "Organization"):
                _schema_person_fields(item, payload)
            if isinstance(item.get("author"), dict):
                _schema_person_fields(item["author"], payload)


def _parse_embedded_json(html: str, payload: dict[str, Any]) -> None:
    field_map = {
        "biography": "bio", "bio": "bio", "description": "bio", "about": "bio", "aboutme": "bio",
        "displayname": "display_name", "full_name": "display_name", "fullname": "display_name",
        "name": "display_name", "location": "location", "company": "organization",
        "organization": "organization", "website": "website", "blog": "website",
        "email": "email", "mail": "email",
    }
    for match in JSON_TEXT_FIELD_RE.finditer(html):
        raw_key = match.group(0).split('"')[1].lower()
        val = _decode_json_string(match.group(1)).strip()
        if not val or len(val) < 2:
            continue
        target = field_map.get(raw_key.replace("_", ""), field_map.get(raw_key))
        if target:
            payload.setdefault(target, val)

    stats: dict[str, Any] = payload.setdefault("public_metadata", {})
    for match in JSON_COUNT_RE.finditer(html):
        key = match.group(0).split('"')[1].lower().rstrip("s")
        stats[key] = match.group(1).replace(",", "")

    captions: list[str] = []
    for cap in JSON_CAPTION_RE.findall(html):
        text = _decode_json_string(cap).strip()
        if text and len(text) > 8 and text not in captions:
            captions.append(text)
        if len(captions) >= 10:
            break
    if captions:
        for cap in captions:
            _append_post_entry(payload, cap)

    posting_times: list[str] = list(payload.get("posting_times") or [])
    for match in JSON_TIMESTAMP_RE.finditer(html):
        ts = _normalize_timestamp(match.group(1).strip())
        if ts and ts not in posting_times:
            posting_times.append(ts)
    if posting_times:
        payload["posting_times"] = posting_times[:24]

    projects: list[str] = list(payload.get("projects") or [])
    for match in JSON_NAME_RE.findall(html):
        name = _decode_json_string(match).strip()
        if name and len(name) >= 2 and name.lower() not in ("main", "master", "default"):
            projects.append(name)
        if len(projects) >= 20:
            break
    if projects:
        payload["projects"] = list(dict.fromkeys(projects))

    for blob in JSON_BLOB_RE.findall(html):
        try:
            data = json.loads(blob.strip())
        except json.JSONDecodeError:
            continue
        _flatten_json_profile(data, payload)


def _parse_visible_stats(text: str, payload: dict[str, Any]) -> None:
    stats = payload.setdefault("public_metadata", {})
    for match in VISIBLE_STAT_RE.finditer(text):
        count, label = match.group(1).replace(",", ""), match.group(2).lower().rstrip("s")
        key = "public_repos" if "repo" in label else label.rstrip("s")
        stats[key] = count


def _parse_title_fields(title: str, payload: dict[str, Any]) -> None:
    if not title:
        return
    parts = [p.strip() for p in TITLE_SPLIT_RE.split(title) if p.strip()]
    if parts:
        payload.setdefault("display_name", parts[0])
    if len(parts) > 1:
        org = sanitize_org_label(parts[1])
        if org:
            payload.setdefault("organization", org)
            payload.setdefault("bio", org)


def _extract_text_intelligence(html: str, payload: dict[str, Any], *, url: str = "", seed_query: str = "") -> None:
    text = html[:60000]
    if not seed_query or not context_references_seed(text, seed_query=seed_query):
        emails = extract_emails_from_text(text)
        for email in emails:
            if "email" not in payload:
                payload["email"] = email
            payload.setdefault("emails", []).append(email)
        for mailto in MAILTO_RE.findall(text):
            addr = mailto.strip().lower()
            if addr:
                payload.setdefault("emails", []).append(addr)
                payload.setdefault("email", addr)
        return

    for school in SCHOOL_RE.findall(text):
        cleaned = " ".join(school.split())
        if len(cleaned) > 4:
            payload.setdefault("schools", []).append(cleaned)
    from services.evidence.document_parser import _extract_event_labels
    for label in _extract_event_labels(text):
        if seed_query and not context_references_seed(label, seed_query=seed_query):
            continue
        payload.setdefault("achievements", []).append(label)

    emails = extract_emails_from_text(text)
    for email in emails:
        if "email" not in payload:
            payload["email"] = email
        payload.setdefault("emails", []).append(email)
    for mailto in MAILTO_RE.findall(text):
        addr = mailto.strip().lower()
        if addr:
            payload.setdefault("emails", []).append(addr)
            payload.setdefault("email", addr)


def _collect_videos(html: str, tags: dict[str, str], url: str, payload: dict[str, Any]) -> None:
    videos: list[str] = []
    for key in OG_VIDEO_KEYS:
        val = tags.get(key)
        if val and val.startswith("http") and val not in videos:
            videos.append(val)
    for match in VIDEO_URL_RE.findall(html[:80000]):
        if match not in videos:
            videos.append(match)
    if videos:
        payload["videos"] = videos[:12]
        payload["media_video"] = videos[0]
    elif any(hint in url.lower() for hint in ("/watch", "/video", "/shorts/", "/reel/", "/embed/", "/channel/", "/@")):
        payload["media_video"] = url
        payload.setdefault("videos", [url])


def _collect_images(html: str, tags: dict[str, str], payload: dict[str, Any]) -> None:
    candidates: list[str] = []
    for key in ("og:image", "twitter:image", "og:image:url"):
        if tags.get(key):
            candidates.append(tags[key])
    for match in IMG_SRC_RE.findall(html[:60000]):
        if match.startswith("http"):
            candidates.append(match)
    candidates.extend(re.findall(
        r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp|gif)(?:\?[^\s"\'<>]*)?',
        html[:60000],
        flags=re.IGNORECASE,
    ))
    candidates.extend(re.findall(
        r'"(?:avatar_url|profile_pic_url|display_url|image_url|profile_image|avatar)":"((?:\\.|[^"\\])*)"',
        html[:60000],
        flags=re.IGNORECASE,
    ))
    avatars: list[str] = []
    gallery: list[str] = []
    for raw in candidates:
        url = _decode_json_string(raw).strip() if raw.startswith("http") is False and "\\" in raw else raw.strip()
        if not url.startswith("http"):
            continue
        if is_plausible_profile_photo(url) and url not in avatars:
            avatars.append(url)
        elif is_displayable_media_url(url) and url not in gallery and url not in avatars:
            gallery.append(url)
    if avatars:
        payload["avatar_url"] = payload.get("avatar_url") or avatars[0]
    all_images = list(dict.fromkeys([*avatars, *gallery]))
    if all_images:
        payload["profile_images"] = all_images[:16]
        if len(all_images) > 1:
            payload["post_images"] = all_images[1:16]


def _parse_page(html: str, url: str, *, seed_query: str = "") -> dict[str, Any]:
    available, _reason = is_profile_page_available(html, url)
    if not available:
        return {}
    domain = normalize_domain(url) or _host(url) or "web"
    payload = _payload_base(url, source=f"{domain}_deep", platform=domain)
    tags = _parse_og_tags(html)

    title = tags.get("og:title") or ""
    description = tags.get("og:description") or tags.get("description") or tags.get("twitter:description") or ""

    _parse_title_fields(title, payload)
    if description and not is_generic_platform_bio(description):
        payload.setdefault("bio", description)
        _parse_visible_stats(description, payload)

    _parse_json_ld(html, payload)
    _parse_embedded_json(html, payload)
    _extract_text_intelligence(html, payload, url=url, seed_query=seed_query)
    _collect_images(html, tags, payload)
    _collect_videos(html, tags, url, payload)

    from services.correlation.handle_quality import normalize_profile_handle

    handle = normalize_profile_handle(url, domain, {})
    if handle:
        payload["username"] = handle.lstrip("@")

    return {k: v for k, v in payload.items() if v is not None and v != ""}


async def _try_json_profile(url: str) -> dict[str, Any]:
    """Some profile pages return JSON when Accept: application/json."""
    body = await _fetch_html(url, accept_json=True)
    if not body or not body.strip().startswith(("{", "[")):
        return {}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {}
    payload: dict[str, Any] = {}
    _flatten_json_profile(data, payload)
    return {k: v for k, v in payload.items() if v}


def _merge_payload(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, val in extra.items():
        if val is None or val == "":
            continue
        if key in merged and isinstance(merged[key], list) and isinstance(val, list):
            merged[key] = list(dict.fromkeys([*merged[key], *val]))
        elif key == "public_metadata" and isinstance(val, dict):
            merged.setdefault("public_metadata", {}).update(val)
        elif key not in merged or not merged[key]:
            merged[key] = val
    return merged


async def _fetch_og_thumbnail(page_url: str) -> str | None:
    """Generic video/page preview — uses og:image from the target URL."""
    html = await _fetch_html(page_url)
    if not html:
        return None
    tags = _parse_og_tags(html)
    for key in ("og:image", "twitter:image", "og:image:url"):
        thumb = tags.get(key)
        if thumb and thumb.startswith("http") and is_displayable_media_url(thumb):
            return thumb
    return None


async def _build_visual_assets(payload: dict[str, Any]) -> None:
    assets: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_asset(kind: str, url: str, thumbnail: str | None = None, title: str = "") -> None:
        if not url or url in seen:
            return
        seen.add(url)
        if kind in ("image", "avatar") and not is_displayable_media_url(url) and not url.startswith("/api/intel/screenshots/"):
            return
        assets.append({
            "type": kind,
            "url": url,
            "thumbnail_url": thumbnail or url,
            "title": title,
        })

    avatar = payload.get("avatar_url")
    if isinstance(avatar, str):
        add_asset("avatar", avatar, avatar, "Profile photo")

    for img in _list_unique(payload.get("profile_images"), payload.get("post_images")):
        if img != avatar:
            add_asset("image", img, img, "Profile image")

    videos = payload.get("videos") if isinstance(payload.get("videos"), list) else []
    if isinstance(payload.get("media_video"), str):
        videos = [payload["media_video"], *videos]
    for vid in videos:
        if not isinstance(vid, str) or not vid.startswith("http"):
            continue
        thumb = await _fetch_og_thumbnail(vid)
        title = payload.get("display_name") or "Video"
        add_asset("video", vid, thumb, str(title))

    page_url = str(payload.get("url") or "")
    has_image = bool(avatar) or any(a.get("type") in ("avatar", "image") for a in assets)
    if page_url.startswith("http") and not has_image:
        from services.page_preview import resolve_page_visual

        visual = await resolve_page_visual(page_url, budget="profile")
        img = visual.get("image_url")
        shot = visual.get("screenshot_url")
        if img and not str(img).startswith("/api/intel/screenshots/"):
            payload["avatar_url"] = payload.get("avatar_url") or img
            add_asset("image", img, img, "Page preview")
        elif shot:
            payload["page_screenshot_url"] = shot
            add_asset("screenshot", page_url, shot, "Profile preview")

    if assets:
        payload["visual_assets"] = assets[:20]


def _list_unique(*groups: Any) -> list[str]:
    out: list[str] = []
    for group in groups:
        if isinstance(group, list):
            for item in group:
                if isinstance(item, str) and item not in out:
                    out.append(item)
    return out


async def deep_fetch_profile(
    url: str,
    *,
    expected_handle: str | None = None,
    seed_query: str = "",
) -> dict[str, Any]:
    """Fetch and parse all available public data from any profile URL."""
    if not url or not url.startswith("http") or is_junk_profile_url(url):
        return {}
    from services.correlation.handle_quality import normalize_profile_handle

    path_handle = normalize_profile_handle(url, normalize_domain(url) or "", {})
    if not _profile_matches_expected(path_handle, expected_handle, url):
        return {}

    html = await _fetch_html(url)
    payload: dict[str, Any] = {}
    if html:
        payload = _parse_page(html, url, seed_query=seed_query)

    json_payload = await _try_json_profile(url)
    if json_payload:
        payload = _merge_payload(payload, json_payload)

    await _build_visual_assets(payload)

    return {k: v for k, v in payload.items() if v is not None and v != ""}


def is_enrichable_profile_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    from services.google_dorking.filters import is_junk_dork_url
    if is_junk_dork_url(url) or is_junk_profile_url(url):
        return False
    parsed = urlparse(url)
    return bool(parsed.netloc and parsed.path.strip("/"))


def is_deep_fetchable_url(url: str) -> bool:
    return is_enrichable_profile_url(url)
