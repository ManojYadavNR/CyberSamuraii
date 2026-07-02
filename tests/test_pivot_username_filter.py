"""Pivot username hop filtering."""

import unittest

from schemas.fusion import Entity
from services.pivot.processors import process_entity


class TestPivotUsernameFilter(unittest.TestCase):
    def test_unrelated_handle_not_pivoted(self):
        entity = Entity(
            entity_id="acct1",
            type="account",
            value="instagram:lover",
            fusion_score=0.8,
            sources=["sherlock"],
            metadata={
                "platform": "instagram.com",
                "url": "https://instagram.com/lover",
                "username": "lover",
                "verified": True,
                "registered": True,
            },
        )
        result = process_entity(entity, source_query="ManojYadavNR", depth=1)
        usernames = [lead.query for lead in result.generated_leads if lead.lead_type == "username"]
        assert "lover" not in usernames

    def test_seed_handle_can_pivot(self):
        entity = Entity(
            entity_id="acct2",
            type="account",
            value="github:manojyadavnr",
            fusion_score=0.9,
            sources=["sherlock"],
            metadata={
                "platform": "github.com",
                "url": "https://github.com/manojyadavnr",
                "username": "manojyadavnr",
                "verified": True,
                "registered": True,
            },
        )
        result = process_entity(entity, source_query="ManojYadavNR", depth=1)
        usernames = [lead.query.lower() for lead in result.generated_leads if lead.lead_type == "username"]
        assert "manojyadavnr" in usernames


if __name__ == "__main__":
    unittest.main()
