"""Classify URLs for lead-generation visual capture."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from services.discovery.validators import is_image_url
from services.google_dorking.filters import is_junk_dork_url

LOGIN_RE = re.compile(r"/login(?:[/?]|$)|/signin(?:[/?]|$)|/auth(?:[/?]|$)", re.I)
SEARCH_RE = re.compile(r"/search(?:[/?]|$)|[?&]q=", re.I)
VIDEO_RE = re.compile(
    r"(?:youtube\.com|youtu\.be|vimeo\.com|tiktok\.com/.+/video/)",
    re.I,
)
HACKATHON_TERMS = (
    "hackathon", "winner", "winners", "finalist", "runner-up", "champion",
    "competition", "coding contest", "devpost", "prize", "awarded", "trophy",
)
NEWS_TERMS = ("news", "newspaper", "reported", "headline", "press release", "coverage", "article")
COLLEGE_TERMS = (
    ".edu", "university", "college", "institute", "campus", "convocation", "graduation",
    "congratulations", "congratulates",
)
EVENT_TERMS = (
    "conference", "summit", "meetup", "workshop", "seminar", "symposium",
    "speaker", "keynote", "webinar", "fest", "expo",
)


def extract_seed_username(seed_query: str) -> str:
    raw = (seed_query or "").strip()
    if "|" in raw:
        left = raw.split("|", 1)[0].strip()
        if left and "@" not in left:
            return left
    if "@" not in raw:
        return raw
    return raw


def is_junk_lead_url(url: str) -> bool:
    if not url.startswith("http") or is_junk_dork_url(url):
        return True
    low = url.lower()
    if LOGIN_RE.search(low):
        return True
    if SEARCH_RE.search(low) and "/watch" not in low:
        return True
    if any(ext in low.split("?", 1)[0] for ext in (".pdf", ".zip", ".mp3", ".exe")):
        return True
    return False


def classify_lead_type(
    *,
    url: str,
    title: str = "",
    snippet: str = "",
    dork_category: str = "",
) -> str:
    blob = f"{title} {snippet} {dork_category} {url}".lower()
    if VIDEO_RE.search(url) or "youtube.com" in blob:
        return "video"
    if any(t in blob for t in HACKATHON_TERMS) or dork_category in ("achievements", "events_general"):
        return "hackathon"
    if any(t in blob for t in NEWS_TERMS) or dork_category == "news_mentions":
        return "news"
    if any(t in blob for t in COLLEGE_TERMS) or ".edu" in url.lower():
        return "college"
    if any(t in blob for t in EVENT_TERMS):
        return "event"
    if dork_category in ("blog_search", "article_search", "publications"):
        return "article"
    if is_image_url(url):
        return "image"
    if dork_category in ("profile_exact", "profile_mentions", "documents"):
        return "profile"
    return "mention"


def source_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url
