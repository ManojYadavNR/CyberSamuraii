"""Resolve og:image, YouTube thumb, or screenshot for a lead URL."""

from __future__ import annotations

from services.evidence.platform_deep import _fetch_og_thumbnail
from services.lead_visual.youtube import youtube_thumbnail
from services.page_screenshot import capture_page_screenshot


async def resolve_lead_visual(
    url: str,
    *,
    lead_type: str,
    allow_screenshot: bool = True,
) -> tuple[str | None, str | None, str]:
    """
    Returns (image_url, thumbnail_url, visual_source).
    Uses lead screenshot budget for page captures.
    """
    if lead_type == "video":
        thumb = youtube_thumbnail(url)
        if thumb:
            return thumb, thumb, "youtube_thumb"

    if lead_type == "profile":
        try:
            from services.evidence.platform_deep import deep_fetch_profile

            payload = await deep_fetch_profile(url)
            avatar = payload.get("avatar_url") if isinstance(payload, dict) else None
            if isinstance(avatar, str) and avatar.startswith("http"):
                return avatar, avatar, "profile_avatar"
        except Exception:
            pass

    try:
        og = await _fetch_og_thumbnail(url)
    except Exception:
        og = None
    if og:
        return og, og, "og_image"

    if allow_screenshot and lead_type in (
        "hackathon", "event", "news", "college", "article", "achievement", "mention",
    ):
        try:
            shot = await capture_page_screenshot(url, budget="lead")
        except Exception:
            shot = None
        if shot:
            return shot, shot, "page_screenshot"

    return None, None, ""
