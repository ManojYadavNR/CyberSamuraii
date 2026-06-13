import re

from adapters.base import BaseAdapter
from schemas.common import ToolResult


class ReconNgAdapter(BaseAdapter):
    name = "recon_ng"
    default_timeout = 180.0

    async def _execute(self, query: str) -> ToolResult:
        tool_path = self.registry.get_tool_path(self.name)
        recon_cmd = self.registry.get_executable_path(self.name)

        if recon_cmd and recon_cmd.exists():
            return await self._run_cli(query, recon_cmd)
        if tool_path and tool_path.exists():
            return await self._run_workspace(query, tool_path)

        return ToolResult(tool=self.name, success=False, error="Recon-ng not found")

    async def _run_cli(self, query: str, recon_cmd) -> ToolResult:
        commands = f"marketplace install all; modules load recon/domains-hosts/hackertarget; options set SOURCE {query}; run; show hosts; exit\n"
        cmd = ["recon-ng", "--no-banner"]
        returncode, stdout, stderr = await self._run_subprocess_with_stdin(cmd, commands)
        return self._parse_output(stdout, stderr, returncode)

    async def _run_workspace(self, query: str, tool_path) -> ToolResult:
        recon_script = tool_path / "recon-ng"
        if not recon_script.exists():
            recon_script = tool_path / "recon-ng.py"

        commands = (
            f"workspaces create {query}\n"
            f"modules load recon/domains-hosts/hackertarget\n"
            f"options set SOURCE {query}\n"
            "run\n"
            "show hosts\n"
            "exit\n"
        )

        cmd = ["python3", str(recon_script), "--no-banner"]
        returncode, stdout, stderr = await self._run_subprocess_with_stdin(
            cmd, commands, cwd=str(tool_path)
        )
        return self._parse_output(stdout, stderr, returncode)

    async def _run_subprocess_with_stdin(
        self, cmd: list[str], stdin_data: str, cwd: str | None = None
    ) -> tuple[int, str, str]:
        import asyncio

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate(input=stdin_data.encode())
        return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")

    def _parse_output(self, stdout: str, stderr: str, returncode: int) -> ToolResult:
        results: list[dict] = []
        host_pattern = re.compile(r"[\w.-]+\.[a-zA-Z]{2,}")

        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("|") or line.startswith("-"):
                continue
            hosts = host_pattern.findall(line)
            for host in hosts:
                results.append(
                    self._normalize_entry(
                        platform="host",
                        url=f"https://{host}",
                        extra={"hostname": host},
                    )
                )

        seen = set()
        deduped = []
        for r in results:
            host = r.get("extra", {}).get("hostname", "")
            if host not in seen:
                seen.add(host)
                deduped.append(r)

        success = len(deduped) > 0 or returncode == 0
        return ToolResult(
            tool=self.name,
            success=success,
            data=deduped,
            error=None if success else stderr[:500] or "No recon results",
            raw_output=stdout[:2000],
        )
