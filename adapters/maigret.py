import json
import re
import sys
import time
from pathlib import Path

from adapters.base import BaseAdapter
from adapters.chunk_runner import dedupe_by_url, run_two_phase_chunked
from adapters.scan_config import CHUNK_SIZE, SITE_PROBE_TIMEOUT, maigret_max_sites, scan_budget_sec
from adapters.scan_summary import scan_summary_entry
from adapters.site_lists import cap_site_list, maigret_site_names
from schemas.common import ToolResult
from services.evidence.maigret_parser import parse_maigret_payload
from services.username import safe_filename


class MaigretAdapter(BaseAdapter):
    name = "maigret"
    default_timeout = 180.0

    async def _execute(self, query: str) -> ToolResult:
        maigret_bin = self.registry.resolve_executable(self.name)
        if not maigret_bin:
            return ToolResult(tool=self.name, success=False, error="Maigret executable not found in PATH or .venv/bin")

        base_dir = Path(f"/tmp/maigret_{safe_filename(query)}")
        base_dir.mkdir(parents=True, exist_ok=True)
        site_names, priority = cap_site_list(maigret_site_names(), maigret_max_sites())
        deadline = time.monotonic() + max(25.0, scan_budget_sec() - 4.0)

        async def _run_chunk(chunk: list[str], index: int) -> tuple[list[dict], int]:
            if time.monotonic() >= deadline:
                return [], len(chunk)
            output_dir = base_dir / f"chunk_{index}"
            output_dir.mkdir(parents=True, exist_ok=True)
            cmd = [
                str(maigret_bin),
                query,
                "-J",
                "simple",
                "--folderoutput",
                str(output_dir),
                "--timeout",
                str(SITE_PROBE_TIMEOUT),
            ]
            if chunk:
                for site in chunk:
                    cmd.extend(["--site", site])

            _, stdout, _ = await self._run_subprocess(cmd)
            rows = self._parse_report_dir(output_dir, query)
            if not rows:
                rows = self._parse_stdout(stdout)
            return rows, len(chunk) if chunk else 0

        async def _on_partial(event: dict) -> None:
            await self._emit_progress(event)

        if site_names:
            results, sites_checked = await run_two_phase_chunked(
                site_names,
                priority,
                _run_chunk,
                chunk_size=CHUNK_SIZE,
                on_partial=_on_partial,
                deadline_monotonic=deadline,
            )
        else:
            results, sites_checked = await _run_chunk([], 0)

        results = dedupe_by_url(results)

        summary = scan_summary_entry(
            self.name,
            sites_checked=sites_checked,
            sites_found=len(results),
            note=f"Two-phase scan · {CHUNK_SIZE}/chunk · capped {len(site_names)} sites · {SITE_PROBE_TIMEOUT}s timeout",
        )
        return ToolResult(
            tool=self.name,
            success=True,
            data=[*results, summary],
            error=None,
            raw_output=f"{sites_checked} site(s) checked, {len(results)} hit(s)",
        )

    def _parse_report_dir(self, output_dir: Path, query: str) -> list[dict]:
        results: list[dict] = []
        report_file = output_dir / f"report_{query}_simple.json"
        if not report_file.exists():
            matches = list(output_dir.glob("report_*_simple.json"))
            report_file = matches[0] if matches else report_file

        try:
            if not report_file.exists():
                return results
            with open(report_file) as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                return results
            for site, info in raw.items():
                if not isinstance(info, dict):
                    continue
                status = info.get("status", {})
                claimed = isinstance(status, dict) and status.get("status") == "Claimed"
                url = info.get("url_user") or info.get("url")
                if url and claimed:
                    profile_fields = parse_maigret_payload(info)
                    extra = {
                        **info,
                        **profile_fields,
                        "verified": False,
                        "check_type": "live_scan",
                        "status": "maigret_claimed",
                    }
                    results.append(self._normalize_entry(platform=site, url=url, extra=extra))
        except (json.JSONDecodeError, OSError):
            pass
        return results

    def _parse_stdout(self, stdout: str) -> list[dict]:
        results: list[dict] = []
        for line in stdout.splitlines():
            match = re.search(r"\[\+\]\s+(.+?):\s+(https?://\S+)", line)
            if match:
                results.append(
                    self._normalize_entry(platform=match.group(1).strip(), url=match.group(2))
                )
        return results
