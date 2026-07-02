"""Investigation mode (Standard / Quick / Deep) wiring tests."""

import asyncio

from adapters.scan_config import (
    DUAL_USERNAME_SCAN_BUDGET_SEC,
    FAST_USERNAME_SCAN_BUDGET_SEC,
    SCAN_BUDGET_SEC,
    scan_budget_sec,
)
from orchestrator.config import get_feature_tools
from orchestrator.parallel_config import effective_wall_seconds
from schemas.discovery import DiscoveryConfig
from schemas.investigation_mode import (
    resolve_investigation_mode,
    tool_profile_for_mode,
    username_tools_override,
)
from services.resource_guard import (
    dual_identity_scan,
    full_scan_mode,
    investigation_mode_scope,
)


def test_resolve_mode_from_explicit():
    assert resolve_investigation_mode(explicit="fast") == "fast"
    assert resolve_investigation_mode(explicit="deep") == "deep"
    assert resolve_investigation_mode(explicit="standard") == "standard"


def test_resolve_mode_from_discovery():
    deep = DiscoveryConfig(enabled=True, max_hops=20)
    quick = DiscoveryConfig(enabled=False)
    assert resolve_investigation_mode(discovery=deep) == "deep"
    assert resolve_investigation_mode(discovery=quick) == "fast"


def test_fast_username_tools_subset():
    fast = username_tools_override("fast")
    samurai = username_tools_override("samurai")
    deep = get_feature_tools("username_search", profile="deep")
    assert fast is not None
    assert samurai == ["samurai"]
    assert "social_analyzer" not in fast
    assert "google_dorking" not in fast
    assert set(fast).issubset(set(deep))


def test_fast_scan_budgets():
    async def _run() -> None:
        async with investigation_mode_scope("fast"):
            assert scan_budget_sec() == FAST_USERNAME_SCAN_BUDGET_SEC
            assert effective_wall_seconds("username_search") == 90.0

    asyncio.run(_run())


def test_deep_multi_restores_full_dual_budgets():
    async def _run() -> None:
        async with investigation_mode_scope("deep"):
            async with dual_identity_scan():
                async with full_scan_mode():
                    assert scan_budget_sec() == SCAN_BUDGET_SEC
                    assert effective_wall_seconds("username_search") > DUAL_USERNAME_SCAN_BUDGET_SEC

    asyncio.run(_run())


def test_tool_profile_per_mode():
    assert tool_profile_for_mode("fast", feature="username_search") == "fast"
    assert tool_profile_for_mode("deep", feature="email_intel") == "deep"
    assert tool_profile_for_mode("standard", feature="username_search") == "deep"
    assert tool_profile_for_mode("standard", feature="email_intel") == "deep"


def test_standard_email_includes_all_registry_tools():
    deep = get_feature_tools("email_intel", target="probe@example.com", profile="deep")
    fast = get_feature_tools("email_intel", target="probe@example.com", profile="fast")
    assert "spiderfoot" in deep
    assert "holehe" in deep
    assert "theharvester" in deep
    assert "google_dorking" in deep
    assert "spiderfoot" not in fast
