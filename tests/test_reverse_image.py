"""Tests for reverse image discovery and image correlation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from schemas.image_intelligence import ImageFinding, ImageIntelligenceOutput
from schemas.reverse_image import ReverseImageMatch
from services.image_correlation.engine import image_correlation_engine
from services.reverse_image.engine import ReverseImageDiscoveryEngine
from services.reverse_image.leads import evidence_chains_from_matches, leads_from_matches
from services.reverse_image.matcher import classify_match_type
from services.reverse_image.registry import build_sources, list_sources


def test_classify_match_type_identical_url():
    url = "https://cdn.example.org/photo.jpg"
    assert classify_match_type(url_a=url, url_b=url) == "identical"


def test_classify_match_type_profile_photo():
    assert classify_match_type(
        url_a="https://x.com/a.jpg",
        url_b="https://github.com/user/avatar.png",
        platform="github.com",
        title="user avatar",
    ) in ("profile_photo", "similar", "cross_platform_reuse")


def test_leads_from_matches_generates_profile_and_username_leads():
    match = ReverseImageMatch(
        match_id=str(uuid4()),
        source="google_lens",
        match_type="profile_photo",
        match_url="https://github.com/alice",
        page_url="https://github.com/alice",
        confidence=0.82,
        profile_urls=["https://github.com/alice"],
    )
    leads = leads_from_matches([match], source_query="seed.png", depth=0)
    queries = {l.query for l in leads}
    assert "alice" in queries
    assert "github.com" in queries


def test_evidence_chains_from_matches_builds_path():
    match = ReverseImageMatch(
        match_id=str(uuid4()),
        source="yandex_images",
        match_type="similar",
        match_url="https://example.org/post/1",
        confidence=0.7,
        profile_urls=["https://linkedin.com/in/alice"],
        organizations=["Acme Corp"],
    )
    chains = evidence_chains_from_matches([match], seed_image="/tmp/seed.jpg")
    assert len(chains) == 1
    steps = [l.step for l in chains[0].links]
    assert steps[0] == "image"
    assert "match" in steps
    assert "profile" in steps
    assert "organization" in steps


def test_sources_registered():
    import services.reverse_image.sources.web  # noqa: F401
    import services.reverse_image.sources.investigation_db  # noqa: F401

    names = list_sources()
    assert "google_lens" in names
    assert "public_search" in names
    assert len(build_sources()) >= 5


def test_image_correlation_merges_face_and_reverse_signals():
    intel = ImageIntelligenceOutput(
        image_source="seed.jpg",
        face_count=1,
        findings=[
            ImageFinding(
                category="face",
                field="face_embedding",
                value="face_0",
                source_tool="insightface",
                confidence=0.88,
                evidence={"face_quality_score": 0.9, "embedding_signature": "abc123"},
            ),
        ],
        perceptual_hashes={"phash": "deadbeef"},
    )
    discovery_matches = [
        ReverseImageMatch(
            match_id=str(uuid4()),
            source="google_lens",
            match_type="profile_photo",
            match_url="https://github.com/alice",
            confidence=0.8,
            profile_urls=["https://github.com/alice"],
            provenance={"hash_verified": True, "hash_similarity": 0.88},
        ),
    ]
    from schemas.reverse_image import ReverseImageDiscoveryOutput

    discovery = ReverseImageDiscoveryOutput(
        seed_image="seed.jpg",
        matches=discovery_matches,
        total_matches=1,
    )
    out = image_correlation_engine.correlate(
        seed_image="seed.jpg",
        fusion=None,
        image_intel=intel,
        reverse_discovery=discovery,
    )
    assert out.identity_candidates
    assert out.face_matches
    assert out.reverse_matches
    assert out.confidence_breakdown.get("face_analysis", 0) > 0
    assert out.confidence_breakdown.get("reverse_image", 0) > 0


@pytest.mark.asyncio
async def test_reverse_engine_runs_sources_in_parallel(tmp_path):
    img = tmp_path / "seed.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    fake_match = ReverseImageMatch(
        match_id=str(uuid4()),
        source="google_lens",
        match_type="similar",
        match_url="https://example.org/img.png",
        confidence=0.75,
        provenance={"hash_verified": True, "hash_similarity": 0.9},
    )

    class FakeSource:
        name = "google_lens"

        async def search(self, image_path, image_url, *, seed_query, context=None):
            return [fake_match]

    with patch("services.reverse_image.engine.build_sources", return_value=[FakeSource()]):
        with patch("adapters.image_common.resolve_image_source", new=AsyncMock(return_value=(str(img), None, None))):
            engine = ReverseImageDiscoveryEngine(source_names=["google_lens"])
            result = await engine.discover(str(img), seed_query="seed.png")

    assert result.total_matches == 1
    assert result.matches[0].match_url == "https://example.org/img.png"
    assert result.generated_leads
    assert result.evidence_chains
    entities = engine.matches_to_entities(result)
    assert any(e.type == "image" for e in entities)
    assert any(e.type == "account" for e in entities) is False  # no profile_urls in fake match
