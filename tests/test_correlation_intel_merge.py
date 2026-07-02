"""Tests for merging Google search intel onto account entities for correlation."""

from schemas.fusion import Entity
from services.evidence.google_search_intel import merge_search_intel_onto_accounts
from services.correlation.account_parser import entity_to_profile
from services.correlation.activity_data import collect_post_snippets, collect_timestamps


def _account(platform: str, handle: str, **meta) -> Entity:
    return Entity(
        type="account",
        value=f"{platform}/{handle}",
        sources=["sherlock", "maigret"],
        metadata={
            "platform": platform,
            "username": handle,
            "url": f"https://{platform}/{handle}",
            "verified": True,
            "check_type": "live_scan",
            "status": "maigret_claimed",
            "content_seed_verified": True,
            **meta,
        },
        fusion_score=0.9,
    )


def test_merge_search_intel_onto_matching_accounts():
    entities = [
        _account("github.com", "TestUser42"),
        _account("instagram.com", "testuser42"),
        _account("facebook.com", "testuser42"),
        _account("twitter.com", "unrelated_person"),
    ]
    google_intel = {
        "social_posts": [
            {
                "platform": "instagram",
                "title": "Achievement post",
                "snippet": "Runner up at build fast hackathon with MERN stack",
            }
        ],
        "hackathon_wins": [
            {
                "hackathon": "Build Fast Hackathon",
                "snippet": "Congratulations on runner up placement",
                "title": "College fest results",
                "platform": "facebook",
            }
        ],
        "colleges": [
            {
                "college": "Example Institute of Technology",
                "snippet": "Student from Example Institute of Technology",
                "title": "Example Institute - Facebook",
                "facebook_page_url": "https://facebook.com/testuser42",
            }
        ],
        "highlights": [
            {"title": "Developer portfolio", "snippet": "Full stack developer projects", "platform": "web"}
        ],
    }

    merged = merge_search_intel_onto_accounts(entities, google_intel, seed_query="TestUser42")
    assert merged == 2

    ig = next(e for e in entities if "instagram" in e.value)
    fb = next(e for e in entities if "facebook" in e.value)
    gh = next(e for e in entities if "github" in e.value)
    unrelated = next(e for e in entities if "twitter" in e.value)

    assert ig.metadata.get("correlation_intel_merged")
    assert "Runner up" in " ".join(ig.metadata.get("recent_posts") or [])
    assert not ig.metadata.get("achievements")
    assert fb.metadata.get("schools")
    assert fb.metadata.get("achievements")
    assert not gh.metadata.get("correlation_intel_merged")
    assert not gh.metadata.get("schools")
    assert not gh.metadata.get("achievements")
    assert "Runner up" not in " ".join(gh.metadata.get("recent_posts") or [])
    assert not unrelated.metadata.get("correlation_intel_merged")

    profile = entity_to_profile(ig)
    assert profile is not None
    assert profile.behavior_corpus
    assert "hackathon" in profile.behavior_corpus.lower()

    gh_profile = entity_to_profile(gh)
    assert gh_profile is not None
    assert not gh_profile.behavior_corpus or "hackathon" not in gh_profile.behavior_corpus.lower()


def test_profile_uses_merged_posting_times():
    entity = _account(
        "instagram.com",
        "testuser42",
        recent_posts=[{"text": "Late night coding session", "created_at": "2024-06-15T23:10:00"}],
        posting_times=["2024-06-15T23:10:00"],
    )
    profile = entity_to_profile(entity)
    assert profile is not None
    posts = collect_post_snippets(entity.metadata or {})
    times = collect_timestamps(entity.metadata or {}, posts)
    assert posts
    assert times
    assert profile.activity_windows
