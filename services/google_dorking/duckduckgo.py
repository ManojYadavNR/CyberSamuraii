"""DuckDuckGo HTML search — free fallback when Google blocks or returns JS-only pages."""

from __future__ import annotations

import asyncio
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

DDG_SEARCH_URL = "https://html.duckduckgo.com/html/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    return unescape(TAG_RE.sub(" ", html)).strip()


def _decode_ddg_href(href: str) -> str | None:
    raw = unescape(href.strip())
    if raw.startswith("//"):
        raw = f"https:{raw}"
    if "duckduckgo.com/l/" in raw:
        parsed = urlparse(raw)
        values = parse_qs(parsed.query).get("uddg")
        if values:
            return unquote(values[0])
    if raw.startswith("http") and "duckduckgo.com" not in urlparse(raw).netloc:
        return raw
    return None


def _parse_ddg_html(html: str, dork: str, *, max_results: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for block in re.split(r'<div class="result results_links[^"]*"', html, flags=re.IGNORECASE):
        link_match = re.search(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not link_match:
            continue
        url = _decode_ddg_href(link_match.group(1))
        if not url or url in seen:
            continue
        title = _strip_tags(link_match.group(2))
        snippet_match = re.search(
            r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>',
            block,
            flags=re.DOTALL | re.IGNORECASE,
        )
        snippet = _strip_tags(snippet_match.group(1)) if snippet_match else ""
        seen.add(url)
        items.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "display_link": urlparse(url).netloc.replace("www.", ""),
                "dork_query": dork,
                "source": "duckduckgo_web",
            }
        )
        if len(items) >= max_results:
            break

    return items


async def search_duckduckgo_web(
    dork: str,
    *,
    num: int = 5,
    client: httpx.AsyncClient | None = None,
    pause_s: float = 0.8,
) -> list[dict[str, Any]]:
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=DEFAULT_HEADERS)

    try:
        assert client is not None
        response = await client.get(DDG_SEARCH_URL, params={"q": dork})
        if response.status_code != 200:
            return []
        return _parse_ddg_html(response.text, dork, max_results=num)
    except httpx.HTTPError:
        return []
    finally:
        if owns_client and client is not None:
            await client.aclose()
        if pause_s > 0:
            await asyncio.sleep(pause_s)
