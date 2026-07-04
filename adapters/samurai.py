"""Samurai — deep Instagram & Facebook profile intelligence."""

from __future__ import annotations

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from adapters.base import BaseAdapter
from adapters.scan_summary import scan_summary_entry
from schemas.common import ToolResult
from services.samurai_bridge import samurai_available, scrape_samurai


class SamuraiAdapter(BaseAdapter):
    name = "samurai"
    default_timeout = 120.0
    max_retries = 0

    def verify_tool(self) -> tuple[bool, str | None]:
        if not samurai_available():
            return False, "Samurai tool not found (expected ./samurai/main.py)"
        return True, None

    async def _execute(self, query: str) -> ToolResult:
        """Always return within SAMURAI_WALL_SEC — never hang the investigation."""
        start = time.monotonic()
        wall = float(os.getenv("SAMURAI_WALL_SEC", "120"))
        budget = max(25.0, wall - 3.0)
        deadline = start + budget

        last_detail = "Collecting Instagram & Facebook…"
        progress_q: asyncio.Queue[str] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _on_progress(detail: str) -> None:
            try:
                loop.call_soon_threadsafe(progress_q.put_nowait, detail)
            except Exception:
                pass

        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="samurai-job")
        future = pool.submit(
            scrape_samurai,
            query,
            on_progress=_on_progress,
            deadline=deadline,
        )

        # Non-blocking progress tick — never let emit block the deadline.
        async def _safe_emit(detail: str) -> None:
            nonlocal last_detail
            last_detail = detail
            try:
                await asyncio.wait_for(
                    self._emit_progress({"status": "running", "detail": detail}),
                    timeout=0.4,
                )
            except Exception:
                pass

        await _safe_emit(last_detail)

        payload: dict | None = None
        error: str | None = None
        try:
            while not future.done():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    detail = await asyncio.wait_for(
                        progress_q.get(),
                        timeout=min(1.5, remaining),
                    )
                    await _safe_emit(detail)
                except asyncio.TimeoutError:
                    await _safe_emit(last_detail)

            if future.done():
                try:
                    payload = future.result(timeout=0)
                except Exception as exc:
                    error = str(exc)
            else:
                # Hard stop — do not wait for hung HTTP threads.
                error = f"Samurai stopped at {budget:.0f}s budget"
                try:
                    payload = future.result(timeout=0.2)
                except (FuturesTimeoutError, Exception):
                    payload = None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        if payload and (payload.get("instagram") or payload.get("facebook")):
            return self._to_tool_result(payload, start)

        return ToolResult(
            tool=self.name,
            success=False,
            error=error or "Samurai returned no data",
            execution_time_ms=(time.monotonic() - start) * 1000,
        )

    def _to_tool_result(self, payload: dict, start: float) -> ToolResult:
        ig = payload.get("instagram") or {}
        fb = payload.get("facebook") or {}
        ig_posts = len(ig.get("recent_posts") or ig.get("posts") or [])
        fb_photos = len(fb.get("photos") or [])
        fb_videos = len((fb.get("videos") or []) + (fb.get("reels") or []))
        prof = ig.get("profile") or {}

        intel_row = {
            "platform": "samurai_intel",
            "check_type": "samurai_intel",
            "source_tool": self.name,
            "username": payload.get("username") or prof.get("username"),
            "seed_query": payload.get("seed_query"),
            "facebook_slug": payload.get("facebook_slug"),
            "facebook_resolution": payload.get("facebook_resolution"),
            "instagram": payload.get("instagram"),
            "facebook": payload.get("facebook"),
            "cross_platform": payload.get("cross_platform"),
            "instagram_session_configured": payload.get("instagram_session_configured"),
            "instagram_error": payload.get("instagram_error"),
            "facebook_error": payload.get("facebook_error"),
            "partial": bool(payload.get("partial")),
        }

        fb_similar = len(fb.get("similar_profiles") or [])
        fb_about = len(fb.get("personal_details") or {})
        note = (
            f"Instagram: {ig_posts} posts · "
            f"Facebook: {fb_photos} photos, {fb_videos} videos/reels"
        )
        if fb_similar:
            note += f", {fb_similar} similar"
        if fb_about:
            note += f", {fb_about} about fields"
        # Only label partial when Facebook itself is still a stub / empty.
        fb_rich = bool(fb) and not fb.get("embed_only") and (
            fb_photos > 0 or fb_about > 0 or fb_similar > 0
        )
        if payload.get("partial") and not fb_rich:
            note += " · partial (time budget)"

        summary = scan_summary_entry(
            self.name,
            sites_checked=2,
            sites_found=(1 if ig else 0) + (1 if fb else 0),
            note=note,
        )

        return ToolResult(
            tool=self.name,
            success=True,
            data=[intel_row, summary],
            raw_output=summary.get("note"),
            execution_time_ms=(time.monotonic() - start) * 1000,
        )
