import re
import sys
import time

from adapters.base import BaseAdapter
from adapters.chunk_runner import dedupe_by_url, run_two_phase_chunked
from adapters.scan_config import CHUNK_SIZE, SITE_PROBE_TIMEOUT, scan_budget_sec, sherlock_max_sites
from adapters.scan_summary import scan_summary_entry
from adapters.site_lists import cap_site_list, sherlock_site_names
from schemas.common import ToolResult


class SherlockAdapter(BaseAdapter):
    name = "sherlock"
    default_timeout = 180.0

    async def _execute(self, query: str) -> ToolResult:
        tool_path = self.registry.get_executable_path(self.name)
        if not tool_path or not tool_path.exists():
            return ToolResult(tool=self.name, success=False, error="Sherlock executable not found")

        raw_sites = sherlock_site_names()
        if not raw_sites:
            site_names, priority = [""], []
        else:
            site_names, priority = cap_site_list(raw_sites, sherlock_max_sites())

        deadline = time.monotonic() + max(25.0, scan_budget_sec() - 4.0)

        async def _run_chunk(chunk: list[str], _index: int) -> tuple[list[dict], int]:
            if time.monotonic() >= deadline:
                return [], len(chunk) if chunk else 0
            if not chunk or chunk == [""]:
                cmd = [
                    sys.executable,
                    str(tool_path),
                    query,
                    "--print-found",
                    "--timeout",
                    str(SITE_PROBE_TIMEOUT),
                    "--local",
                ]
                _, stdout, _ = await self._run_subprocess(cmd)
                return self._parse_stdout(stdout), min(len(raw_sites) if raw_sites else 482, sherlock_max_sites() or 482)

            cmd = [
                sys.executable,
                str(tool_path),
                query,
                "--print-found",
                "--timeout",
                str(SITE_PROBE_TIMEOUT),
                "--local",
            ]
            for site in chunk:
                cmd.extend(["--site", site])
            _, stdout, _ = await self._run_subprocess(cmd)
            return self._parse_stdout(stdout), len(chunk)

        async def _on_partial(event: dict) -> None:
            await self._emit_progress(event)

        if site_names and site_names != [""]:
            results, sites_checked = await run_two_phase_chunked(
                site_names,
                priority,
                _run_chunk,
                chunk_size=CHUNK_SIZE,
                on_partial=_on_partial,
                deadline_monotonic=deadline,
            )
        else:
            results, sites_checked = await _run_chunk([""], 0)

        results = dedupe_by_url(results)

        summary = scan_summary_entry(
            self.name,
            sites_checked=sites_checked,
            sites_found=len(results),
            note=f"Two-phase scan · {CHUNK_SIZE}/chunk · capped {len(site_names) if site_names != [''] else 'all'} sites",
        )
        payload = [*results, summary]

        return ToolResult(
            tool=self.name,
            success=True,
            data=payload,
            error=None,
            raw_output=f"{sites_checked} site(s) checked, {len(results)} hit(s)",
        )

    def _parse_stdout(self, stdout: str) -> list[dict]:
        results: list[dict] = []
        for line in stdout.splitlines():
            match = re.search(r"\[\+\]\s+(.+?):\s+(https?://\S+)", line)
            if match:
                results.append(
                    self._normalize_entry(
                        platform=match.group(1).strip(),
                        url=match.group(2),
                        extra={
                            "verified": False,
                            "check_type": "username_probe",
                            "status": "unconfirmed",
                        },
                    )
                )
        return results
