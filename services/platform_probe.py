"""Direct HTTP probes for high-value social platforms — fast live username checks."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

from services.correlation.handle_quality import is_correlatable_handle, normalize_profile_handle
from services.evidence.profile_verifier import USER_AGENT, is_profile_page_available

REQUEST_TIMEOUT = 8.0
MAX_CONCURRENT = 18
DEFAULT_BUDGET_SEC = 28.0

from services.platform_registry import build_probe_templates, login_wall_trust_hosts, normalize_platform_host, profile_slug_from_url


def classify_probe_response(url: str, status_code: int, html: str) -> tuple[bool | None, str]:
    """Return (exists, reason). Login walls on 200 mean profile likely exists."""
    available, reason = is_profile_page_available(html, url, status_code=status_code)
    if available:
        return True, reason
    if reason == "login_wall" and status_code < 400:
        host = normalize_platform_host(url)
        if host in login_wall_trust_hosts():
            return True, "login_wall"
        return None, reason
    if reason in ("unavailable_page", "not_found", "error_title") or reason.startswith("http_404"):
        return False, reason
    if reason.startswith("http_") and status_code >= 400:
        return False, reason
    if status_code == 404:
        return False, "http_404"
    if status_code == 200 and reason in ("empty_response", "service_error_page", "parking_page"):
        return False, reason
    return None, reason


async def _probe_one(
    client: httpx.AsyncClient,
    template: dict[str, Any],
    query: str,
    deadline: float,
) -> dict[str, Any] | None:
    if time.monotonic() >= deadline:
        return None
    url = str(template["url"]).format(q=query)
    platform = str(template["platform"])
    try:
        response = await client.get(url)
    except httpx.HTTPError:
        return None

    exists, reason = classify_probe_response(url, response.status_code, response.text)
    if exists is not True:
        return None

    final_url = str(response.url)
    from services.discovery.attribution import context_references_seed
    from services.discovery.validators import is_junk_profile_url
    from services.correlation.handle_quality import is_correlatable_handle, normalize_profile_handle

    if is_junk_profile_url(final_url):
        return None

    content_seed = context_references_seed(response.text[:50000], seed_query=query)
    if reason != "login_wall" and not content_seed:
        return None

    platform = normalize_platform_host(final_url) or str(template["platform"])
    handle = profile_slug_from_url(final_url) or normalize_profile_handle(final_url, platform, {"username": query.lower()})
    if not handle or not is_correlatable_handle(handle, query, final_url):
        return None

    return {
        "platform": platform,
        "url": final_url,
        "username": handle,
        "check_type": "live_scan",
        "verified": True,
        "registered": True,
        "status": "registered",
        "live_profile_verified": None if reason == "login_wall" else True,
        "live_verify_reason": reason,
        "content_seed_verified": True if content_seed else None,
        "http_status": response.status_code,
        "probe_source": "platform_probe",
    }


async def probe_priority_platforms(
    query: str,
    *,
    budget_sec: float = DEFAULT_BUDGET_SEC,
) -> tuple[list[dict[str, Any]], int]:
    """Live-check major social platforms in parallel."""
    q = query.strip()
    if not q or not re.match(r"^[\w][\w.-]{0,31}$", q):
        return [], 0

    deadline = time.monotonic() + budget_sec
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    templates = build_probe_templates()

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        limits=httpx.Limits(max_connections=MAX_CONCURRENT, max_keepalive_connections=8),
    ) as client:
        async def run(template: dict[str, Any]) -> None:
            async with sem:
                hit = await _probe_one(client, template, q, deadline)
                if not hit:
                    return
                url = str(hit.get("url") or "")
                if url in seen_urls:
                    return
                seen_urls.add(url)
                results.append(hit)

        await asyncio.gather(*(run(t) for t in templates))

    results.sort(key=lambda r: str(r.get("platform", "")).lower())
    return results, len(templates)
