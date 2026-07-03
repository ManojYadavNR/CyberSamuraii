"""Samurai — deep Instagram & Facebook profile intelligence."""

from __future__ import annotations

import asyncio
import time

from adapters.base import BaseAdapter
from adapters.scan_summary import scan_summary_entry
from schemas.common import ToolResult
from services.samurai_bridge import samurai_available, scrape_samurai


class SamuraiAdapter(BaseAdapter):
    name = "samurai"
    default_timeout = 240.0
    max_retries = 0

    def verify_tool(self) -> tuple[bool, str | None]:
        if not samurai_available():
            return False, "Samurai tool not found (expected ./samurai/main.py)"
        return True, None

    async def _execute(self, query: str) -> ToolResult:
        start = time.monotonic()
        try:
            payload = await asyncio.to_thread(scrape_samurai, query)
        except Exception as exc:
            return ToolResult(
                tool=self.name,
                success=False,
                error=str(exc),
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

        ig = payload.get("instagram") or {}
        fb = payload.get("facebook") or {}
        ig_posts = len(ig.get("recent_posts") or [])
        fb_photos = len((fb.get("photos") or []))
        fb_videos = len((fb.get("videos") or []) + (fb.get("reels") or []))

        intel_row = {
            "platform": "samurai_intel",
            "check_type": "samurai_intel",
            "source_tool": self.name,
            "username": payload.get("username"),
            "seed_query": payload.get("seed_query"),
            "facebook_slug": payload.get("facebook_slug"),
            "facebook_resolution": payload.get("facebook_resolution"),
            "instagram": payload.get("instagram"),
            "facebook": payload.get("facebook"),
            "cross_platform": payload.get("cross_platform"),
            "instagram_session_configured": payload.get("instagram_session_configured"),
            "instagram_error": payload.get("instagram_error"),
            "facebook_error": payload.get("facebook_error"),
        }

        summary = scan_summary_entry(
            self.name,
            sites_checked=2,
            sites_found=(1 if ig else 0) + (1 if fb else 0),
            note=(
                f"Instagram: {ig_posts} posts · "
                f"Facebook: {fb_photos} photos, {fb_videos} videos/reels"
            ),
        )

        return ToolResult(
            tool=self.name,
            success=True,
            data=[intel_row, summary],
            raw_output=summary.get("note"),
            execution_time_ms=(time.monotonic() - start) * 1000,
        )
