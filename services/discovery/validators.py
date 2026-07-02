"""Validators to prevent URL-derived fake username expansion."""

from __future__ import annotations

import re
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", re.IGNORECASE)
PHONE_RE = re.compile(r"^\+?[\d\s\-().]{7,20}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)
HANDLE_RE = re.compile(r"^[\w][\w.-]{0,31}$")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")
IMAGE_PATH_HINTS = ("/avatar", "/avatars/", "/profile/", "/photo/", "/img/", "/image/")
BRANDING_IMAGE_HINTS = (
    "/favicon", "favicon.", "/logo", "/logos/", "/icon-", "/icons/", "/apple-touch-icon",
    "/sprite", "/badge", "/brand/", "/static/images/logo", "/assets/logo", "/default-avatar",
    "opengraph-image", "og-image", "/share-image", "placeholder", "1x1.", "pixel.",
)
GENERIC_BIO_PHRASES = (
    "share your videos with friends",
    "sign in to continue",
    "log in or sign up",
    "join to view",
    "this page isn't available",
    "see photos and videos",
    "connect with friends",
)
URL_LIKE_MARKERS = (".com", ".org", ".net", ".io", ".co", "http", "://", "www.", "/")
GENERIC_PATH_SEGMENTS = frozenset({
    "user", "users", "profile", "details", "forums", "forum", "member", "member.php",
    "api-v2", "hackers", "player", "perfil", "p", "u", "about", "players",
})


def is_url(value: str) -> bool:
    q = value.strip().lower()
    return q.startswith(("http://", "https://")) or ("." in q and "/" in q)


def is_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value.strip()))


def is_phone(value: str) -> bool:
    return bool(PHONE_RE.match(value.strip()))


def is_plausible_phone(value: str) -> bool:
    """Reject ISO dates, CDN numeric fragments, and bare digit runs from URLs."""
    raw = value.strip()
    if not raw or not is_phone(raw):
        return False
    if ISO_DATE_RE.match(raw):
        return False
    if raw.startswith(("http://", "https://")):
        return False
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) < 10 or len(digits) > 15:
        return False
    has_formatting = any(ch in raw for ch in "()-. ")
    if not raw.startswith("+") and not has_formatting and len(digits) > 11:
        return False
    if "." in raw and "-" in raw:
        return False
    return True


def is_domain(value: str) -> bool:
    host = value.strip().lower().replace("www.", "")
    if "@" in host or "/" in host:
        return False
    return bool(DOMAIN_RE.match(host))


def is_screenshot_preview_url(value: str) -> bool:
    return value.strip().startswith("/api/intel/screenshots/")


def is_social_cdn_media_url(value: str) -> bool:
    """Instagram/Facebook CDN URLs — often lack file extensions."""
    low = value.strip().lower()
    if not low.startswith(("http://", "https://")):
        return False
    if not any(host in low for host in ("fbcdn.net", "cdninstagram.com", "instagram.", "lookaside.fbsbx.com", "scontent.")):
        return False
    if any(ext in low.split("?", 1)[0] for ext in (".mp4", ".webm", ".m4v", ".jpg", ".jpeg", ".png", ".webp")):
        return True
    return any(hint in low for hint in ("/v/t", "/o1/v/", "stp=dst-jpg", "efg=", "oe=")) or (
        "lookaside/crawler/media" in low or "media_id=" in low
    )


def is_proxiable_media_url(value: str) -> bool:
    """URLs safe to fetch through the in-app media proxy."""
    q = value.strip()
    if not q.startswith(("http://", "https://")):
        return False
    if is_image_url(q):
        return True
    low = q.lower().split("?", 1)[0]
    if low.endswith((".mp4", ".webm", ".m4v")):
        return True
    return is_social_cdn_media_url(q)


def is_image_url(value: str) -> bool:
    q = value.strip()
    if is_screenshot_preview_url(q):
        return True
    q = q.lower()
    if not q.startswith(("http://", "https://")):
        return False
    if is_branding_image_url(q):
        return False
    parsed = urlparse(q)
    path = parsed.path.lower()
    query = parsed.query.lower()
    if any(hint in path for hint in IMAGE_PATH_HINTS):
        return True
    if any(path.endswith(ext) for ext in IMAGE_EXTENSIONS):
        return True
    if any(k in query for k in ("format=jpg", "format=png", "format=webp", "type=image")):
        return True
    if "/avatar" in path or "/photo" in path or "profile_pic" in path or "display_url" in path:
        return True
    if is_social_cdn_media_url(q):
        return True
    return False


def is_branding_image_url(value: str) -> bool:
    """Reject favicons, logos, and site branding — not profile photos."""
    low = value.strip().lower()
    if not low.startswith("http"):
        return True
    if any(hint in low for hint in BRANDING_IMAGE_HINTS):
        return True
    if low.endswith(".svg") or low.endswith(".ico"):
        return True
    if re.search(r"/\d{1,2}x\d{1,2}\.", low):
        return True
    return False


def is_plausible_profile_photo(value: str) -> bool:
    """Profile photo candidate — real image URL, not site logo/favicon."""
    if not value.startswith(("http://", "https://")):
        return False
    if is_branding_image_url(value):
        return False
    return is_image_url(value)


def is_displayable_media_url(value: str) -> bool:
    """Gallery / post image — slightly more permissive than profile avatar filter."""
    if not value.startswith(("http://", "https://")):
        return False
    if is_branding_image_url(value):
        return False
    low = value.lower()
    if any(ext in low for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
        return True
    if any(hint in low for hint in ("/avatar", "/photo", "/image", "/media/", "/upload", "/attachments/")):
        return True
    return is_image_url(value)


_JUNK_PROFILE_PATH_RE = re.compile(
    r"cloud-\d+img|service[_-]?code|/error(?:/|$)|unavailable|placeholder",
    re.IGNORECASE,
)

FEDIVERSE_HOST_HINTS = ("mastodon", "pleroma", "misskey", "peertube", "friendica")
VALID_OG_TYPES = frozenset({
    "website", "article", "profile", "music.song", "music.album",
    "music.playlist", "music.radio_station", "video.movie", "video.episode",
    "video.tv_show", "video.other", "book", "books.author", "books.book",
})


def is_plausible_display_name(value: str) -> bool:
    """Reject numeric-only or junk display names scraped from error/parking pages."""
    name = (value or "").strip()
    if len(name) < 3:
        return False
    if re.fullmatch(r"\d+", name):
        return False
    if name.lower() in {"pk", "na", "n/a", "unknown", "none", "null", "undefined"}:
        return False
    return True


def is_junk_profile_url(url: str) -> bool:
    """Reject hosting error pages, CDN placeholders, and non-profile URLs."""
    if not url or not url.startswith(("http://", "https://")):
        return True
    from services.google_dorking.filters import is_junk_dork_url

    if is_junk_dork_url(url):
        return True
    parsed = urlparse(url.strip())
    path = (parsed.path or "").lower().strip("/")
    host = (parsed.netloc or "").lower().replace("www.", "")
    if not path:
        return True
    if _JUNK_PROFILE_PATH_RE.search(path):
        return True
    if path.endswith(".html") and "@" not in path:
        if "cloud-" in path or "img.html" in path or path.count("/") == 0:
            return True
    if host.startswith("media.") and "@" not in path and "/users/" not in path:
        if ".html" in path or "cloud-" in path:
            return True
    if any(hint in host for hint in FEDIVERSE_HOST_HINTS):
        if "@" not in url and "/users/" not in path and "/@/" not in path:
            segments = [s for s in path.split("/") if s]
            if len(segments) == 1 and not segments[0].startswith("@"):
                return True
    if host.endswith("substack.com") and path.startswith("search"):
        return True
    if host.endswith("replit.com") and "login" in path:
        return True
    if "search.php" in path and "author=" in (parsed.query or "").lower():
        return True
    return False


def is_parking_page_html(html: str) -> bool:
    """Detect domain parking / hijacked pages that return HTTP 200 with fake OG tags."""
    low = (html or "").lower()
    og_type = re.search(r'property=["\']og:type["\']\s+content=["\']([^"\']+)', low)
    og_title = re.search(r'property=["\']og:title["\']\s+content=["\']([^"\']+)', low)
    if not og_type or not og_title:
        return False
    otype = og_type.group(1).strip().lower()
    title = og_title.group(1).strip()
    if otype not in VALID_OG_TYPES and otype == title.lower():
        return True
    if re.fullmatch(r"\d+", title) and otype not in VALID_OG_TYPES:
        return True
    if "loli.io" in low or "vip2.loli.io" in low:
        return True
    body = re.sub(r"<[^>]+>", " ", low)
    if len(body.strip()) < 400 and og_type and og_title:
        if otype not in VALID_OG_TYPES and len(title) <= 4:
            return True
    return False


def is_service_error_html(html: str) -> bool:
    low = (html or "").lower()
    if "do not provide services in your area" in low or "not provide services in your area" in low:
        return True
    if "service code" in low and ("service email" in low or "hosted by" in low):
        return True
    if "something went wrong" in low and ("hackerrank" in low or "reload" in low):
        return True
    if "specified member cannot be found" in low or "member cannot be found" in low:
        return True
    if "форум временно отключ" in low or "forum temporarily" in low:
        return True
    return False


def is_generic_platform_bio(value: str) -> bool:
    low = value.strip().lower()
    if not low or len(low) < 12:
        return False
    return any(phrase in low for phrase in GENERIC_BIO_PHRASES)


def is_plausible_handle(value: str) -> bool:
    """Strict handle check — rejects URL fragments and domain-like tokens."""
    handle = value.strip().lower()
    if not handle or len(handle) < 2 or len(handle) > 32:
        return False
    if any(marker in handle for marker in URL_LIKE_MARKERS):
        return False
    if handle.count(".") > 1:
        return False
    if is_domain(handle):
        return False
    if handle in GENERIC_PATH_SEGMENTS:
        return False
    return bool(HANDLE_RE.match(handle))


def is_known_platform_domain(value: str) -> bool:
    """True when a website value is a bare domain root, not a personal page."""
    q = value.strip()
    if q.startswith(("http://", "https://")):
        parsed = urlparse(q)
        path = parsed.path.strip("/")
        if not path:
            return True
        segments = path.split("/")
        return len(segments) == 1 and segments[0].lower() in GENERIC_PATH_SEGMENTS
    if "/" not in q and is_domain(q):
        return True
    return False


def is_fake_url_username(value: str) -> bool:
    """Detect mangled usernames produced from URL concatenation."""
    q = value.strip().lower()
    if not q:
        return True
    if any(tld in q for tld in (".com", ".org", ".net", ".io", ".co.uk")):
        return True
    if "://" in q or q.count("/") > 1:
        return True
    return False


def normalize_domain(value: str) -> str | None:
    q = value.strip()
    if q.startswith(("http://", "https://")):
        host = urlparse(q).netloc
    else:
        host = q.split("/")[0]
    host = host.replace("www.", "").lower().strip()
    if is_domain(host):
        return host
    return None


def extract_emails_from_text(text: str) -> list[str]:
    found = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text, flags=re.IGNORECASE)
    return sorted({e.lower() for e in found if is_email(e)})


def extract_urls_from_text(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"']+", text, flags=re.IGNORECASE)


DEFINITIVE_VERIFY_FAILURES = frozenset({
    "junk_profile_url",
    "parking_page",
    "service_error_page",
    "unavailable_page",
    "not_found",
    "error_title",
    "empty_response",
})


def verify_outcome_confirmed(available: bool | None, reason: str) -> bool | None:
    """Map HTTP profile check to True / False / None (inconclusive)."""
    if available is True:
        return True
    if reason == "login_wall":
        return None
    if reason in DEFINITIVE_VERIFY_FAILURES or reason.startswith("http_404"):
        return False
    if reason.startswith("fetch_error") or reason.startswith("http_"):
        return None
    return False


def verify_blocks_account_confirmation(meta: dict) -> bool:
    if meta.get("live_profile_verified") is not False:
        return False
    reason = str(meta.get("live_verify_reason") or "")
    return reason in DEFINITIVE_VERIFY_FAILURES or reason.startswith("http_404")
