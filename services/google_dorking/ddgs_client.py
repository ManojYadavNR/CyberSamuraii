"""Free web search via ddgs — rotates backends when DuckDuckGo returns empty."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

_BACKENDS = ("auto", "bing", "yahoo")


def _search_sync(dork: str, *, num: int, backend: str) -> list[dict[str, Any]]:
    try:
        from ddgs import DDGS
    except ImportError:
        return []

    items: list[dict[str, Any]] = []
    try:
        for hit in DDGS().text(dork, max_results=max(1, min(num, 10)), backend=backend):
            if not isinstance(hit, dict):
                continue
            url = str(hit.get("href") or hit.get("url") or "").strip()
            if not url:
                continue
            items.append(
                {
                    "title": str(hit.get("title") or ""),
                    "url": url,
                    "snippet": str(hit.get("body") or hit.get("snippet") or ""),
                    "display_link": urlparse(url).netloc.replace("www.", ""),
                    "dork_query": dork,
                    "source": f"ddgs_{backend}",
                }
            )
    except Exception:
        return []
    return items


async def search_ddgs_web(dork: str, *, num: int = 5, pause_s: float = 0.2) -> list[dict[str, Any]]:
    """Try multiple ddgs backends — plain duckduckgo often returns empty."""
    for backend in _BACKENDS:
        hits = await asyncio.to_thread(_search_sync, dork, num=num, backend=backend)
        if hits:
            if pause_s > 0:
                await asyncio.sleep(pause_s)
            return hits
        await asyncio.sleep(0.15)
    return []
