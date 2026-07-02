"""Direct Google web search — no API key required."""

from __future__ import annotations

import asyncio
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx

GOOGLE_SEARCH_URL = "https://www.google.com/search"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

BLOCKED_MARKERS = (
    "unusual traffic",
    "captcha",
    "recaptcha",
    "detected unusual",
    "sorry/index",
)

TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    return unescape(TAG_RE.sub("", html)).strip()


def _decode_href(href: str) -> str | None:
    raw = unescape(href.strip())
    if raw.startswith("/url?"):
        parsed = urlparse(raw)
        for key in ("q", "url"):
            values = parse_qs(parsed.query).get(key)
            if values and values[0].startswith("http"):
                return values[0]
        return None
    if raw.startswith("http") and "google." not in urlparse(raw).netloc:
        return raw
    return None


def _parse_google_html(html: str, dork: str, *, max_results: int) -> list[dict[str, Any]]:
    if any(marker in html.lower() for marker in BLOCKED_MARKERS):
        return []

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Pattern 1: classic /url?q= redirect links with h3 titles
    for match in re.finditer(
        r'<a[^>]+href="(/url\?[^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        url = _decode_href(match.group(1))
        if not url or url in seen:
            continue
        title = _strip_tags(match.group(2))
        seen.add(url)
        items.append(
            {
                "title": title,
                "url": url,
                "snippet": "",
                "display_link": urlparse(url).netloc.replace("www.", ""),
                "dork_query": dork,
                "source": "google_web",
            }
        )
        if len(items) >= max_results:
            return items

    # Pattern 2: direct https links near h3 (newer layouts)
    for match in re.finditer(
        r'<a[^>]+href="(https?://[^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        url = _decode_href(match.group(1))
        if not url or url in seen:
            continue
        title = _strip_tags(match.group(2))
        seen.add(url)
        items.append(
            {
                "title": title,
                "url": url,
                "snippet": "",
                "display_link": urlparse(url).netloc.replace("www.", ""),
                "dork_query": dork,
                "source": "google_web",
            }
        )
        if len(items) >= max_results:
            return items

    # Pattern 3: fallback — any decoded /url?q= links
    for match in re.finditer(r'href="(/url\?[^"]+)"', html, flags=re.IGNORECASE):
        url = _decode_href(match.group(1))
        if not url or url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "title": "",
                "url": url,
                "snippet": "",
                "display_link": urlparse(url).netloc.replace("www.", ""),
                "dork_query": dork,
                "source": "google_web",
            }
        )
        if len(items) >= max_results:
            break

    return items


async def search_google_web(
    dork: str,
    *,
    num: int = 5,
    client: httpx.AsyncClient | None = None,
    pause_s: float = 1.2,
) -> list[dict[str, Any]]:
    """Fetch google.com/search and parse public result links."""
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=DEFAULT_HEADERS)

    try:
        assert client is not None
        params = {"q": dork, "num": str(max(1, min(num, 10))), "hl": "en"}
        response = await client.get(GOOGLE_SEARCH_URL, params=params)
        if response.status_code != 200:
            return []
        return _parse_google_html(response.text, dork, max_results=num)
    except httpx.HTTPError:
        return []
    finally:
        if owns_client and client is not None:
            await client.aclose()
        if pause_s > 0:
            await asyncio.sleep(pause_s)
