import re

from adapters.base import BaseAdapter
from schemas.common import ToolResult


class SherlockAdapter(BaseAdapter):
    name = "sherlock"
    default_timeout = 180.0

    async def _execute(self, query: str) -> ToolResult:
        tool_path = self.registry.get_executable_path(self.name)
        if not tool_path or not tool_path.exists():
            return ToolResult(tool=self.name, success=False, error="Sherlock executable not found")

        cmd = [
            "python3",
            str(tool_path),
            query,
            "--print-found",
            "--timeout",
            "10",
            "--local",
        ]

        returncode, stdout, stderr = await self._run_subprocess(cmd)

        results: list[dict] = []
        for line in stdout.splitlines():
            match = re.search(r"\[\+\]\s+(.+?):\s+(https?://\S+)", line)
            if match:
                results.append(
                    self._normalize_entry(
                        platform=match.group(1).strip(),
                        url=match.group(2),
                        extra={"verified": True, "check_type": "live_scan"},
                    )
                )

        success = len(results) > 0
        error = None
        if not success:
            combined = f"{stderr}\n{stdout}".strip()
            if "ERROR:" in combined:
                error = combined[:500]
            else:
                error = "No results found"

        return ToolResult(
            tool=self.name,
            success=success,
            data=results,
            error=error,
            raw_output=(stdout + stderr)[:2000],
        )
