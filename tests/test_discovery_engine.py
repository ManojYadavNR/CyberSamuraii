"""Tests for entity-aware discovery expansion."""

from schemas.common import FeatureResult, ToolResult
from schemas.fusion import Entity, FusionOutput
from services.discovery.lead_extractor import extract_leads_from_entity, extract_leads_from_result
from services.discovery.router import build_routable_lead, route_lead_query
from services.discovery.validators import is_fake_url_username, is_plausible_handle


def test_route_email_lead():
    routed = route_lead_query("analyst@example.org")
    assert routed == ("email_intel", "analyst@example.org", "email")


def test_route_domain_from_url():
    routed = route_lead_query("https://docs.example.org/team/alice")
    assert routed == ("domain_intel", "docs.example.org", "domain")


def test_route_account_handle():
    routed = route_lead_query("someplatform:alice_johnson", lead_type="account")
    assert routed is not None
    feature, query, lead_type = routed
    assert feature == "username_search"
    assert query == "alice_johnson"
    assert lead_type == "username"


def test_route_image_url():
    routed = route_lead_query("https://cdn.example.org/avatars/alice.png")
    assert routed == ("image_intel", "https://cdn.example.org/avatars/alice.png", "image")


def test_blocks_url_as_username():
    assert route_lead_query("https://github.com/manojyadavnr", lead_type="username") is None
    assert route_lead_query("github.commanojyadavnr", lead_type="username") is None
    assert is_fake_url_username("github.commanojyadavnr")
    assert not is_plausible_handle("github.commanojyadavnr")


def test_extract_leads_from_email_entity():
    entity = Entity(
        type="email",
        value="found@example.org",
        metadata={"verified": True, "username_attributed": True},
        fusion_score=0.8,
    )
    leads = extract_leads_from_entity(entity, source_query="found", depth=1, max_leads=5)
    assert len(leads) == 1
    assert leads[0].query == "found@example.org"
    assert leads[0].feature == "email_intel"


def test_extract_leads_skips_unverified_dataset_lookup():
    entity = Entity(
        type="account",
        value="example.com:ghost",
        metadata={"check_type": "dataset_lookup", "verified": False},
    )
    leads = extract_leads_from_entity(entity, source_query="seed", depth=1, max_leads=5)
    assert leads == []


def test_account_url_does_not_spawn_username_search():
    entity = Entity(
        type="account",
        value="https://github.com/manojyadavnr",
        metadata={
            "verified": True,
            "url": "https://github.com/manojyadavnr",
            "platform": "GitHub",
        },
        fusion_score=0.8,
    )
    leads = extract_leads_from_entity(entity, source_query="manojyadavnr", depth=1, max_leads=10)
    assert all(lead.feature != "username_search" for lead in leads)
    assert all("github.commanojyadavnr" not in lead.query for lead in leads)


def test_account_profile_extracts_metadata_intelligence():
    entity = Entity(
        type="account",
        value="https://github.com/alice",
        metadata={
            "verified": True,
            "platform": "GitHub",
            "url": "https://github.com/alice",
            "username": "alice",
            "website": "projects.example.org",
            "email": "alice@projects.example.org",
            "avatar_url": "https://cdn.example.org/avatars/alice.png",
            "organization": "Example Labs",
        },
        fusion_score=0.7,
    )
    leads = extract_leads_from_entity(entity, source_query="alice", depth=1, max_leads=10)
    queries = {lead.query for lead in leads}
    features = {lead.feature for lead in leads}
    assert "alice@projects.example.org" in queries
    assert "projects.example.org" in queries
    assert "alice" in queries
    assert "username_search" in features
    assert "email_intel" in features
    assert "domain_intel" in features
    assert "image_intel" in features


def test_account_image_lead_from_avatar():
    entity = Entity(
        type="account",
        value="https://github.com/alice",
        metadata={
            "verified": True,
            "platform": "GitHub",
            "avatar_url": "https://cdn.example.org/avatars/alice.png",
            "username": "alice",
        },
        fusion_score=0.7,
    )
    leads = extract_leads_from_entity(entity, source_query="alice", depth=1, max_leads=10)
    queries = {lead.query for lead in leads}
    assert "https://cdn.example.org/avatars/alice.png" in queries
def test_extract_leads_from_result_includes_metadata_website():
    result = FeatureResult(
        feature="username_search",
        query="alice",
        fusion=FusionOutput(
            deduplicated_entities=[
                Entity(
                    type="account",
                    value="profile.example:alice",
                    metadata={
                        "verified": True,
                        "username": "alice",
                        "website": "projects.example.org",
                        "email": "alice@projects.example.org",
                    },
                    fusion_score=0.7,
                )
            ]
        ),
    )
    leads = extract_leads_from_result(result, source_query="alice", depth=1, max_leads=10)
    queries = {lead.query for lead in leads}
    assert "projects.example.org" in queries
    assert "alice@projects.example.org" in queries
    assert all("profile.example:alice" not in lead.query for lead in leads)


def test_leads_include_provenance_metadata():
    entity = Entity(
        type="email",
        value="user@example.org",
        metadata={"verified": True, "username_attributed": True},
        fusion_score=0.9,
    )
    leads = extract_leads_from_entity(entity, source_query="user", depth=1, max_leads=5)
    assert leads[0].metadata.get("expansion_strategy") == "email_account_pivot"
    assert leads[0].metadata.get("source_field") == "email"


def test_build_routable_lead_returns_none_for_invalid():
    assert build_routable_lead("!!!", lead_type="name") is None
