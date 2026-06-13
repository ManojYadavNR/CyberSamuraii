from typing import Any

from schemas.common import ConfidenceInput, ToolResult

TOOL_BASE_WEIGHTS: dict[str, float] = {
    "sherlock": 1.0,
    "maigret": 1.0,
    "social_analyzer": 0.8,
    "whatsmyname": 0.2,
    "holehe": 0.9,
}

MAX_ITEM_CONFIDENCE_INPUTS = 20


def _is_verified_hit(item: dict[str, Any]) -> bool:
    if item.get("verified") is False:
        return False
    if item.get("check_type") == "dataset_lookup":
        return False
    if item.get("status") in ("rate_limited", "not_registered"):
        return False
    if item.get("platform") == "_scan_summary":
        return False
    return True


def _item_weight(item: dict[str, Any], tool_weight: float) -> float:
    if not _is_verified_hit(item):
        return 0.05 * tool_weight
    return 0.5 * tool_weight


def normalize_tool_results(tool_results: list[ToolResult]) -> list[dict[str, Any]]:
    """Normalize raw tool outputs into a unified schema."""
    normalized: list[dict[str, Any]] = []

    for result in tool_results:
        if not result.success:
            continue
        for item in result.data:
            entry: dict[str, Any] = {
                "platform": item.get("platform", "unknown"),
                "source_tool": item.get("source_tool", result.tool),
                "url": item.get("url"),
                "metadata": {},
            }
            reserved = {"platform", "source_tool", "url"}
            for key, value in item.items():
                if key not in reserved:
                    entry["metadata"][key] = value
            normalized.append(entry)

    return normalized


def build_confidence_inputs(tool_results: list[ToolResult]) -> list[ConfidenceInput]:
    """Build raw confidence inputs from tool results (no correlation)."""
    inputs: list[ConfidenceInput] = []

    for result in tool_results:
        tool_weight = TOOL_BASE_WEIGHTS.get(result.tool, 0.5)
        verified_count = sum(1 for item in result.data if _is_verified_hit(item))

        inputs.append(
            ConfidenceInput(
                source_tool=result.tool,
                field="success",
                value=result.success,
                weight=tool_weight if result.success else 0.0,
            )
        )

        if result.success:
            count_weight = min(verified_count * 0.2, 1.0) if verified_count else 0.1
            inputs.append(
                ConfidenceInput(
                    source_tool=result.tool,
                    field="result_count",
                    value=verified_count or len(result.data),
                    weight=count_weight * tool_weight,
                )
            )

        item_inputs = 0
        for item in result.data:
            if item_inputs >= MAX_ITEM_CONFIDENCE_INPUTS:
                break
            item_w = _item_weight(item, tool_weight)
            if item.get("url"):
                inputs.append(
                    ConfidenceInput(
                        source_tool=result.tool,
                        field="url",
                        value=item["url"],
                        weight=item_w,
                    )
                )
                item_inputs += 1
            if item.get("platform") and item_inputs < MAX_ITEM_CONFIDENCE_INPUTS:
                inputs.append(
                    ConfidenceInput(
                        source_tool=result.tool,
                        field="platform",
                        value=item["platform"],
                        weight=item_w * 0.6,
                    )
                )
                item_inputs += 1

    return inputs
