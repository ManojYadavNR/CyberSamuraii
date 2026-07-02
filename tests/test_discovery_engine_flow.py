"""Tests for recursive discovery engine orchestration."""

from unittest.mock import AsyncMock, patch

import pytest

from schemas.common import FeatureResult, ToolResult
from schemas.discovery import DiscoveryConfig
from schemas.fusion import Entity, FusionOutput
from services.discovery.engine import RecursiveDiscoveryEngine


def _result(query: str, feature: str, entities: list[Entity]) -> FeatureResult:
    return FeatureResult(
        feature=feature,
        query=query,
        tool_results=[ToolResult(tool="mock", success=True, data=[{"platform": "x"}])],
        fusion=FusionOutput(deduplicated_entities=entities, fusion_score=0.5),
    )


@pytest.mark.asyncio
async def test_expand_stops_when_no_expandable_leads():
    seed = _result("alice", "username_search", [])
    engine = RecursiveDiscoveryEngine()

    with patch("services.pivot.engine.auto_pivot_engine._run_hop", new_callable=AsyncMock) as run_hop:
        final = await engine.expand(
            seed_query="alice",
            seed_query_type="username",
            seed_result=seed,
            config=DiscoveryConfig(enabled=True, max_depth=2, max_hops=5),
        )

    run_hop.assert_not_called()
    assert final.discovery is not None
    assert final.discovery.total_hops == 0
    assert final.discovery.stop_reason == "no_new_leads"


@pytest.mark.asyncio
async def test_expand_runs_child_hop_and_merges():
    seed_entity = Entity(
        type="email",
        value="alice@example.org",
        metadata={"verified": True},
        fusion_score=0.9,
    )
    seed = _result("alice", "username_search", [seed_entity])
    child = _result("alice@example.org", "email_intel", [Entity(type="domain", value="example.org")])

    engine = RecursiveDiscoveryEngine()

    with patch("services.pivot.engine.auto_pivot_engine._run_hop", new_callable=AsyncMock) as run_hop:
        run_hop.return_value = (child, None)
        with patch("services.persistence.postgres.persist_discovery_chain", return_value=None):
            final = await engine.expand(
                seed_query="alice",
                seed_query_type="username",
                seed_result=seed,
                config=DiscoveryConfig(enabled=True, max_depth=2, max_hops=3, max_leads_per_hop=5),
            )

    run_hop.assert_called()
    assert run_hop.call_count >= 1
    assert final.discovery is not None
    assert final.discovery.total_hops >= 1
    assert final.fusion is not None
    assert len(final.fusion.deduplicated_entities) >= 2
    assert final.execution_mode == "recursive"
