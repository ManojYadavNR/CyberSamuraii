import json

from adapters.base import BaseAdapter
from schemas.common import ToolResult


class WhatsMyNameAdapter(BaseAdapter):
    name = "whatsmyname"
    default_timeout = 30.0

    async def _execute(self, query: str) -> ToolResult:
        tool_path = self.registry.get_tool_path(self.name)
        if not tool_path:
            return ToolResult(tool=self.name, success=False, error="WhatsMyName path not configured")

        wmn_file = tool_path / "wmn-data.json"
        if not wmn_file.exists():
            wmn_file = tool_path / "data" / "wmn-data.json"

        if not wmn_file.exists():
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"WhatsMyName dataset not found at {wmn_file}",
            )

        with open(wmn_file) as f:
            dataset = json.load(f)

        sites = dataset if isinstance(dataset, list) else dataset.get("sites", dataset.get("data", []))

        results: list[dict] = []
        for site in sites:
            if not isinstance(site, dict):
                continue
            name = site.get("name") or site.get("site") or "unknown"
            uri_check = site.get("uri_check") or site.get("uri") or site.get("url")
            if not uri_check:
                continue
            url = uri_check.replace("{account}", query)
            results.append(
                self._normalize_entry(
                    platform=name,
                    url=url,
                    extra={
                        "category": site.get("cat") or site.get("category"),
                        "check_type": "dataset_lookup",
                        "verified": False,
                    },
                )
            )

        return ToolResult(
            tool=self.name,
            success=True,
            data=results[:500],
            raw_output=f"Generated {len(results)} candidate URLs from WhatsMyName dataset",
        )
