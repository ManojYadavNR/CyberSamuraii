import abc
import asyncio
import time
from typing import Any

from schemas.common import ToolResult, ToolStatus
from tools.registry import registry


class BaseAdapter(abc.ABC):
    """Base class for all OSINT tool adapters."""

    name: str = "base"
    default_timeout: float = 120.0
    max_retries: int = 2
    retry_delay: float = 1.0

    def __init__(self):
        self.registry = registry

    def verify_tool(self) -> tuple[bool, str | None]:
        """Verify tool exists and is healthy before execution."""
        status = self.registry.check_health(self.name)
        if status == ToolStatus.NOT_INSTALLED:
            return False, f"Tool '{self.name}' is not installed. Run scripts/install_tools.sh"
        if status == ToolStatus.MISSING_API_KEY:
            return False, f"Tool '{self.name}' requires an API key (set {self.name.upper()}_API_KEY)"
        if status == ToolStatus.UNHEALTHY:
            return False, f"Tool '{self.name}' is unhealthy. Run scripts/verify_tools.sh"
        return True, None

    async def run(self, query: str, timeout: float | None = None) -> ToolResult:
        """Execute tool with timeout, retry, and failure isolation."""
        timeout = timeout or self.default_timeout
        start = time.monotonic()

        ok, error = self.verify_tool()
        if not ok:
            return ToolResult(
                tool=self.name,
                success=False,
                error=error,
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._execute(query),
                    timeout=timeout,
                )
                result.execution_time_ms = (time.monotonic() - start) * 1000
                return result
            except asyncio.TimeoutError:
                last_error = f"Tool '{self.name}' timed out after {timeout}s"
            except Exception as e:
                last_error = f"Tool '{self.name}' failed: {type(e).__name__}: {e}"

            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay * (attempt + 1))

        return ToolResult(
            tool=self.name,
            success=False,
            error=last_error,
            execution_time_ms=(time.monotonic() - start) * 1000,
        )

    @abc.abstractmethod
    async def _execute(self, query: str) -> ToolResult:
        """Subclass implements actual tool execution."""
        ...

    async def _run_subprocess(
        self,
        cmd: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Run a subprocess asynchronously."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        return (
            proc.returncode or 0,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
        )

    def _normalize_entry(
        self,
        platform: str,
        url: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "platform": platform,
            "source_tool": self.name,
        }
        if url:
            entry["url"] = url
        if extra:
            entry.update(extra)
        return entry
