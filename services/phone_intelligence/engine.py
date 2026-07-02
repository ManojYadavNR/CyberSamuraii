"""Run the integrated phone OSINT pipeline (ported from phoneNumber/phoneinfoga)."""

from __future__ import annotations

from schemas.common import ToolResult
from services.phone_intelligence.results import rows_from_social_only_scan
from services.phone_intelligence.scan_all import scan_phone_social_only


def run_phone_social_intel(query: str) -> ToolResult:
    """Social registration checks, profile resolution, and platform web search."""
    try:
        scan = scan_phone_social_only(query)
    except Exception as exc:
        return ToolResult(
            tool="phone_social_intel",
            success=False,
            error=f"Phone social scan failed: {type(exc).__name__}: {exc}",
        )

    if not scan.get("success"):
        return ToolResult(
            tool="phone_social_intel",
            success=False,
            error=str(scan.get("error") or "Phone social scan failed"),
        )

    rows = rows_from_social_only_scan(scan)
    social = scan.get("social_accounts") or {}
    summary = social.get("summary") or {}
    return ToolResult(
        tool="phone_social_intel",
        success=True,
        data=rows,
        raw_output=(
            f"Social OSINT: {summary.get('confirmed_links', 0)} confirmed link(s), "
            f"{summary.get('registered_accounts_found', 0)} platform registration(s), "
            f"{summary.get('possible_links', 0)} possible match(es)"
        ),
    )
