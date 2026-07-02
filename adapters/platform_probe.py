"""Built-in adapter — fast direct HTTP checks on major social platforms."""

from __future__ import annotations

import time

from adapters.base import BaseAdapter
from adapters.scan_summary import scan_summary_entry
from schemas.common import ToolResult
from services.platform_probe import probe_priority_platforms


class PlatformProbeAdapter(BaseAdapter):
    name = "platform_probe"
    default_timeout = 35.0
    max_retries = 0

    def verify_tool(self) -> tuple[bool, str | None]:
        return True, None

    async def run(self, query: str, timeout: float | None = None, on_progress=None) -> ToolResult:
        """Use internal budget so partial hits survive outer orchestrator timeouts."""
        start = time.monotonic()
        self._on_progress = on_progress
        budget = min(float(timeout or self.default_timeout) - 2.0, 30.0)
        budget = max(budget, 12.0)
        try:
            result = await self._execute(query, budget_sec=budget)
            result.execution_time_ms = (time.monotonic() - start) * 1000
            return result
        except Exception as exc:
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Tool '{self.name}' failed: {type(exc).__name__}: {exc}",
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

    async def _execute(self, query: str, *, budget_sec: float = 28.0) -> ToolResult:
        hits, checked = await probe_priority_platforms(query, budget_sec=budget_sec)
        summary = scan_summary_entry(
            self.name,
            sites_checked=checked,
            sites_found=len(hits),
            note=f"Direct HTTP probe · {checked} major platforms",
        )
        return ToolResult(
            tool=self.name,
            success=True,
            data=[*hits, summary],
            raw_output=f"{checked} platform(s) probed, {len(hits)} live hit(s)",
            error=None,
        )
