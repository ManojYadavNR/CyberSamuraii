import asyncio
import json
import re
import sys
import time
from urllib.parse import urlparse

from adapters.base import BaseAdapter
from adapters.chunk_runner import dedupe_by_url, run_two_phase_chunked
from adapters.scan_config import (
    SOCIAL_ANALYZER_BUDGET_SEC,
    SOCIAL_ANALYZER_CHUNK_SIZE,
    SITE_PROBE_TIMEOUT,
    social_analyzer_max_sites,
    social_analyzer_phase2_parallel,
)
from adapters.scan_summary import scan_summary_entry
from adapters.site_lists import cap_site_list, social_analyzer_site_tokens
from schemas.common import ToolResult


class SocialAnalyzerAdapter(BaseAdapter):
    name = "social_analyzer"
    default_timeout = SOCIAL_ANALYZER_BUDGET_SEC
    max_retries = 0

    def __init__(self) -> None:
        super().__init__()
        self._partial_results: list[dict] = []
        self._sites_checked = 0
        self._deadline: float | None = None

    async def run(
        self,
        query: str,
        timeout: float | None = None,
        on_progress=None,
    ) -> ToolResult:
        """Run with partial-result preservation when the wall budget is hit."""
        timeout = timeout or self.default_timeout
        start = time.monotonic()
        self._on_progress = on_progress
        self._partial_results = []
        self._sites_checked = 0
        self._deadline = time.monotonic() + max(20.0, float(timeout) - 3.0)

        ok, error = self.verify_tool()
        if not ok:
            return ToolResult(
                tool=self.name,
                success=False,
                error=error,
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

        try:
            result = await asyncio.wait_for(self._execute(query), timeout=timeout)
            result.execution_time_ms = (time.monotonic() - start) * 1000
            return result
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            partial = self._partial_tool_result()
            if partial:
                partial.execution_time_ms = (time.monotonic() - start) * 1000
                return partial
            if isinstance(exc, asyncio.CancelledError):
                raise
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Tool '{self.name}' timed out after {timeout}s",
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

    def _partial_tool_result(self) -> ToolResult | None:
        if not self._partial_results:
            return None
        summary = scan_summary_entry(
            self.name,
            sites_checked=self._sites_checked,
            sites_found=len(self._partial_results),
            note="Partial scan preserved after time budget",
        )
        return ToolResult(
            tool=self.name,
            success=True,
            data=[*self._partial_results, summary],
            raw_output=f"{self._sites_checked} site(s) checked, {len(self._partial_results)} hit(s) (partial)",
        )

    async def _execute(self, query: str) -> ToolResult:
        tool_path = self.registry.get_tool_path(self.name)
        if not tool_path:
            return ToolResult(tool=self.name, success=False, error="SocialAnalyzer path not configured")

        cli_script = tool_path / "app.py"
        if not cli_script.exists():
            return ToolResult(tool=self.name, success=False, error="SocialAnalyzer CLI not found")

        site_tokens, priority = cap_site_list(social_analyzer_site_tokens(), social_analyzer_max_sites())

        async def _run_chunk(chunk: list[str], _index: int) -> tuple[list[dict], int]:
            if self._deadline and time.monotonic() >= self._deadline:
                return [], len(chunk)
            websites_arg = " ".join(chunk) if chunk else "all"
            cmd = [
                sys.executable,
                str(cli_script),
                "--username",
                query,
                "--websites",
                websites_arg,
                "--output",
                "json",
                "--method",
                "find",
                "--timeout",
                str(max(1, SITE_PROBE_TIMEOUT - 3)),
            ]
            _, stdout, stderr = await self._run_subprocess(cmd, cwd=str(tool_path))
            if "ModuleNotFoundError" in stderr or "No module named" in stderr:
                return [], 0
            rows = self._parse_live_output(stdout)
            if not rows and stderr:
                rows = self._parse_live_output(stderr)
            return rows, len(chunk) if chunk else len(site_tokens)

        async def _on_partial(event: dict) -> None:
            snapshot = event.get("results_snapshot")
            if isinstance(snapshot, list) and snapshot:
                self._partial_results = dedupe_by_url([*self._partial_results, *snapshot])[-200:]
            if event.get("sites_checked") is not None:
                self._sites_checked = int(event["sites_checked"])
            await self._emit_progress(event)

        if site_tokens:
            results, sites_checked = await run_two_phase_chunked(
                site_tokens,
                priority,
                _run_chunk,
                chunk_size=SOCIAL_ANALYZER_CHUNK_SIZE,
                phase2_parallel_count=social_analyzer_phase2_parallel(),
                on_partial=_on_partial,
                deadline_monotonic=self._deadline,
            )
        else:
            results, sites_checked = await _run_chunk([], 0)

        results = dedupe_by_url(results)
        self._partial_results = results
        self._sites_checked = sites_checked

        summary = scan_summary_entry(
            self.name,
            sites_checked=sites_checked,
            sites_found=len(results),
            note=f"Two-phase scan · {SOCIAL_ANALYZER_CHUNK_SIZE}/chunk · capped {len(site_tokens)} sites",
        )
        payload = [*results, summary]

        return ToolResult(
            tool=self.name,
            success=True,
            data=payload,
            error=None,
            raw_output=f"{sites_checked} site(s) checked, {len(results)} hit(s)",
        )

    def _parse_live_output(self, output: str) -> list[dict]:
        results: list[dict] = []
        payload = output.strip()
        if not payload:
            return results

        json_start = payload.find("{")
        if json_start > 0:
            payload = payload[json_start:]

        try:
            raw = json.loads(payload)
        except json.JSONDecodeError:
            for line in output.splitlines():
                match = re.search(r"(https?://\S+)", line)
                if match:
                    results.append(
                        self._normalize_entry(
                            platform="social_analyzer",
                            url=match.group(1),
                            extra={"verified": False, "check_type": "live_scan"},
                        )
                    )
            return results

        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = []
            for section in ("detected", "unknown"):
                section_items = raw.get(section, [])
                if isinstance(section_items, list):
                    items.extend(section_items)
        else:
            return results

        for item in items:
            if not isinstance(item, dict):
                continue
            url = item.get("link") or item.get("url")
            if not url:
                continue
            platform = self._platform_name(item, url)
            results.append(
                self._normalize_entry(
                    platform=platform,
                    url=url,
                    extra={
                        "country": item.get("country"),
                        "rank": item.get("rank"),
                        "rate": item.get("rate"),
                        "detection_status": item.get("status"),
                        "language": item.get("language"),
                        "verified": False,
                        "check_type": "live_scan",
                        "status": "social_analyzer_detected",
                    },
                )
            )
        return results

    def _platform_name(self, item: dict, url: str) -> str:
        for field in ("title", "text", "type"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                cleaned = value.split("·")[0].split("|")[0].strip()
                if 0 < len(cleaned) <= 80:
                    return cleaned
        host = urlparse(url).netloc.replace("www.", "")
        return host or "unknown"
