import json
import re
from pathlib import Path

from adapters.base import BaseAdapter
from schemas.common import ToolResult
from services.username import safe_filename


class MaigretAdapter(BaseAdapter):
    name = "maigret"
    default_timeout = 180.0

    async def _execute(self, query: str) -> ToolResult:
        output_dir = Path(f"/tmp/maigret_{safe_filename(query)}")
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "maigret",
            query,
            "-J",
            "simple",
            "--folderoutput",
            str(output_dir),
            "--timeout",
            "10",
        ]

        returncode, stdout, stderr = await self._run_subprocess(cmd)

        results: list[dict] = []
        report_file = output_dir / f"report_{query}_simple.json"
        if not report_file.exists():
            matches = list(output_dir.glob("report_*_simple.json"))
            report_file = matches[0] if matches else report_file

        try:
            if report_file.exists():
                with open(report_file) as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    for site, info in raw.items():
                        if not isinstance(info, dict):
                            continue
                        status = info.get("status", {})
                        claimed = isinstance(status, dict) and status.get("status") == "Claimed"
                        url = info.get("url_user") or info.get("url")
                        if url and claimed:
                            results.append(
                                self._normalize_entry(platform=site, url=url, extra=info)
                            )
        except (json.JSONDecodeError, OSError):
            pass

        if not results:
            for line in stdout.splitlines():
                match = re.search(r"\[\+\]\s+(.+?):\s+(https?://\S+)", line)
                if match:
                    results.append(
                        self._normalize_entry(platform=match.group(1).strip(), url=match.group(2))
                    )

        success = len(results) > 0
        return ToolResult(
            tool=self.name,
            success=success,
            data=results,
            error=None if success else stderr[:500] or "No results found",
            raw_output=stdout[:2000],
        )
