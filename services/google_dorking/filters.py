"""Filter low-signal or unrelated Google dork hits."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from services.discovery.validators import normalize_domain

# Domains that rarely identify a specific person for username OSINT.
JUNK_DORK_DOMAINS = frozenset({
    "wheelofnames.com",
    "bettingcompanies.africa",
    "winner.rw",
    "winner-africa.com",
    "wikipedia.org",
    "en.wikipedia.org",
    "amazon.com",
    "google.com",
    "accounts.google.com",
    "epfindia.gov.in",
    "unifiedportal-mem.epfindia.gov.in",
    "justdial.com",
    "www.justdial.com",
    "indiamart.com",
    "sulekha.com",
    "truecaller.com",
})

HIGH_VALUE_DORK_CATEGORIES = frozenset({
    "google_plain",
    "web_inurl",
    "web_intext",
    "profile_mentions",
    "blog_search",
    "article_search",
    "news_mentions",
    "forum_mentions",
    "discussion_search",
    "events_general",
    "achievements",
    "education",
    "dev_blogs",
    "media_images",
    "media_video",
})

HACKATHON_NEWS_RE = re.compile(
    r"hackathon|winner|won|first place|finalist|champion|award|trophy|"
    r"college|university|institute|campus|school|alumni|newspaper|headline|"
    r"congratulations|fest|competition|devpost",
    re.I,
)

from services.platform_registry import is_social_post_url as _registry_is_social_post_url

SOCIAL_POST_RE = re.compile(
    r"/(?:posts|photos|videos|reel|permalink)(?:/|$)|/(?:p|reel|tv)/[^/?#]+",
    re.I,
)


def is_social_post_url(url: str) -> bool:
    if not url:
        return False
    if SOCIAL_POST_RE.search(url.lower()):
        return True
    return _registry_is_social_post_url(url)


def is_junk_dork_url(url: str) -> bool:
    domain = normalize_domain(url) or ""
    if not domain:
        return True
    if domain in JUNK_DORK_DOMAINS:
        return True
    if domain.endswith(".wikipedia.org"):
        return True
    return False


def is_college_homepage_url(url: str) -> bool:
    """Bare college/university site root — not a post about the seed user."""
    if not url or is_social_post_url(url):
        return False
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or "").lower()
    is_edu_host = bool(
        re.search(r"\.(edu|ac\.in|edu\.|gov\.)(\.|$)", host)
        or re.search(r"college|university|institute|school|academy", host)
    )
    if not is_edu_host:
        return False
    segments = [s for s in parsed.path.split("/") if s]
    return len(segments) <= 1


PHONE_JUNK_HOSTS = frozenset({
    "googleguide.com",
    "ahrefs.com",
    "geeksforgeeks.org",
    "gist.github.com",
    "edu.google.com",
    "stripe.com",
    "ecfmg.org",
    "sixflags.com",
})


def phone_dork_hit_displayable(
    *,
    url: str,
    title: str = "",
    snippet: str = "",
    seed_query: str,
) -> bool:
    """Phone dork hits must reference the full number — blocks SEO/tutorial false positives."""
    from urllib.parse import urlparse

    from services.fusion_engine import normalize_phone

    if is_junk_dork_url(url):
        return False
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower().replace("www.", "")
    if host in PHONE_JUNK_HOSTS:
        return False
    if "whoisphone" in host and "whois phone number" in title.lower():
        return False

    seed_digits = re.sub(r"\D", "", normalize_phone(seed_query))
    if len(seed_digits) < 7:
        return False
    tail = seed_digits[-10:] if len(seed_digits) >= 10 else seed_digits
    blob_digits = re.sub(r"\D", "", f"{url} {title} {snippet}")
    return tail in blob_digits


def sanitize_org_label(value: str) -> str:
    """Strip LinkedIn/login chrome accidentally parsed as employer names."""
    cleaned = value.strip()
    for junk in (
        "| LinkedIn",
        "Sign in - Google Accounts",
        "Sign in",
        "LinkedInSign in",
        "· GitHub",
        "Whois Phone Number",
        "look up phone owner",
        "Area Code",
    ):
        if junk in cleaned:
            cleaned = cleaned.split(junk)[0].strip()
    return cleaned


def handle_from_profile_url(url: str) -> str | None:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    path = parsed.path.strip("/")
    if not path:
        return None
    if "@" in path:
        return path.split("@", 1)[1].split("/")[0].lower()
    if path.startswith("in/"):
        return path.split("/")[1].lower() if len(path.split("/")) > 1 else None
    return path.split("/")[0].lower()


def dork_hit_displayable(
    *,
    url: str,
    title: str = "",
    snippet: str = "",
    seed_query: str,
    dork_category: str = "",
    dork_query: str = "",
) -> bool:
    """
    Dork hit belongs to the investigated person.
    Requires the seed username/handle in the URL, title, or snippet —
    blocks random hackathon/news hits about other people.
    """
    from services.discovery.attribution import dork_hit_attributed

    if is_junk_dork_url(url):
        return False
    if not seed_query.strip():
        return True
    return dork_hit_attributed(
        url=url,
        title=title,
        snippet=snippet,
        seed_query=seed_query,
        dork_query=dork_query,
        dork_category=dork_category,
    )
