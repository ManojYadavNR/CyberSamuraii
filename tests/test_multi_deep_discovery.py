"""Deep mode + multi-input discovery integration."""

import asyncio

from adapters.scan_config import (
    DUAL_USERNAME_SCAN_BUDGET_SEC,
    SCAN_BUDGET_SEC,
    scan_budget_sec,
)
from orchestrator.parallel_config import effective_wall_seconds
from schemas.discovery import DiscoveryConfig, is_deep_discovery
from services.resource_guard import dual_identity_scan, full_scan_mode


def test_is_deep_discovery_from_ui_payload():
    deep = DiscoveryConfig(enabled=True, max_depth=4, max_hops=20, max_leads_per_hop=12, max_total_leads=50)
    standard = DiscoveryConfig(enabled=True, max_depth=2, max_hops=2, max_leads_per_hop=5, max_total_leads=12)
    assert is_deep_discovery(deep)
    assert not is_deep_discovery(standard)
    assert not is_deep_discovery(None)


def test_full_scan_mode_restores_dual_budgets():
    async def _run() -> None:
        async with dual_identity_scan():
            assert scan_budget_sec() == DUAL_USERNAME_SCAN_BUDGET_SEC
            assert effective_wall_seconds("username_search") < SCAN_BUDGET_SEC
            async with full_scan_mode():
                assert scan_budget_sec() == SCAN_BUDGET_SEC
                assert effective_wall_seconds("username_search") > DUAL_USERNAME_SCAN_BUDGET_SEC

    asyncio.run(_run())
