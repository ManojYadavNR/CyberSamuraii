"""Resolve a visual preview for a page URL."""

from __future__ import annotations

from services.evidence.platform_deep import _fetch_og_thumbnail
from services.page_screenshot import capture_page_screenshot


async def resolve_page_visual(url: str, *, budget: str = "lead") -> dict[str, str]:
    if not url or not url.startswith("http"):
        return {}

    out: dict[str, str] = {"source_url": url}
    try:
        thumb = await _fetch_og_thumbnail(url)
    except Exception:
        thumb = None
    if thumb:
        out["image_url"] = thumb
        return out

    try:
        preview = await capture_page_screenshot(url, budget=budget)
    except Exception:
        preview = None
    if preview:
        out["screenshot_url"] = preview
    return out
