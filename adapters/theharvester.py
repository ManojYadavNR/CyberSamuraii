import json
import re
from pathlib import Path

from adapters.base import BaseAdapter
from schemas.common import ToolResult
from services.email_intel import CONSUMER_MAIL_DOMAINS, is_consumer_mail

# Fast public sources — avoid `-b all` which can run for several minutes.
FAST_SOURCES = "duckduckgo,hackertarget,crtsh"


class TheHarvesterAdapter(BaseAdapter):
    name = "theharvester"
    default_timeout = 180.0

    def _resolve_query(self, query: str) -> str:
        if "@" in query:
            return query.split("@", 1)[1].strip().lower()
        return query.strip().lower()

    async def _execute(self, query: str) -> ToolResult:
        harvest_domain = self._resolve_query(query)
        if not harvest_domain:
            return ToolResult(tool=self.name, success=False, error="Invalid domain for theHarvester")

        if "@" in query and harvest_domain in CONSUMER_MAIL_DOMAINS:
            return ToolResult(
                tool=self.name,
                success=True,
                data=[],
                raw_output=(
                    f"Skipped theHarvester for consumer mail domain '{harvest_domain}'. "
                    "Use a company/organization domain for email harvesting."
                ),
            )

        tool_path = self.registry.get_executable_path(self.name)
        if not tool_path or not tool_path.exists():
            import shutil

            path_cli = shutil.which("theHarvester")
            if path_cli:
                tool_path = Path(path_cli)
            else:
                return ToolResult(tool=self.name, success=False, error="theHarvester executable not found")

        tool_dir = tool_path.parent.parent if tool_path.parent.name == "bin" else tool_path.parent
        safe_name = re.sub(r"[^\w.-]", "_", harvest_domain)
        output_file = f"/tmp/theharvester_{safe_name}"

        cmd = [
            "python3",
            str(tool_path),
            "-d",
            harvest_domain,
            "-b",
            FAST_SOURCES,
            "-q",
            "-f",
            output_file,
        ]

        returncode, stdout, stderr = await self._run_subprocess(cmd, cwd=str(tool_dir))

        results = self._parse_json_output(f"{output_file}.json", harvest_domain)
        if not results:
            results = self._parse_stdout(stdout, harvest_domain)

        seen: set[str] = set()
        deduped: list[dict] = []
        for entry in results:
            key = str(entry.get("url", "")) + str(entry.get("extra", {}).get("email", ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entry)

        success = len(deduped) > 0 or returncode == 0
        return ToolResult(
            tool=self.name,
            success=success,
            data=deduped,
            error=None if success else stderr[:500] or "No harvest results",
            raw_output=stdout[:2000],
        )

    def _parse_json_output(self, json_path: str, source_domain: str) -> list[dict]:
        path = Path(json_path)
        if not path.exists():
            return []

        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

        results: list[dict] = []
        for email in data.get("emails", []):
            email_str = str(email).strip().lower()
            if not email_str or "@" not in email_str:
                continue
            if not self._is_relevant_email(email_str, source_domain):
                continue
            results.append(
                self._normalize_entry(
                    platform="email",
                    extra={"email": email_str, "source_domain": source_domain},
                )
            )

        for host in data.get("hosts", []):
            host_str = str(host).split(":")[0].strip()
            if not host_str or host_str == source_domain:
                continue
            results.append(
                self._normalize_entry(
                    platform="host",
                    url=f"https://{host_str}",
                    extra={"hostname": host_str, "source_domain": source_domain},
                )
            )

        return results

    def _is_relevant_email(self, email: str, source_domain: str) -> bool:
        domain_part = email.split("@", 1)[1]
        if domain_part == source_domain or domain_part.endswith(f".{source_domain}"):
            return True
        return False

    def _parse_stdout(self, stdout: str, source_domain: str) -> list[dict]:
        results: list[dict] = []
        email_pattern = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
        host_pattern = re.compile(r"[\w.-]+\.[a-zA-Z]{2,}")

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            for email in email_pattern.findall(line):
                if not self._is_relevant_email(email.lower(), source_domain):
                    continue
                results.append(
                    self._normalize_entry(
                        platform="email",
                        extra={"email": email, "source_domain": source_domain},
                    )
                )

            if "Hosts found" in line or "host" in line.lower():
                for host in host_pattern.findall(line):
                    if host != source_domain:
                        results.append(
                            self._normalize_entry(
                                platform="host",
                                url=f"https://{host}",
                                extra={"hostname": host, "source_domain": source_domain},
                            )
                        )

        return results
