"""Tool scan statistics — surfaced in UI as sites checked vs hits found."""

from __future__ import annotations

from typing import Any


def scan_summary_entry(
    tool: str,
    *,
    sites_checked: int,
    sites_found: int,
    note: str = "",
) -> dict[str, Any]:
    return {
        "platform": "_scan_summary",
        "source_tool": tool,
        "sites_checked": sites_checked,
        "sites_found": sites_found,
        "note": note,
    }
