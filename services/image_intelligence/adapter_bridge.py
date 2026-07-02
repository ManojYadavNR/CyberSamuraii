"""Convert analyzer findings into adapter ToolResult payloads."""

from __future__ import annotations

from typing import Any

from adapters.image_common import image_result
from schemas.common import ToolResult
from services.json_utils import to_json_safe
from schemas.image_intelligence import ImageFinding


def findings_to_tool_result(
    tool: str,
    findings: list[ImageFinding],
    *,
    platform: str,
    group: str,
    success: bool = True,
    error: str | None = None,
) -> ToolResult:
    if error:
        return ToolResult(tool=tool, success=False, error=error)
    if not findings:
        return ToolResult(tool=tool, success=True, data=[], raw_output=f"{tool}: no findings")

    data: list[dict[str, Any]] = []
    for finding in findings:
        evidence = to_json_safe(finding.evidence or {})
        data.append({
            "platform": platform,
            "source_tool": tool,
            "intel_group": group,
            "check_type": "image_intel",
            "field": finding.field,
            "category": finding.category,
            "value": finding.value,
            "confidence": finding.confidence,
            "extraction_strategy": finding.extraction_strategy,
            **evidence,
        })
    return ToolResult(
        tool=tool,
        success=success,
        data=data,
        raw_output=f"{tool}: {len(data)} findings",
    )


def single_payload(tool: str, platform: str, group: str, extra: dict[str, Any], url: str | None = None) -> ToolResult:
    class _Stub:
        name = tool

    return ToolResult(
        tool=tool,
        success=True,
        data=[image_result(_Stub(), platform=platform, group=group, extra=extra, url=url)],
    )
