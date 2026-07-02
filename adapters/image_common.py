"""Shared helpers for parallel image intelligence adapters."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

from schemas.common import ToolResult


async def resolve_image_source(query: str) -> tuple[str | None, str | None, str | None]:
    """Return (local_path, image_url, error). Downloads URLs to a temp file when needed."""
    q = query.strip()
    if not q:
        return None, None, "empty query"

    if os.path.isfile(q):
        return q, None, None

    if q.startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(q)
                resp.raise_for_status()
                suffix = Path(q.split("?")[0]).suffix or ".img"
                fd, path = tempfile.mkstemp(suffix=suffix)
                os.close(fd)
                with open(path, "wb") as fh:
                    fh.write(resp.content)
                return path, q, None
        except Exception as exc:
            return None, q, f"download failed: {exc}"

    return None, None, "image must be a file path or URL"


def image_result(
    adapter: Any,
    *,
    platform: str,
    group: str,
    extra: dict[str, Any] | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    meta = {"intel_group": group, "check_type": "image_intel", **(extra or {})}
    return adapter._normalize_entry(platform=platform, url=url, extra=meta)


def unavailable(tool: str, group: str, reason: str) -> ToolResult:
    return ToolResult(
        tool=tool,
        success=False,
        error=reason,
        data=[
            {
                "platform": tool,
                "source_tool": tool,
                "intel_group": group,
                "status": "unavailable",
                "note": reason,
            }
        ],
    )
