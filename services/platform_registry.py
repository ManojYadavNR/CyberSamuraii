"""Dynamic platform host discovery — Maigret inventory, labels, probe templates."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from services.discovery.validators import normalize_domain

USERNAME_PLACEHOLDER_RE = re.compile(r"\{username\}", re.I)
SOCIAL_POST_PATH_RE = re.compile(
    r"/(?:posts|photos|videos|reel|permalink)(?:/|$)|/(?:p|reel|tv)/[^/?#]+",
    re.I,
)
PROFILE_PATH_SKIP = frozenset({
    "p", "reel", "tv", "explore", "accounts", "share", "sharer", "pages",
    "profile.php", "www", "posts", "photos", "videos",
})

# Used only when Maigret DB is unavailable.
_FALLBACK_PROBE_TEMPLATES: list[dict[str, Any]] = [
    {"platform": "github.com", "url": "https://github.com/{q}", "rank": 1},
    {"platform": "gitlab.com", "url": "https://gitlab.com/{q}", "rank": 2},
    {"platform": "linkedin.com", "url": "https://www.linkedin.com/in/{q}", "rank": 3},
    {"platform": "instagram.com", "url": "https://www.instagram.com/{q}/", "rank": 4},
    {"platform": "facebook.com", "url": "https://www.facebook.com/{q}", "rank": 5},
    {"platform": "youtube.com", "url": "https://www.youtube.com/@{q}", "rank": 6},
    {"platform": "reddit.com", "url": "https://www.reddit.com/user/{q}", "rank": 7},
    {"platform": "tiktok.com", "url": "https://www.tiktok.com/@{q}", "rank": 8},
    {"platform": "x.com", "url": "https://x.com/{q}", "rank": 9},
    {"platform": "medium.com", "url": "https://medium.com/@{q}", "rank": 10},
    {"platform": "dev.to", "url": "https://dev.to/{q}", "rank": 11},
    {"platform": "pinterest.com", "url": "https://www.pinterest.com/{q}/", "rank": 12},
]


def normalize_platform_host(url_or_host: str) -> str:
    if not url_or_host:
        return ""
    raw = url_or_host.strip()
    if "://" in raw:
        host = urlparse(raw).netloc
    else:
        host = raw.split("/")[0]
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    if host.startswith("in.") and "linkedin" in host:
        host = host[3:]
    return host


def platform_label_from_host(url_or_host: str) -> str:
    host = normalize_platform_host(url_or_host)
    if not host:
        return "Web"
    parts = [p for p in host.split(".") if p]
    if not parts:
        return host
    if host in {"youtu.be"}:
        return "YouTube"
    if host in {"t.me", "telegram.me"}:
        return "Telegram"
    if host in {"x.com", "twitter.com"}:
        return "X"
    if host.endswith(".github.io") and len(parts) >= 3:
        return parts[0].replace("-", " ").title()
    label = parts[-2] if len(parts) >= 2 and len(parts[-1]) <= 3 else parts[0]
    return label.replace("-", " ").title()


def is_social_post_url(url: str) -> bool:
    if not url:
        return False
    if SOCIAL_POST_PATH_RE.search(url.lower()):
        return True
    return False


def profile_slug_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    path = parsed.path.strip("/")
    if not path:
        return None
    if path.startswith("in/"):
        parts = path.split("/")
        return parts[1].lower() if len(parts) > 1 else None
    if "@" in path:
        return path.split("@", 1)[1].split("/")[0].lower()
    host = normalize_platform_host(parsed.netloc)
    if host.endswith("tumblr.com") and parsed.netloc and not parsed.netloc.startswith("www."):
        return parsed.netloc.split(".")[0].lower()
    segment = path.split("/")[0].lower()
    if segment in PROFILE_PATH_SKIP:
        return None
    return segment


def open_link_label_for_url(url: str) -> str:
    label = platform_label_from_host(url)
    if label == "Web":
        return "Open original page →"
    return f"View on {label} →"


@lru_cache(maxsize=1)
def _maigret_sites() -> list[tuple[int, str, dict[str, Any]]]:
    db_path = Path.home() / ".maigret" / "data.json"
    try:
        with open(db_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    sites = data.get("sites", data)
    if not isinstance(sites, dict):
        return []

    out: list[tuple[int, str, dict[str, Any]]] = []
    for name, info in sites.items():
        if not isinstance(info, dict) or info.get("disabled"):
            continue
        rank = info.get("alexaRank") or info.get("alexa_rank")
        if not isinstance(rank, int) or rank <= 0:
            rank = 10_000_000
        out.append((rank, str(name), info))
    out.sort(key=lambda row: row[0])
    return out


@lru_cache(maxsize=1)
def priority_social_domains(max_domains: int = 12) -> tuple[str, ...]:
    """Hosts for site: dork queries — ranked from Maigret metadata."""
    domains: list[str] = []
    seen: set[str] = set()
    for rank, _name, info in _maigret_sites():
        if len(domains) >= max_domains:
            break
        url_main = str(info.get("urlMain") or info.get("url") or "")
        url_user = str(info.get("url") or "")
        if "{username}" not in url_user:
            continue
        host = normalize_platform_host(url_main or url_user)
        if not host or host in seen:
            continue
        seen.add(host)
        domains.append(host)
    if not domains:
        domains = [str(t["platform"]) for t in _FALLBACK_PROBE_TEMPLATES[:max_domains]]
    return tuple(domains)


def build_probe_templates(*, max_sites: int | None = None) -> list[dict[str, Any]]:
    """Probe URLs from Maigret site DB (username placeholders), with small fallback."""
    cap = max_sites or int(os.getenv("PLATFORM_PROBE_MAX_SITES", "32"))
    templates: list[dict[str, Any]] = []
    seen_hosts: set[str] = set()

    for rank, _name, info in _maigret_sites():
        if len(templates) >= cap:
            break
        url_pattern = str(info.get("url") or "")
        if not USERNAME_PLACEHOLDER_RE.search(url_pattern):
            continue
        probe_url = USERNAME_PLACEHOLDER_RE.sub("{q}", url_pattern)
        url_main = str(info.get("urlMain") or url_pattern)
        host = normalize_platform_host(url_main)
        if not host or host in seen_hosts:
            continue
        seen_hosts.add(host)
        templates.append({
            "platform": host,
            "url": probe_url,
            "rank": rank,
        })

    if not templates:
        return _FALLBACK_PROBE_TEMPLATES[:cap]

    for fallback in _FALLBACK_PROBE_TEMPLATES:
        if len(templates) >= cap:
            break
        host = str(fallback["platform"])
        if host in seen_hosts:
            continue
        seen_hosts.add(host)
        templates.append(dict(fallback))

    templates.sort(key=lambda t: int(t.get("rank", 10_000_000)))
    return templates[:cap]


def platform_key_from_host(url_or_host: str) -> str:
    host = normalize_platform_host(url_or_host)
    if not host:
        return "web"
    parts = [p for p in host.split(".") if p]
    if not parts:
        return host
    if host.endswith(".github.io") and len(parts) >= 3:
        return parts[0]
    if len(parts) >= 2 and len(parts[-1]) <= 3:
        return parts[-2]
    return parts[0]


@lru_cache(maxsize=1)
def priority_social_host_set() -> frozenset[str]:
    return frozenset(priority_social_domains(128))


def is_priority_social_host(url_or_host: str) -> bool:
    host = normalize_platform_host(url_or_host)
    return bool(host and host in priority_social_host_set())


def site_post_search_query(domain: str, anchor: str, phrase: str) -> str:
    """Build a site: dork for any discovered host (no fixed platform list)."""
    domain = normalize_platform_host(domain) or domain
    return f"site:{domain} {anchor} {phrase}"


def generic_search_domains(limit: int = 8) -> list[str]:
    """Hosts for cross-platform dork OR-clauses — from Maigret rank."""
    return list(priority_social_domains(limit))


def skip_pivot_domain(domain: str) -> bool:
    """Generic hosts not useful as entity-pivot targets."""
    host = normalize_platform_host(domain) or domain.lower()
    return host in {"google.com", "youtu.be", "youtube.com"} or host.endswith(".google.com")


def build_site_or_query(domains: list[str], anchor: str, terms: str, *, category: str = "achievements") -> str:
    """(site:a OR site:b) anchor terms — domains from registry, not hardcoded."""
    hosts = [normalize_platform_host(d) for d in domains if d]
    hosts = [h for h in hosts if h][:4]
    if not hosts:
        return f"{anchor} {terms}"
    if len(hosts) == 1:
        return f"site:{hosts[0]} {anchor} {terms}"
    clause = " OR ".join(f"site:{h}" for h in hosts)
    return f"({clause}) {anchor} {terms}"


def login_wall_trust_hosts() -> frozenset[str]:
    """Hosts where HTTP 200 + login wall still implies a live profile."""
    hosts = {normalize_platform_host(t["platform"]) for t in build_probe_templates(max_sites=200)}
    return frozenset(hosts)
