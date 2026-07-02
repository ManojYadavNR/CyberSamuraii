"""Integration tests for Recursive Discovery + Universal Evidence Extraction."""

from unittest.mock import AsyncMock, patch

import pytest

from schemas.common import FeatureResult, ToolResult
from schemas.discovery import DiscoveryConfig
from schemas.evidence import EvidenceExtractionOutput, UnifiedPersonProfile
from schemas.fusion import Entity, FusionOutput
from services.discovery.engine import RecursiveDiscoveryEngine
from services.discovery.lead_extractor import extract_leads_from_entity
from services.evidence.engine import evidence_engine


def _enriched_account(platform: str, handle: str, **fields) -> Entity:
    meta = {
        "verified": True,
        "check_type": "live_scan",
        "status": "maigret_claimed",
        "platform": platform,
        "url": f"https://{platform}/{handle}",
        "username": handle,
        **fields,
    }
    return Entity(
        type="account",
        value=f"{platform}/{handle}",
        sources=["maigret"],
        fusion_score=0.8,
        metadata=meta,
    )


@pytest.mark.asyncio
async def test_seed_evidence_enables_discovery_leads():
    """Evidence-extracted profile fields must spawn discovery leads (not URLs)."""
    entity = _enriched_account(
        "github.com",
        "alice",
        email="alice@projects.example.org",
        website="projects.example.org",
        avatar_url="https://cdn.example.org/alice.png",
    )
    fusion = FusionOutput(deduplicated_entities=[entity], fusion_score=0.8)
    updated, output = await evidence_engine.extract(fusion, seed_query="alice", enrich_public_profiles=False)

    assert output.fields_extracted > 0
    enriched = updated.deduplicated_entities[0]
    leads = extract_leads_from_entity(enriched, source_query="alice", depth=1, max_leads=10)
    queries = {lead.query for lead in leads}
    assert "alice@projects.example.org" in queries
    assert "projects.example.org" in queries
    assert all("github.com/alice" not in lead.query for lead in leads)


@pytest.mark.asyncio
async def test_discovery_merge_refreshes_unified_profile():
    seed_account = _enriched_account(
        "github.com",
        "alice",
        bio="Dev",
        email="alice@projects.example.org",
        website="projects.example.org",
    )
    seed_fusion = FusionOutput(deduplicated_entities=[seed_account], fusion_score=0.7)
    seed_fusion, seed_evidence = await evidence_engine.extract(
        seed_fusion, seed_query="alice", enrich_public_profiles=False
    )
    seed = FeatureResult(
        feature="username_search",
        query="alice",
        fusion=seed_fusion,
        evidence_extraction=seed_evidence,
        tool_results=[ToolResult(tool="sherlock", success=True, data=[])],
    )

    hop_entity = Entity(
        type="domain",
        value="projects.example.org",
        sources=["theharvester"],
        fusion_score=0.6,
        metadata={"hostname": "projects.example.org", "platform": "domain"},
    )
    hop = FeatureResult(
        feature="domain_intel",
        query="projects.example.org",
        fusion=FusionOutput(deduplicated_entities=[hop_entity], fusion_score=0.6),
        tool_results=[ToolResult(tool="theharvester", success=True, data=[])],
    )

    engine = RecursiveDiscoveryEngine()
    with patch("services.pivot.engine.auto_pivot_engine._run_hop", new_callable=AsyncMock) as run_hop:
        run_hop.return_value = (hop, None)
        with patch("services.persistence.postgres.persist_discovery_chain", return_value=None):
            final = await engine.expand(
                seed_query="alice",
                seed_query_type="username",
                seed_result=seed,
                config=DiscoveryConfig(enabled=True, max_depth=2, max_hops=2, max_leads_per_hop=5),
            )

    assert final.evidence_extraction is not None
    assert final.evidence_extraction.unified_profile is not None
    assert final.evidence_extraction.platforms_analyzed >= 1
    assert final.discovery is not None
    assert final.discovery.total_hops >= 1
    entity_types = {e.type for e in final.fusion.deduplicated_entities}
    assert "account" in entity_types
    assert "domain" in entity_types


@pytest.mark.asyncio
async def test_pipeline_order_evidence_before_discovery():
    """Seed evidence extraction must complete before discovery reads entities."""
    entity = _enriched_account(
        "github.com",
        "alice",
        email="alice@example.org",
    )
    fusion = FusionOutput(deduplicated_entities=[entity], fusion_score=0.8)
    fusion, evidence = await evidence_engine.extract(fusion, seed_query="alice", enrich_public_profiles=False)

    seed = FeatureResult(
        feature="username_search",
        query="alice",
        fusion=fusion,
        evidence_extraction=evidence,
        tool_results=[],
    )

    engine = RecursiveDiscoveryEngine()
    hop_stub = FeatureResult(
        feature="email_intel",
        query="alice@example.org",
        fusion=FusionOutput(deduplicated_entities=[], fusion_score=0.5),
        tool_results=[],
    )
    with patch("services.pivot.engine.auto_pivot_engine._run_hop", new_callable=AsyncMock) as run_hop:
        run_hop.return_value = (hop_stub, None)
        with patch("services.persistence.postgres.persist_discovery_chain", return_value=None):
            await engine.expand(
                seed_query="alice",
                seed_query_type="username",
                seed_result=seed,
                config=DiscoveryConfig(enabled=True, max_depth=1, max_hops=1, max_leads_per_hop=5),
            )

    first_call_args = run_hop.call_args
    assert first_call_args is not None
    lead = first_call_args[0][0]
    assert lead.query == "alice@example.org"
    assert lead.lead_type == "email"
