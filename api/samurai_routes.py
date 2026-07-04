import re

from fastapi import APIRouter, Depends, HTTPException

from api.deps import require_permission
from schemas.samurai import (
    InstagramCommentsRequest,
    InstagramCommentsResponse,
    InstagramTimelineRequest,
    InstagramTimelineResponse,
    InstagramTopCommentersRequest,
    InstagramTopCommentersResponse,
)
from services.apify.instagram_comments import (
    apify_configured,
    fetch_instagram_comments,
    fetch_profile_comment_statistics,
)
from services.apify.instagram_timeline import fetch_instagram_timeline

router = APIRouter(prefix="/api/samurai", tags=["samurai"])

_view = require_permission("view_investigations")


@router.get("/instagram-comments/status")
async def instagram_comments_status(user=Depends(_view)):
    return {"configured": apify_configured()}


@router.post("/instagram-comments", response_model=InstagramCommentsResponse)
async def instagram_comments(request: InstagramCommentsRequest, user=Depends(_view)):
    if not apify_configured():
        raise HTTPException(
            status_code=503,
            detail="APIFY_API_TOKEN is not configured. Add it to .env and restart the backend.",
        )
    result = await fetch_instagram_comments(
        request.url,
        results_limit=request.results_limit,
        include_replies=request.include_replies,
    )
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "Apify scrape failed")
    return InstagramCommentsResponse(**result)


@router.post("/instagram-top-commenters", response_model=InstagramTopCommentersResponse)
async def instagram_top_commenters(request: InstagramTopCommentersRequest, user=Depends(_view)):
    if not apify_configured():
        raise HTTPException(
            status_code=503,
            detail="APIFY_API_TOKEN is not configured. Add it to .env and restart the backend.",
        )
    result = await fetch_profile_comment_statistics(
        request.urls,
        profile_username=request.profile_username,
        results_limit=request.results_limit,
        include_replies=request.include_replies,
        top_n=request.top_n,
    )
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "Comment statistics failed")
    return InstagramTopCommentersResponse(**result)


@router.post("/instagram-timeline", response_model=InstagramTimelineResponse)
async def instagram_timeline(request: InstagramTimelineRequest, user=Depends(_view)):
    if not apify_configured():
        raise HTTPException(
            status_code=503,
            detail="APIFY_API_TOKEN is not configured. Add it to .env and restart the backend.",
        )
    result = await fetch_instagram_timeline(
        request.username,
        results_limit=request.results_limit,
        skip_pinned=request.skip_pinned,
        data_detail_level=request.data_detail_level,
    )
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "Timeline fetch failed")
    return InstagramTimelineResponse(**result)


@router.get("/instagram-media/{shortcode}")
async def instagram_media(shortcode: str, user=Depends(_view)):
    """Resolve direct CDN video/thumbnail for a post or reel (in-app playback)."""
    import asyncio

    from samurai.main import fetch_post_details

    code = (shortcode or "").strip()
    if not code or not re.match(r"^[A-Za-z0-9_-]+$", code):
        raise HTTPException(status_code=400, detail="Invalid shortcode")

    details = await asyncio.get_running_loop().run_in_executor(None, fetch_post_details, code)
    if not details:
        raise HTTPException(status_code=404, detail="Could not resolve media for this post")

    video_url = details.get("video_url")
    display_url = details.get("display_url")
    if not video_url and not display_url:
        raise HTTPException(status_code=404, detail="No playable media URL found")

    return {
        "shortcode": code,
        "video_url": video_url,
        "display_url": display_url,
        "type": details.get("type"),
        "is_video": bool(details.get("is_video") or details.get("type") in ("Video", "Reel")),
    }
