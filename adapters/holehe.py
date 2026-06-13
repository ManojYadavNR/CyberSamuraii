import asyncio
from typing import Any

import httpx
import trio

from adapters.base import BaseAdapter
from holehe.core import get_functions, import_submodules, is_email, launch_module
from schemas.common import ToolResult


class _HoleheArgs:
    """Enable password-recovery probes for richer investigation metadata."""

    nopasswordrecovery = False


async def _run_holehe_scan(email: str, request_timeout: int) -> list[dict[str, Any]]:
    def _scan() -> list[dict[str, Any]]:
        async def _core() -> list[dict[str, Any]]:
            modules = import_submodules("holehe.modules")
            websites = get_functions(modules, _HoleheArgs())
            out: list[dict[str, Any]] = []
            client = httpx.AsyncClient(timeout=request_timeout)
            async with trio.open_nursery() as nursery:
                for website in websites:
                    nursery.start_soon(launch_module, website, email, client, out)
            await client.aclose()
            return sorted(out, key=lambda i: i.get("name", ""))

        return trio.run(_core)

    return await asyncio.to_thread(_scan)


class HoleheAdapter(BaseAdapter):
    name = "holehe"
    default_timeout = 180.0
    request_timeout = 15

    async def _execute(self, query: str) -> ToolResult:
        if not is_email(query):
            return ToolResult(tool=self.name, success=False, error="Invalid email address")

        try:
            raw = await _run_holehe_scan(query, self.request_timeout)
        except Exception as e:
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Holehe scan failed: {type(e).__name__}: {e}",
            )

        results: list[dict] = []
        seen_domains: set[str] = set()
        registered = 0
        rate_limited = 0
        not_used = 0

        for item in raw:
            domain = (item.get("domain") or item.get("name") or "unknown").strip().lower()
            if domain in seen_domains:
                continue
            seen_domains.add(domain)

            exists = bool(item.get("exists"))
            limited = bool(item.get("rateLimit"))

            if exists:
                status = "registered"
                registered += 1
            elif limited:
                status = "rate_limited"
                rate_limited += 1
            else:
                status = "not_registered"
                not_used += 1
                continue  # negative results are not investigation findings

            extra: dict[str, Any] = {
                "email": query,
                "status": status,
                "registered": exists,
                "rate_limited": limited,
                "check_type": "live_scan",
                "verified": exists,
            }
            if item.get("emailrecovery"):
                extra["email_recovery_hint"] = item["emailrecovery"]
            if item.get("phoneNumber"):
                extra["phone_hint"] = item["phoneNumber"]
            if item.get("others"):
                extra["profile_metadata"] = item["others"]

            results.append(self._normalize_entry(platform=domain, extra=extra))

        status_order = {"registered": 0, "rate_limited": 1, "not_registered": 2}
        results.sort(key=lambda r: status_order.get(r.get("status", ""), 3))

        results.insert(
            0,
            self._normalize_entry(
                platform="_scan_summary",
                extra={
                    "email": query,
                    "sites_checked": len(seen_domains),
                    "confirmed_registrations": registered,
                    "sites_rate_limited": rate_limited,
                    "sites_not_registered": not_used,
                    "investigation_note": (
                        "registered = live confirmation; rate_limited = inconclusive "
                        "(manual follow-up recommended); not_registered = checked, no account found."
                    ),
                },
            ),
        )

        return ToolResult(
            tool=self.name,
            success=True,
            data=results,
            raw_output=(
                f"Holehe checked {len(seen_domains)} sites: "
                f"{registered} registered, {rate_limited} rate-limited, {not_used} not registered"
            ),
        )
