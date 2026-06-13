import asyncio
import json
import time
from typing import Any

import httpx

from adapters.base import BaseAdapter
from schemas.common import ToolResult

MAX_CONCURRENT_CHECKS = 25
REQUEST_TIMEOUT_SEC = 5.0
MAX_SITES_TO_CHECK = 150
SITE_CHECK_BUDGET_SEC = 75.0
USER_AGENT = "SOCMINT-OSINT/1.0 (investigation-platform)"


def _account_url(site: dict[str, Any], query: str) -> str | None:
    template = site.get("uri_check") or site.get("uri") or site.get("url")
    if not template or not isinstance(template, str):
        return None
    return template.replace("{account}", query).replace("{username}", query)


def _site_priority(site: dict[str, Any]) -> tuple[int, str]:
    score = 0
    if site.get("e_string"):
        score += 2
    if site.get("e_code") is not None:
        score += 1
    if site.get("m_string"):
        score += 1
    if site.get("m_code") is not None:
        score += 1
    return (-score, str(site.get("name") or site.get("site") or ""))


def classify_whatsmyname_response(
    site: dict[str, Any],
    status_code: int,
    body: str,
) -> bool | None:
    e_code = site.get("e_code")
    e_string = site.get("e_string") or ""
    m_code = site.get("m_code")
    m_string = site.get("m_string") or ""

    if e_string and m_string and e_string == m_string and e_string in body:
        return None

    has_miss_signal = False
    if m_string and m_string in body:
        has_miss_signal = not m_code or status_code == m_code
    elif m_code is not None and status_code == m_code and not m_string:
        has_miss_signal = True

    has_hit_signal = False
    if e_string and e_string in body:
        has_hit_signal = not e_code or status_code == e_code
    elif e_code is not None and status_code == e_code and not e_string:
        has_hit_signal = True

    if has_miss_signal and has_hit_signal:
        return None
    if has_miss_signal:
        return False
    if has_hit_signal:
        return True
    return None


class WhatsMyNameAdapter(BaseAdapter):
    name = "whatsmyname"
    default_timeout = 180.0

    async def run(self, query: str, timeout: float | None = None) -> ToolResult:
        """Run without outer wait_for — internal time budget avoids client teardown races."""
        start = time.monotonic()
        ok, error = self.verify_tool()
        if not ok:
            return ToolResult(
                tool=self.name,
                success=False,
                error=error,
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

        try:
            result = await self._execute(query, outer_timeout=timeout)
            result.execution_time_ms = (time.monotonic() - start) * 1000
            return result
        except Exception as exc:
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Tool '{self.name}' failed: {type(exc).__name__}: {exc}",
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

    async def _execute(self, query: str, outer_timeout: float | None = None) -> ToolResult:
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
        checkable = [s for s in sites if isinstance(s, dict) and _account_url(s, query)]
        checkable.sort(key=_site_priority)
        selected = checkable[:MAX_SITES_TO_CHECK]

        budget = SITE_CHECK_BUDGET_SEC
        if outer_timeout:
            budget = min(budget, max(outer_timeout - 5.0, 30.0))

        verified, checked = await self._verify_sites(query, selected, budget)

        return ToolResult(
            tool=self.name,
            success=True,
            data=verified,
            raw_output=(
                f"Live-verified {len(verified)} of {checked} WhatsMyName site checks "
                f"for '{query}' (from {len(checkable)} checkable sites)"
            ),
        )

    async def _check_one(
        self,
        client: httpx.AsyncClient,
        site: dict[str, Any],
        query: str,
        deadline: float,
    ) -> dict | None:
        if time.monotonic() >= deadline:
            return None
        url = _account_url(site, query)
        if not url:
            return None
        try:
            response = await client.get(url)
        except (httpx.HTTPError, RuntimeError, asyncio.CancelledError):
            return None

        exists = classify_whatsmyname_response(site, response.status_code, response.text)
        if exists is not True:
            return None

        name = site.get("name") or site.get("site") or "unknown"
        return self._normalize_entry(
            platform=name,
            url=url,
            extra={
                "category": site.get("cat") or site.get("category"),
                "check_type": "live_scan",
                "verified": True,
                "status": "registered",
                "http_status": response.status_code,
            },
        )

    async def _verify_sites(
        self,
        query: str,
        sites: list[dict[str, Any]],
        budget_sec: float,
    ) -> tuple[list[dict], int]:
        if not sites:
            return [], 0

        deadline = time.monotonic() + budget_sec
        results: list[dict] = []
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        for site in sites:
            queue.put_nowait(site)
        for _ in range(MAX_CONCURRENT_CHECKS):
            queue.put_nowait(None)

        client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT_SEC,
            headers={"User-Agent": USER_AGENT},
            limits=httpx.Limits(max_connections=MAX_CONCURRENT_CHECKS, max_keepalive_connections=10),
        )
        workers: list[asyncio.Task] = []

        try:
            async def worker() -> None:
                while time.monotonic() < deadline:
                    site = await queue.get()
                    try:
                        if site is None:
                            return
                        hit = await self._check_one(client, site, query, deadline)
                        if hit:
                            results.append(hit)
                    finally:
                        queue.task_done()

            workers = [asyncio.create_task(worker()) for _ in range(MAX_CONCURRENT_CHECKS)]
            await asyncio.gather(*workers, return_exceptions=True)
        finally:
            for task in workers:
                if not task.done():
                    task.cancel()
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            await client.aclose()

        results.sort(key=lambda r: str(r.get("platform", "")).lower())
        return results, len(sites)
