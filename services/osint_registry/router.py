"""Automatic tool routing — Target → Registry → Tool Selection."""

from __future__ import annotations

import os
from typing import Any

from services.osint_registry.registry import registry
from services.osint_registry.tool_metadata import ToolSelectionPlan

INPUT_TO_FEATURE: dict[str, str] = {
    "username": "username_search",
    "email": "email_intel",
    "image": "image_intel",
    "domain": "domain_intel",
    "phone": "infra_intel",
    "infra": "infra_intel",
    "url": "url_intel",
}

FEATURE_TO_INPUT: dict[str, str] = {v: k for k, v in INPUT_TO_FEATURE.items()}

WALL_BUDGET_SEC = float(os.getenv("INVESTIGATION_WALL_SECONDS", "300"))


def input_type_from_feature(feature: str) -> str:
    return FEATURE_TO_INPUT.get(feature, "username")


def feature_from_input(input_type: str) -> str:
    return INPUT_TO_FEATURE.get(input_type, "username_search")


def select_tools(
    target: str,
    *,
    input_type: str | None = None,
    feature: str | None = None,
    profile: str = "fast",
    hop: bool = False,
    wall_budget_sec: float | None = None,
) -> ToolSelectionPlan:
    """Registry-driven tool selection for a target + input shape."""
    from services.query_detector import detect_query_type

    resolved_input = input_type or detect_query_type(target)
    resolved_feature = feature or feature_from_input(resolved_input)
    budget = wall_budget_sec or WALL_BUDGET_SEC

    metas = registry.tools_for_input(
        resolved_input,
        feature=resolved_feature,
        hop=hop,
        profile=profile,
        runnable_only=True,
    )

    cost_weight = {"free": 0.5, "low": 1.0, "medium": 2.0, "high": 4.0}
    speed_weight = {"fast": 1.0, "medium": 1.5, "slow": 3.0}
    selected: list[str] = []
    selected_meta: list = []

    # Select all runnable tools — they execute in parallel within the wall budget.
    for meta in metas:
        if hop:
            tool_cost = cost_weight.get(meta.cost, 1.0) * speed_weight.get(meta.speed, 1.5)
            if tool_cost > 3.0:
                continue
        key = meta.adapter_key or meta.tool_name
        if key not in selected:
            selected.append(key)
            selected_meta.append(meta)

    groups = registry.parallel_groups(selected_meta)
    return ToolSelectionPlan(
        input_type=resolved_input,
        feature=resolved_feature,
        tools=selected,
        parallel_groups=groups,
        wall_budget_sec=budget,
        metadata=selected_meta,
    )


def _resolve_input_type(feature: str, target: str) -> str:
    """Pick registry input bucket from feature + target shape (phone vs infra IP)."""
    probe = (target or "").strip()
    if probe and probe not in ("probe",):
        from services.multi_input import parse_investigation_input
        from services.query_detector import detect_query_type

        parsed = parse_investigation_input(probe)
        if parsed.phone or detect_query_type(probe) == "phone":
            return "phone"
        if feature == "domain_intel" or parsed.domain:
            return "domain"
        if feature == "infra_intel":
            return "infra"
    return input_type_from_feature(feature)


def tools_for_feature(
    feature: str,
    *,
    profile: str = "fast",
    hop: bool = False,
    target: str = "",
) -> list[str]:
    """Drop-in replacement for hardcoded FEATURE_TOOLS[feature]."""
    input_type = _resolve_input_type(feature, target)
    plan = select_tools(
        target or "probe",
        input_type=input_type,
        feature=feature,
        profile=profile,
        hop=hop,
    )
    if plan.tools:
        return _filter_unavailable_tools(plan.tools, input_type=input_type)

    return _filter_unavailable_tools(_fallback_tools(feature, input_type=input_type), input_type=input_type)


def _filter_unavailable_tools(tools: list[str], *, input_type: str = "") -> list[str]:
    """Drop tools that need auth the user has not configured."""
    from services.ghunt_session import ghunt_session_available

    out: list[str] = []
    for tool in tools:
        if tool in ("gitfive", "nexfil"):
            continue
        if tool == "ghunt" and not ghunt_session_available():
            continue
        if input_type == "phone" and tool == "shodan":
            continue
        out.append(tool)
    return out


def _fallback_tools(feature: str, *, input_type: str = "") -> list[str]:
    """Safety net if catalog fails to load."""
    from orchestrator.parallel_config import IMAGE_PARALLEL_TOOLS

    defaults: dict[str, list[str]] = {
        "username_search": ["platform_probe", "maigret", "sherlock", "social_analyzer", "samurai", "google_dorking"],
        "email_intel": ["holehe", "theharvester", "spiderfoot", "google_dorking"],
        "domain_intel": ["theharvester", "spiderfoot", "recon_ng", "google_dorking"],
        "infra_intel": (
            ["phoneinfoga", "phone_social_intel", "google_dorking"]
            if input_type == "phone"
            else ["shodan", "google_dorking"]
        ),
        "url_intel": ["instagram_comment_apify"],
        "image_intel": IMAGE_PARALLEL_TOOLS,
    }
    return defaults.get(feature, [])


def reload_registry() -> dict[str, Any]:
    count = registry.reload()
    return {"reloaded": True, "tool_count": count, "inputs": list(INPUT_TO_FEATURE.keys())}
