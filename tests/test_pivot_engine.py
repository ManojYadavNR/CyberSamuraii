"""Tests for Auto Pivot Engine and person-centric intelligence."""

import pytest

from schemas.common import FeatureResult, ToolResult
from schemas.discovery import DiscoveryConfig
from schemas.fusion import Entity, FusionOutput
from services.intelligence.person import build_identity_profile
from services.pivot.processors import process_entity
from services.pivot.queue import LeadQueue
from services.pivot.tree import InvestigationTreeBuilder


def _account(**meta) -> Entity:
    base = {
        "verified": True,
        "check_type": "live_scan",
        "status": "maigret_claimed",
        "corroboration_status": "confirmed",
        "platform": "github.com",
        "url": "https://github.com/alice",
        "username": "alice",
    }
    base.update(meta)
    return Entity(
        type="account",
        value="github.com/alice",
        sources=["maigret"],
        fusion_score=0.8,
        metadata=base,
    )


def test_pivot_processor_returns_evidence_and_leads():
    entity = _account(email="alice@example.org", website="projects.example.org", bio="Engineer")
    result = process_entity(entity, source_query="alice", depth=1, max_leads=10)

    assert result.evidence
    assert result.generated_leads
    assert result.opportunities
    assert any(l.lead_type == "email" for l in result.generated_leads)
    assert any(l.lead_type == "domain" for l in result.generated_leads)
    assert all(l.metadata.get("pivot") for l in result.generated_leads)


def test_pivot_processor_skips_platform_root_domains():
    entity = _account(website="github.com", bio="MERN developer")
    result = process_entity(entity, source_query="alice", depth=1, max_leads=10)
    assert not any(l.query == "github.com" for l in result.generated_leads)


def test_pivot_processor_rejects_generic_handles():
    entity = _account(username="user", platform="reddit.com", url="https://reddit.com/user/alice")
    result = process_entity(entity, source_query="alice", depth=1, max_leads=10)
    assert not any(l.query == "user" for l in result.generated_leads)


def test_lead_queue_deduplicates():
    from services.discovery.router import build_routable_lead

    queue = LeadQueue()
    lead = build_routable_lead("alice@example.org", lead_type="email", depth=1)
    assert lead
    assert queue.enqueue(lead)
    assert not queue.enqueue(lead)
    assert len(queue) == 1


def test_investigation_tree_tracks_chain():
    from services.pivot.processors import process_entity
    from services.discovery.router import build_routable_lead

    builder = InvestigationTreeBuilder("alice")
    entity = _account(email="alice@example.org")
    pivot = process_entity(entity, source_query="alice", depth=1, max_leads=5)

    for ev in pivot.evidence:
        builder.add_evidence(ev)
    for lead in pivot.generated_leads:
        builder.add_lead(lead)

    tree = builder.build()
    assert tree.total_evidence_nodes >= 1
    assert tree.total_lead_nodes >= 1
    assert tree.max_depth >= 1
    assert any(n.node_type == "seed" for n in tree.nodes)


def test_identity_profile_aggregates_person_intelligence():
    entity = _account(
        display_name="Alice Smith",
        email="alice@example.org",
        bio="Open source",
        location="NYC",
        organization="Example Labs",
    )
    fusion = FusionOutput(deduplicated_entities=[entity], fusion_score=0.8)

    from services.evidence.engine import evidence_engine
    import asyncio

    updated, extraction = asyncio.run(evidence_engine.extract(fusion, seed_query="alice", enrich_public_profiles=False))

    profile = build_identity_profile(seed_query="alice", fusion=updated, evidence_extraction=extraction)
    assert profile.confidence_score > 0
    assert profile.emails or profile.names or profile.supporting_evidence
    assert profile.platform_profiles or profile.social_accounts


@pytest.mark.asyncio
async def test_auto_pivot_engine_expands_leads():
    from unittest.mock import AsyncMock, patch
    from services.pivot.engine import AutoPivotEngine

    entity = _account(email="alice@example.org", website="projects.example.org")
    fusion = FusionOutput(deduplicated_entities=[entity], fusion_score=0.8)
    seed = FeatureResult(feature="username_search", query="alice", fusion=fusion, tool_results=[])

    hop_entity = Entity(type="email", value="alice@example.org", sources=["holehe"], fusion_score=0.7, metadata={"verified": True})
    hop = FeatureResult(feature="email_intel", query="alice@example.org", fusion=FusionOutput(deduplicated_entities=[hop_entity], fusion_score=0.7), tool_results=[])

    engine = AutoPivotEngine()
    with patch.object(engine, "_run_hop", new_callable=AsyncMock) as run_hop:
        run_hop.return_value = (hop, None)
        with patch("services.persistence.postgres.persist_discovery_chain", return_value=None):
            result, discovery, tree = await engine.expand(
                seed_query="alice",
                seed_query_type="username",
                seed_result=seed,
                config=DiscoveryConfig(enabled=True, max_depth=2, max_hops=2, max_leads_per_hop=5),
            )

    assert discovery.total_hops >= 1
    assert tree.total_lead_nodes >= 1
    assert tree.total_hop_nodes >= 1


@pytest.mark.asyncio
async def test_recursive_discovery_integrates_pivot_and_identity():
    from unittest.mock import AsyncMock, patch
    from services.discovery.engine import RecursiveDiscoveryEngine

    entity = _account(email="alice@example.org")
    fusion = FusionOutput(deduplicated_entities=[entity], fusion_score=0.8)
    seed = FeatureResult(feature="username_search", query="alice", fusion=fusion, tool_results=[])

    engine = RecursiveDiscoveryEngine()
    with patch("services.pivot.engine.auto_pivot_engine.expand", new_callable=AsyncMock) as expand:
        from schemas.discovery import DiscoveryOutput
        from schemas.pivot import InvestigationTree, InvestigationTreeNode

        tree = InvestigationTree(root_id="r1", seed_query="alice", nodes=[
            InvestigationTreeNode(node_id="r1", node_type="seed", label="Seed", value="alice", depth=0),
        ])
        discovery = DiscoveryOutput(enabled=True, seed_query="alice", seed_query_type="username", config=DiscoveryConfig(), investigation_tree=tree)
        expand.return_value = (seed, discovery, tree)

        final = await engine.expand(seed_query="alice", seed_query_type="username", seed_result=seed, config=DiscoveryConfig(enabled=True))

    assert final.identity_profile is not None
    assert final.discovery is not None
    assert final.discovery.investigation_tree is not None
