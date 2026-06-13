import json

from adapters.base import BaseAdapter
from schemas.common import ToolResult


class SpiderFootAdapter(BaseAdapter):
    name = "spiderfoot"
    default_timeout = 180.0

    MODULES_EMAIL = [
        "sfp_email",
        "sfp_haveibeenpwned",
        "sfp_hunter",
        "sfp_clearbit",
    ]
    MODULES_DOMAIN = [
        "sfp_dnsresolve",
        "sfp_subdomain",
        "sfp_ssl",
        "sfp_whois",
        "sfp_shodan",
    ]

    async def _execute(self, query: str) -> ToolResult:
        tool_path = self.registry.get_executable_path(self.name)
        if not tool_path or not tool_path.exists():
            return ToolResult(tool=self.name, success=False, error="SpiderFoot executable not found")

        tool_dir = tool_path.parent
        is_email = "@" in query
        modules = self.MODULES_EMAIL if is_email else self.MODULES_DOMAIN
        module_str = ",".join(modules)

        cmd = [
            "python3",
            str(tool_path),
            "-s",
            query,
            "-m",
            module_str,
            "-q",
            "-o",
            "json",
        ]

        returncode, stdout, stderr = await self._run_subprocess(cmd, cwd=str(tool_dir))

        results: list[dict] = []
        seen: set[str] = set()
        parsed_json = False

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("["):
                try:
                    entries = json.loads(line)
                    parsed_json = True
                    if isinstance(entries, list):
                        for entry in entries:
                            if isinstance(entry, dict):
                                self._append_entry(results, seen, entry, query)
                except json.JSONDecodeError:
                    pass
                continue
            if not line.startswith("{"):
                continue
            try:
                entry = json.loads(line)
                parsed_json = True
                self._append_entry(results, seen, entry, query)
            except json.JSONDecodeError:
                continue

        if not results and parsed_json:
            return ToolResult(
                tool=self.name,
                success=True,
                data=[],
                error=None,
                raw_output=(
                    "SpiderFoot modules ran but returned no new findings beyond the seed query. "
                    "HIBP/Hunter/Clearbit modules may need API keys."
                ),
            )

        success = len(results) > 0 or returncode == 0
        return ToolResult(
            tool=self.name,
            success=success,
            data=results,
            error=None if success else stderr[:500] or "No SpiderFoot results",
            raw_output=stdout[:2000] if results else (
                "SpiderFoot modules ran but returned no new findings beyond the seed query."
            ),
        )

    def _append_entry(
        self,
        results: list[dict],
        seen: set[str],
        entry: dict,
        query: str,
    ) -> None:
        data_type = entry.get("type", "unknown")
        data_val = entry.get("data", "")
        module = entry.get("module", "spiderfoot")

        if not data_val or data_val == query:
            return
        if data_type == "Email Address" and data_val.lower() == query.lower():
            return
        if module == "SpiderFoot UI":
            return

        dedupe_key = f"{data_type}:{data_val.lower()}"
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)

        platform = module
        extra: dict = {
            "data_type": data_type,
            "value": data_val,
            "module": module,
        }
        if data_type == "Email Address" or "@" in data_val:
            platform = "email"
            extra["email"] = data_val

        results.append(
            self._normalize_entry(
                platform=platform,
                url=data_val if data_val.startswith("http") else None,
                extra=extra,
            )
        )
