"""Google dork execution — free ddgs search (default) with optional Google API."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from services.google_dorking.ddgs_client import search_ddgs_web
from services.google_dorking.scraper import search_google_web

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"


def _api_credentials() -> tuple[str, str] | None:
    api_key = os.environ.get("GOOGLE_CUSTOM_SEARCH_API_KEY", "").strip()
    cx = os.environ.get("GOOGLE_CUSTOM_SEARCH_CX", "").strip()
    if not api_key or not cx:
        return None
    return api_key, cx


def _search_mode() -> str:
    return os.environ.get("GOOGLE_DORKING_MODE", "web").strip().lower()


async def search_dork_api(
    dork: str,
    *,
    num: int = 5,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    creds = _api_credentials()
    if not creds:
        return []

    api_key, cx = creds
    params = {
        "key": api_key,
        "cx": cx,
        "q": dork,
        "num": max(1, min(num, 10)),
        "safe": "off",
    }

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=20.0)

    try:
        assert client is not None
        response = await client.get(SEARCH_URL, params=params)
        if response.status_code == 429:
            return []
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    finally:
        if owns_client and client is not None:
            await client.aclose()

    items: list[dict[str, Any]] = []
    for hit in payload.get("items") or []:
        if not isinstance(hit, dict):
            continue
        link = hit.get("link")
        if not link:
            continue
        items.append(
            {
                "title": hit.get("title") or "",
                "url": link,
                "snippet": hit.get("snippet") or "",
                "display_link": hit.get("displayLink") or "",
                "dork_query": dork,
                "source": "google_api",
            }
        )
    return items


async def search_dork_web(dork: str, *, num: int = 5, client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
    """
    Free search chain (no API keys):
    1. Google CSE API for site: surgical dorks when keys are configured
    2. ddgs library — reliable, supports site:/inurl:/intext: dork operators
    3. google.com HTML — best-effort fallback (often JS-only from servers)
    """
    if "site:" in dork.lower() and _api_credentials():
        api_hits = await search_dork_api(dork, num=num, client=client)
        if api_hits:
            return api_hits
    hits = await search_ddgs_web(dork, num=num, pause_s=0.1)
    if hits:
        return hits
    return await search_google_web(dork, num=num, client=client, pause_s=0.4)


async def search_dork(
    dork: str,
    *,
    num: int = 5,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    if _search_mode() == "api":
        return await search_dork_api(dork, num=num, client=client)
    return await search_dork_web(dork, num=num, client=client)


async def run_dork_queries(
    dorks: list[str],
    *,
    results_per_dork: int = 5,
    max_concurrency: int = 3,
    dork_categories: dict[str, str] | None = None,
    deadline_monotonic: float | None = None,
) -> list[dict[str, Any]]:
    if not dorks:
        return []

    import time

    api_mode = _search_mode() == "api"
    concurrency = max(1, min(max_concurrency, 8))
    sem = asyncio.Semaphore(concurrency)
    seen_urls: set[str] = set()
    merged: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=20.0) as client:

        async def _one(dork: str) -> None:
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                return
            async with sem:
                if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                    return
                hits: list[dict[str, Any]] = []
                for attempt in range(2):
                    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                        break
                    if api_mode:
                        hits = await search_dork_api(dork, num=results_per_dork, client=client)
                    else:
                        hits = await search_dork_web(dork, num=results_per_dork, client=client)
                    if hits:
                        break
                    await asyncio.sleep(0.25 * (attempt + 1))
                for hit in hits:
                    url = str(hit.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    if dork_categories and dork in dork_categories:
                        hit = {**hit, "dork_category": dork_categories[dork]}
                    merged.append(hit)

        ordered = sorted(
            dorks,
            key=lambda d: (
                0 if not any(op in d for op in ("site:", "inurl:", "intext:", "filetype:")) and not d.startswith('"') else
                1 if d.startswith('"') or "inurl:" in d else
                2,
                d,
            ),
        )
        await asyncio.gather(*(_one(dork) for dork in ordered))

    return merged
