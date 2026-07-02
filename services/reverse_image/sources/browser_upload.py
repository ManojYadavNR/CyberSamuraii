"""Headless browser reverse image search (Google Lens, Yandex, Bing)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.parse import parse_qs, unquote, urlparse

from schemas.reverse_image import ReverseImageMatch
from services.reverse_image.extractors import extract_platform, extract_profile_urls
from services.reverse_image.filters import is_junk_url, is_real_profile_url
from services.reverse_image.matcher import classify_match_type
from services.reverse_image.registry import register_source
from services.reverse_image.sources.common import browser_hits_to_matches, ddgs_image_search

logger = logging.getLogger(__name__)

_BROWSER_LOCK = asyncio.Lock()
_CHROME_CHANNEL = os.getenv("PLAYWRIGHT_CHROME_CHANNEL", "chrome")


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


async def _run_browser(engine: str, image_path: str, face_crop: str | None) -> list[dict]:
    if not _playwright_available():
        return []
    async with _BROWSER_LOCK:
        return await _browser_hits(engine, image_path, face_crop)


def _hits_from_yandex_links(links: list[str]) -> list[dict]:
    hits: list[dict] = []
    seen: set[str] = set()
    for link in links:
        if "/images/search" in link:
            continue
        qs = parse_qs(urlparse(link).query)
        img = (qs.get("img_url") or qs.get("imgurl") or [None])[0]
        if not img:
            continue
        img = unquote(img)
        if img in seen or is_junk_url(img):
            continue
        seen.add(img)
        hits.append({
            "url": img,
            "page_url": img,
            "title": extract_platform(img) or "",
            "snippet": "yandex_cbir",
        })
    return hits


def _hits_from_bing_html(html: str) -> list[dict]:
    hits: list[dict] = []
    seen: set[str] = set()
    patterns = [
        r'&quot;murl&quot;:&quot;(https?://[^&]+)',
        r'&quot;contentUrl&quot;:&quot;(https?://[^&]+)',
        r'"murl":"(https?://[^"\\]+)"',
        r'"contentUrl":"(https?://[^"\\]+)"',
    ]
    host_pat = r'&quot;hostPageUrl&quot;:&quot;(https?://[^&]+)'
    hosts = [unquote(u) for u in re.findall(host_pat, html)]
    for pat in patterns:
        for raw in re.findall(pat, html):
            url = unquote(raw)
            if url in seen or is_junk_url(url):
                continue
            seen.add(url)
            page = hosts[len(hits)] if len(hits) < len(hosts) else url
            hits.append({"url": url, "page_url": page, "title": extract_platform(page) or "", "snippet": "bing_visual"})
    return hits


def _hits_from_google_links(links: list[str], html: str) -> list[dict]:
    hits: list[dict] = []
    seen: set[str] = set()

    for link in links:
        if is_junk_url(link):
            continue
        if is_real_profile_url(link):
            if link not in seen:
                seen.add(link)
                hits.append({"url": link, "page_url": link, "title": extract_platform(link) or "", "snippet": "google_lens_profile"})

    for pat in (r'"ou":"(https?://[^"\\]+)"', r'"ru":"(https?://[^"\\]+)"', r'"tu":"(https?://[^"\\]+)"'):
        for url in re.findall(pat, html):
            if url in seen or is_junk_url(url):
                continue
            if not re.search(r"\.(jpg|jpeg|png|webp|gif)", url, re.I):
                continue
            seen.add(url)
            hits.append({"url": url, "page_url": url, "title": "", "snippet": "google_lens_image"})
    return hits


async def _search_yandex(image_path: str) -> list[dict]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            channel=_CHROME_CHANNEL,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 900},
            )
            await page.goto("https://yandex.ru/images/", timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            file_input = page.locator('input[type="file"]').first
            if await file_input.count() == 0:
                logger.warning("Yandex file input not found")
                return []
            await file_input.set_input_files(image_path)
            links: list[str] = []
            for _ in range(6):
                await page.wait_for_timeout(3000)
                links = await page.eval_on_selector_all(
                    'a[href]',
                    'els => els.map(e => e.href).filter(h => h.startsWith("http"))',
                )
                if any("img_url=" in l or "imgurl=" in l for l in links):
                    break
            return _hits_from_yandex_links(links)
        finally:
            await browser.close()


async def _search_bing(image_path: str) -> list[dict]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel=_CHROME_CHANNEL)
        try:
            page = await browser.new_page()
            await page.goto("https://www.bing.com/images", timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            file_input = page.locator('input[type="file"]').first
            if await file_input.count() == 0:
                logger.warning("Bing file input not found")
                return []
            await file_input.set_input_files(image_path)
            await page.wait_for_timeout(12000)
            html = await page.content()
            return _hits_from_bing_html(html)
        finally:
            await browser.close()


async def _search_google_lens(image_path: str) -> list[dict]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel=_CHROME_CHANNEL)
        try:
            page = await browser.new_page()
            await page.goto("https://www.google.com/imghp?hl=en", timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            camera = page.locator('div[aria-label="Search by image"]').first
            if await camera.count() == 0:
                return []
            async with page.expect_file_chooser(timeout=8000) as fc_info:
                await camera.click()
            fc = await fc_info.value
            await fc.set_files(image_path)
            await page.wait_for_timeout(15000)
            body = await page.inner_text("body")
            if "unusual traffic" in body.lower() or "not a robot" in body.lower():
                logger.warning("Google Lens blocked by captcha")
                return []
            links = await page.eval_on_selector_all(
                'a[href]',
                'els => els.map(e => e.href).filter(h => h.startsWith("http"))',
            )
            html = await page.content()
            return _hits_from_google_links(links, html)
        finally:
            await browser.close()


async def _browser_hits(engine: str, image_path: str, face_crop: str | None) -> list[dict]:
    search_path = face_crop if face_crop and os.path.isfile(face_crop) else image_path
    try:
        if engine == "yandex":
            return await _search_yandex(search_path)
        if engine == "bing":
            return await _search_bing(search_path)
        if engine == "google":
            return await _search_google_lens(search_path)
    except Exception as exc:
        logger.warning("Browser reverse search %s failed: %s", engine, exc)
    return []


@register_source
class YandexBrowserSource:
    name = "yandex_upload"

    async def search(self, image_path: str, image_url: str | None, *, seed_query: str, context: dict | None = None) -> list[ReverseImageMatch]:
        crop = (context or {}).get("face_crop_path")
        hits = await _run_browser(_browser_hits("yandex", image_path, str(crop) if crop else None))
        if not hits:
            hits = await _ddgs_person_fallback(image_path, context)
        if not hits:
            return []
        return await browser_hits_to_matches(
            hits, source=self.name, seed_image=image_path, seed_url=image_url,
        )


@register_source
class BingBrowserSource:
    name = "bing_upload"

    async def search(self, image_path: str, image_url: str | None, *, seed_query: str, context: dict | None = None) -> list[ReverseImageMatch]:
        crop = (context or {}).get("face_crop_path")
        hits = await _run_browser("bing", image_path, str(crop) if crop else None)
        if not hits:
            return []
        return await browser_hits_to_matches(
            hits, source=self.name, seed_image=image_path, seed_url=image_url,
        )


async def _ddgs_person_fallback(image_path: str, context: dict | None) -> list[dict]:
    ctx = context or {}
    queries = [
        "portrait headshot profile photo",
        "public account avatar picture",
        "profile portrait photo",
    ]
    if ctx.get("ocr_text"):
        queries.insert(0, f'"{str(ctx["ocr_text"])[:80]}"')
    hits: list[dict] = []
    for q in queries[:5]:
        hits.extend(await ddgs_image_search(q, num=6))
    return hits


@register_source
class GoogleLensBrowserSource:
    name = "google_lens"

    async def search(self, image_path: str, image_url: str | None, *, seed_query: str, context: dict | None = None) -> list[ReverseImageMatch]:
        crop = (context or {}).get("face_crop_path")
        hits = await _run_browser("google", image_path, str(crop) if crop else None)
        if not hits:
            hits = await _ddgs_person_fallback(image_path, context)
        if not hits:
            return []
        matches = await browser_hits_to_matches(
            hits, source=self.name, seed_image=image_path, seed_url=image_url,
        )
        out: list[ReverseImageMatch] = []
        for m in matches:
            profiles = [u for u in extract_profile_urls(m.page_url or m.match_url, m.title or "", m.snippet or "") if is_real_profile_url(u)]
            if profiles:
                m = m.model_copy(update={"profile_urls": profiles, "confidence": max(m.confidence, 0.72)})
            out.append(m)
        return out
