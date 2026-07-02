"""Search intelligence extraction — evidence-centric, not platform-priority."""

from schemas.fusion import Entity
from services.evidence.platform_deep import is_enrichable_profile_url, is_deep_fetchable_url
from services.evidence.search_intelligence import (
    classify_search_hit,
    extract_all_search_findings,
    extract_search_findings,
)


def _dork_entity(**meta) -> Entity:
    base = {
        "check_type": "google_dork",
        "url": "https://community.example.org/user/TestUser42",
        "title": "TestUser42 profile",
        "snippet": "Posts about machine learning and open source",
        "dork_category": "profile_mentions",
    }
    base.update(meta)
    return Entity(
        type="document",
        value=str(base["url"]),
        sources=["google_dorking"],
        fusion_score=0.7,
        metadata=base,
    )


def test_classify_profile_by_url_shape():
    assert classify_search_hit(
        "https://community.example.org/user/TestUser42",
        "TestUser42 profile",
        "",
    ) == "profile"


def test_classify_blog_by_path():
    assert classify_search_hit(
        "https://blogs.example.org/article/testuser42-writeup",
        "My Article",
        "",
    ) in ("blog", "article")


def test_is_enrichable_accepts_any_profile_url():
    assert is_enrichable_profile_url("https://community.example.org/user/alice")
    assert is_enrichable_profile_url("https://blogs.example.org/@alice")
    assert is_enrichable_profile_url("https://profiles.example.org/alice")
    assert not is_enrichable_profile_url("https://example.com/")


def test_is_deep_fetchable_alias():
    url = "https://profiles.example.org/alice/"
    assert is_deep_fetchable_url(url) == is_enrichable_profile_url(url)


def test_extract_search_findings_for_attributed_dork():
    entity = _dork_entity()
    findings = extract_search_findings(entity, seed_query="TestUser42")
    fields = {fp.field for fp in findings}
    assert "search_hit" in fields
    assert "search_snippet" in fields
    assert "public_link" in fields


def test_extract_all_search_findings_dedupes():
    entities = [_dork_entity(), _dork_entity()]
    out = extract_all_search_findings(entities, seed_query="TestUser42")
    hits = [fp for fp in out if fp.field == "search_hit"]
    assert len(hits) == 1


def test_unattributed_dork_yields_no_findings():
    entity = _dork_entity(
        title="Someone Else - Other Corp",
        snippet="Unrelated person",
        url="https://profiles.example.org/in/someone-else",
    )
    assert extract_search_findings(entity, seed_query="TestUser42") == []
