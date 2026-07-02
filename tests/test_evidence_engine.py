"""Tests for Universal Evidence Extraction Engine."""

import pytest

from schemas.fusion import Entity, FusionOutput
from services.evidence.engine import (
    UniversalEvidenceExtractionEngine,
    build_unified_person_profile,
    extract_account_intelligence,
)
from services.evidence.maigret_parser import parse_maigret_payload


def _account_entity(**kwargs) -> Entity:
    meta = {
        "verified": True,
        "check_type": "live_scan",
        "status": "maigret_claimed",
        "platform": "github.com",
        "url": "https://github.com/alice",
        "username": "alice",
        **kwargs.pop("metadata", {}),
    }
    return Entity(
        type="account",
        value="github.com/alice",
        sources=["maigret"],
        fusion_score=0.8,
        metadata=meta,
        **kwargs,
    )


def test_parse_maigret_payload():
    payload = parse_maigret_payload({
        "ids": {"FullName": "Alice Smith", "bio": "Engineer", "location": "NYC"},
        "ids_user": {"username": "alice"},
    })
    assert payload["display_name"] == "Alice Smith"
    assert payload["bio"] == "Engineer"
    assert payload["location"] == "NYC"
    assert payload["username"] == "alice"


def test_extract_account_intelligence_from_metadata():
    entity = _account_entity(metadata={
        "verified": True,
        "check_type": "live_scan",
        "platform": "facebook.com",
        "url": "https://facebook.com/alice",
        "username": "alice",
        "display_name": "Alice Smith",
        "bio": "Lives in NYC",
        "location": "New York",
        "website": "alice.dev",
        "email": "alice@example.org",
        "avatar_url": "https://cdn.example.org/alice.png",
        "organization": "Example Labs",
    })
    profile = extract_account_intelligence(entity)
    assert profile is not None
    assert profile.display_name == "Alice Smith"
    assert profile.bio == "Lives in NYC"
    assert profile.location == "New York"
    assert profile.email == "alice@example.org"
    assert profile.organizations == ["Example Labs"]
    assert len(profile.extracted_fields) >= 6


def test_unified_profile_aggregates_all_platforms():
    github = extract_account_intelligence(_account_entity(metadata={
        "platform": "github.com", "username": "alice", "bio": "Open source dev",
        "display_name": "Alice Dev",
    }))
    facebook = extract_account_intelligence(_account_entity(metadata={
        "platform": "facebook.com", "username": "alice", "location": "New York",
        "organization": "Example Labs",
    }))
    youtube = extract_account_intelligence(_account_entity(metadata={
        "platform": "youtube.com", "username": "alice", "bio": "Tech videos",
        "avatar_url": "https://yt.example/alice.jpg",
    }))

    unified = build_unified_person_profile(
        [github, facebook, youtube],  # type: ignore[arg-type]
        seed_query="alice",
    )
    assert unified.platform_count == 3
    assert unified.primary_display_name == "Alice Dev"
    assert any(p.value == "New York" for p in unified.locations)
    assert any(p.value == "Open source dev" for p in unified.bios)
    assert any(p.value == "Example Labs" for p in unified.organizations)
    assert len(unified.platform_profiles) == 3


@pytest.mark.asyncio
async def test_evidence_engine_enriches_entities():
    entities = [
        _account_entity(metadata={
            "platform": "github.com", "username": "octocat", "bio": "GitHub mascot",
        }),
        Entity(
            type="account",
            value="facebook.com/alice",
            sources=["maigret"],
            fusion_score=0.7,
            metadata={
                "verified": True,
                "check_type": "live_scan",
                "status": "maigret_claimed",
                "platform": "facebook.com",
                "url": "https://facebook.com/alice",
                "username": "alice",
                "location": "Boston",
            },
        ),
    ]
    fusion = FusionOutput(deduplicated_entities=entities, fusion_score=0.75)
    engine = UniversalEvidenceExtractionEngine()

    updated, output = await engine.extract(fusion, seed_query="alice", enrich_public_profiles=False)

    assert output.fields_extracted > 0
    assert output.unified_profile is not None
    assert output.unified_profile.platform_count >= 2
    assert output.unified_profile.verified_platform_count >= 2
    enriched = updated.deduplicated_entities[0]
    assert enriched.metadata.get("extracted_intelligence")
    assert enriched.metadata.get("intelligence_field_count", 0) > 0
