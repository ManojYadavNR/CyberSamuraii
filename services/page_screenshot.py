"""Headless page screenshots when og:image / avatar URLs are unavailable."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.parse import urlparse

from services.screenshot_store import load_cached_screenshot, save_screenshot

logger = logging.getLogger(__name__)

_SCREENSHOT_LOCK = asyncio.Lock()
_PROFILE_CAPTURED = 0
_LEAD_CAPTURED = 0
_CHROME_CHANNEL = os.getenv("PLAYWRIGHT_CHROME_CHANNEL", "chrome")
MAX_PROFILE_SCREENSHOTS = max(0, int(os.getenv("MAX_PROFILE_SCREENSHOTS", "3")))
MAX_LEAD_SCREENSHOTS = max(0, int(os.getenv("MAX_LEAD_SCREENSHOTS", "18")))
SCREENSHOT_TIMEOUT_MS = max(5000, int(os.getenv("SCREENSHOT_TIMEOUT_MS", "18000")))
SCREENSHOT_VIEWPORT = {"width": 1280, "height": 900}
SKIP_HOSTS = frozenset({"localhost", "127.0.0.1"})
BAD_SCREENSHOT_TITLE = re.compile(
    r"sign in|log in|login|verify|verification|checkpoint|security check|"
    r"create an account|join facebook|access denied|just a moment|confirm your identity|"
    r"two-factor|captcha",
    re.I,
)
PROFILE_HOME_RE = re.compile(
    r"github\.com/[^/]+/?$|instagram\.com/[^/]+/?$|facebook\.com/[^/]+/?$|"
    r"linkedin\.com/in/[^/]+/?$|twitter\.com/[^/]+/?$|x\.com/[^/]+/?$",
    re.I,
)


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def screenshots_enabled() -> bool:
    return os.getenv("PAGE_SCREENSHOTS_ENABLED", "true").lower() in ("1", "true", "yes")


def _should_skip_url(url: str) -> bool:
    if not url.startswith("http"):
        return True
    low = url.lower()
    if re.search(r"/login(?:[/?]|$)|/signin(?:[/?]|$)|/auth(?:[/?]|$)|/checkpoint", low):
        return True
    if re.search(r"/(?:verify|verification|confirm|challenge)(?:[/?]|$)", low):
        return True
    if any(ext in low.split("?", 1)[0] for ext in (".pdf", ".zip", ".mp4", ".mp3", ".exe")):
        return True
    host = (urlparse(url).hostname or "").lower()
    if host in SKIP_HOSTS:
        return True
    return False


def _is_bad_screenshot_page(title: str, url: str) -> bool:
    if BAD_SCREENSHOT_TITLE.search(title or ""):
        return True
    low = (url or "").lower()
    if "/login" in low or "/checkpoint" in low or "/verify" in low:
        return True
    return False


def reset_screenshot_budget() -> None:
    global _PROFILE_CAPTURED, _LEAD_CAPTURED
    _PROFILE_CAPTURED = 0
    _LEAD_CAPTURED = 0


def _budget_remaining(budget: str) -> bool:
    if budget == "profile":
        return _PROFILE_CAPTURED < MAX_PROFILE_SCREENSHOTS
    return _LEAD_CAPTURED < MAX_LEAD_SCREENSHOTS


def _increment_budget(budget: str) -> None:
    global _PROFILE_CAPTURED, _LEAD_CAPTURED
    if budget == "profile":
        _PROFILE_CAPTURED += 1
    else:
        _LEAD_CAPTURED += 1


async def capture_page_screenshot(url: str, *, budget: str = "lead") -> str | None:
    """
    Capture a PNG preview of a public page.
    budget: 'lead' (hackathon/news) or 'profile' (verified accounts).
    """
    if not screenshots_enabled() or not url or _should_skip_url(url):
        return None

    cached = load_cached_screenshot(url)
    if cached:
        return cached

    if not _budget_remaining(budget):
        return None

    if not _playwright_available():
        return None

    async with _SCREENSHOT_LOCK:
        cached = load_cached_screenshot(url)
        if cached:
            return cached
        if not _budget_remaining(budget):
            return None
        try:
            png = await _capture_png(url)
            if not png:
                return None
            saved = save_screenshot(png, url=url)
            _increment_budget(budget)
            return saved["preview_url"]
        except Exception as exc:
            logger.warning("Screenshot failed for %s: %s", url, exc)
            return None


async def _capture_png(url: str) -> bytes | None:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel=_CHROME_CHANNEL)
        try:
            page = await browser.new_page(viewport=SCREENSHOT_VIEWPORT)
            await page.goto(url, wait_until="domcontentloaded", timeout=SCREENSHOT_TIMEOUT_MS)
            await page.wait_for_timeout(1200)
            title = await page.title()
            body_text = ""
            try:
                body_text = await page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 800)")
            except Exception:
                pass
            if _is_bad_screenshot_page(title, url) or _is_bad_screenshot_page(body_text, url):
                logger.info("Skipping bad screenshot page for %s (title=%r)", url, (title or "")[:80])
                return None
            return await page.screenshot(type="png", full_page=False)
        finally:
            await browser.close()
