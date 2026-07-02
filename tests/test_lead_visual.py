"""Lead visual engine tests."""

from services.lead_visual.classifier import classify_lead_type, is_junk_lead_url
from services.lead_visual.scorer import score_lead
from services.lead_visual.youtube import youtube_thumbnail


def test_classify_hackathon():
    t = classify_lead_type(
        url="https://devpost.com/software/winning-project",
        title="Manoj wins ABC Hackathon 2024",
        snippet="First place winner",
        dork_category="achievements",
    )
    assert t == "hackathon"


def test_junk_login_url():
    assert is_junk_lead_url("https://replit.com/login?goto=%2Fuser")


def test_score_hackathon_beats_profile():
    hack = score_lead(
        lead_type="hackathon",
        title="Winner at Tech Hackathon",
        snippet="college news",
        url="https://news.example.edu/hackathon",
        fusion_score=0.8,
    )
    profile = score_lead(
        lead_type="profile",
        title="user",
        snippet="",
        url="https://github.com/user",
        fusion_score=0.9,
    )
    assert hack > profile


def test_youtube_thumbnail():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert youtube_thumbnail(url) == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"


def test_build_lead_visuals_survives_unreachable_url():
    import asyncio

    from schemas.fusion import Entity
    from services.lead_visual.engine import build_lead_visuals

    entity = Entity(
        entity_id="hack_unreachable",
        type="document",
        value="https://news.example.edu/hackathon-win",
        fusion_score=0.85,
        metadata={
            "check_type": "google_dork",
            "url": "https://news.example.edu/hackathon-win",
            "title": "Student wins hackathon",
            "snippet": "manojyadavnr placed first at the campus hackathon.",
            "dork_category": "achievements",
            "username_attributed": True,
        },
    )

    out = asyncio.run(build_lead_visuals([entity], seed_query="manojyadavnr"))
    assert len(out.leads) == 1
    assert out.leads[0].lead_type == "hackathon"
    assert "hackathon" in out.leads[0].snippet.lower()
