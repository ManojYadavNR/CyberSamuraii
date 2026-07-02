"""Investigation speed modes — Standard / Quick / Deep."""

from __future__ import annotations

from typing import Literal

from schemas.discovery import DiscoveryConfig, is_deep_discovery

InvestigationMode = Literal["standard", "fast", "deep", "samurai"]

FAST_USERNAME_TOOLS = ["platform_probe", "maigret", "sherlock"]
SAMURAI_USERNAME_TOOLS = ["samurai"]


def resolve_investigation_mode(
    *,
    explicit: str | None = None,
    discovery: DiscoveryConfig | None = None,
    image_profile: str = "fast",
) -> InvestigationMode:
    if explicit in ("standard", "fast", "deep", "samurai"):
        return explicit  # type: ignore[return-value]
    if image_profile == "deep" or is_deep_discovery(discovery):
        return "deep"
    if discovery is not None and not discovery.enabled:
        return "fast"
    return "standard"


def tool_profile_for_mode(mode: InvestigationMode, *, feature: str) -> str:
    if mode == "fast":
        return "fast"
    if mode == "deep":
        return "deep"
    return "deep" if feature in ("username_search", "email_intel") else "fast"


def username_tools_override(mode: InvestigationMode) -> list[str] | None:
    if mode == "fast":
        return list(FAST_USERNAME_TOOLS)
    if mode == "samurai":
        return list(SAMURAI_USERNAME_TOOLS)
    return None


def mode_label(mode: InvestigationMode) -> str:
    return {
        "standard": "Standard",
        "fast": "Quick",
        "deep": "Deep",
        "samurai": "Social (Samurai)",
    }[mode]
