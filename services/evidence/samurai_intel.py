"""Build Samurai social intel payload for the frontend."""

from __future__ import annotations

from typing import Any

from schemas.common import ToolResult


def _strip_local_paths(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key in ("local_path", "profile_picture_local") and isinstance(value, str):
                if value.startswith(("/", "C:", "c:")):
                    continue
            out[key] = _strip_local_paths(value)
        return out
    if isinstance(obj, list):
        return [_strip_local_paths(item) for item in obj]
    return obj


def samurai_payload_from_tool_results(tool_results: list[ToolResult] | None) -> dict[str, Any] | None:
    if not tool_results:
        return None
    for result in tool_results:
        if result.tool != "samurai" or not result.success:
            continue
        for row in result.data:
            if not isinstance(row, dict):
                continue
            if row.get("check_type") == "samurai_intel" or row.get("platform") == "samurai_intel":
                payload = {
                    "username": row.get("username"),
                    "seed_query": row.get("seed_query"),
                    "instagram": row.get("instagram"),
                    "facebook": row.get("facebook"),
                    "cross_platform": row.get("cross_platform"),
                    "facebook_slug": row.get("facebook_slug"),
                    "facebook_resolution": row.get("facebook_resolution"),
                    "instagram_error": row.get("instagram_error"),
                    "facebook_error": row.get("facebook_error"),
                }
                return _strip_local_paths(payload)
    return None


def build_samurai_social_intel(tool_results: list[ToolResult] | None) -> dict[str, Any] | None:
    payload = samurai_payload_from_tool_results(tool_results)
    if not payload:
        return None

    ig = payload.get("instagram") or {}
    fb = payload.get("facebook") or {}
    return {
        **payload,
        "has_instagram": bool(ig),
        "has_facebook": bool(fb),
        "instagram_post_count": len(ig.get("recent_posts") or []),
        "instagram_reel_count": len(ig.get("reels") or []),
        "facebook_photo_count": len(fb.get("photos") or []),
        "facebook_video_count": len((fb.get("videos") or [])) + len(fb.get("reels") or []),
    }
