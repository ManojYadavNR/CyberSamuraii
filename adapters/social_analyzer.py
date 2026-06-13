import json
import re
from urllib.parse import urlparse

from adapters.base import BaseAdapter
from schemas.common import ToolResult


class SocialAnalyzerAdapter(BaseAdapter):
    name = "social_analyzer"
    default_timeout = 120.0

    async def _execute(self, query: str) -> ToolResult:
        tool_path = self.registry.get_tool_path(self.name)
        if not tool_path:
            return ToolResult(tool=self.name, success=False, error="SocialAnalyzer path not configured")

        cli_script = tool_path / "app.py"
        if cli_script.exists():
            cmd = [
                "python3",
                str(cli_script),
                "--username",
                query,
                "--output",
                "json",
                "--method",
                "find",
                "--top",
                "50",
            ]
            returncode, stdout, stderr = await self._run_subprocess(cmd, cwd=str(tool_path))
            if "ModuleNotFoundError" in stderr or "No module named" in stderr:
                return await self._dataset_lookup(query, tool_path)
        else:
            return await self._dataset_lookup(query, tool_path)

        results = self._parse_live_output(stdout)
        if not results and stderr:
            results = self._parse_live_output(stderr)

        success = len(results) > 0
        return ToolResult(
            tool=self.name,
            success=success,
            data=results,
            error=None if success else stderr[:500] or stdout[:500] or "No results",
            raw_output=(stdout or stderr)[:2000],
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
                            extra={"verified": True, "check_type": "live_scan"},
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
                        "status": item.get("status"),
                        "language": item.get("language"),
                        "verified": True,
                        "check_type": "live_scan",
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

    async def _dataset_lookup(self, query: str, tool_path) -> ToolResult:
        data_file = tool_path / "data" / "sites.json"
        if not data_file.exists():
            data_file = tool_path / "sites.json"

        if not data_file.exists():
            return ToolResult(
                tool=self.name,
                success=False,
                error="SocialAnalyzer dataset not found",
            )

        with open(data_file) as f:
            sites = json.load(f)

        results: list[dict] = []
        if isinstance(sites, list):
            site_list = sites
        else:
            site_list = sites.get("websites_entries", sites.get("sites", []))
        for site in site_list:
            if not isinstance(site, dict):
                continue
            url_template = site.get("url") or site.get("uri_check")
            if url_template:
                url = url_template.replace("{username}", query).replace("{account}", query)
                results.append(
                    self._normalize_entry(
                        platform=site.get("name", "unknown"),
                        url=url,
                        extra={"check_type": "dataset_lookup", "verified": False},
                    )
                )

        return ToolResult(
            tool=self.name,
            success=len(results) > 0,
            data=results[:300],
            error=None if results else "Dataset lookup produced no candidates",
            raw_output=f"Dataset lookup: {len(results)} candidates",
        )
