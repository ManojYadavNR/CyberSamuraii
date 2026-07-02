"""Username pivot regressions — no bogus phones or avatar reverse-image hops."""

from uuid import uuid4

from schemas.fusion import Entity
from services.pivot.processors import process_entity


def _verified_github_account(**meta) -> Entity:
    return Entity(
        entity_id=str(uuid4()),
        type="account",
        value="github.com:manojyadavnr",
        sources=["sherlock"],
        fusion_score=0.9,
        metadata={
            "platform": "github.com",
            "url": "https://github.com/manojyadavnr",
            "username": "manojyadavnr",
            "display_name": "Manoj Yadav N R",
            "bio": "MERN STACK DEVELOPER",
            "avatar_url": "https://avatars.githubusercontent.com/u/123?v=4",
            "verified": True,
            "public_metadata": {"created_at": "2024-02-24", "followers": 10},
            **meta,
        },
    )


def test_username_seed_does_not_spawn_avatar_image_hops():
    entity = _verified_github_account()
    result = process_entity(entity, source_query="ManojYadavNR", depth=1)
    lead_types = {lead.lead_type for lead in result.generated_leads}
    assert "image" not in lead_types
    assert any(ev.field == "avatar_url" for ev in result.evidence)


def test_public_metadata_dates_not_treated_as_phones():
    entity = _verified_github_account()
    result = process_entity(entity, source_query="ManojYadavNR", depth=1)
    phone_leads = [l for l in result.generated_leads if l.lead_type == "phone"]
    phone_evidence = [e for e in result.evidence if e.field == "phone"]
    assert phone_leads == []
    assert phone_evidence == []
