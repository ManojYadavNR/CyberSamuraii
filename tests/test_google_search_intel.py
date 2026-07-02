"""Tests for Google username search intel extraction."""

import unittest

from services.discovery.attribution import dork_hit_attributed
from services.evidence.google_search_intel import (
    _college_names_from_hit,
    _extract_colleges,
    _is_social_highlight,
    build_google_search_intel,
)
from schemas.fusion import Entity


class TestGoogleSearchIntel(unittest.TestCase):
    def test_instagram_post_attributed_when_seed_in_snippet(self):
        assert dork_hit_attributed(
            url="https://www.instagram.com/p/ABC123/",
            title="Hackathon win",
            snippet="Manoj Yadav NR team celebration photo",
            seed_query="ManojYadavNR",
            dork_query='site:instagram.com "Manoj Yadav NR" hackathon',
            dork_category="social_post_search",
        )
        assert not dork_hit_attributed(
            url="https://www.instagram.com/p/ABC123/",
            title="Hackathon win",
            snippet="Team celebration photo",
            seed_query="ManojYadavNR",
            dork_query='site:instagram.com "Manoj Yadav NR" hackathon',
            dork_category="social_post_search",
        )

    def test_college_names_from_facebook_post(self):
        hit = {
            "title": "Cit NC - Congratulations ManojYadavNR for winning Smart India Hackathon",
            "snippet": "Cambridge Institute of Technology celebrates our student ManojYadavNR",
            "url": "https://www.facebook.com/cit.nc/photos/123456",
        }
        names = _college_names_from_hit(hit)
        assert "Cambridge Institute of Technology" in names
        assert "Cit NC" in names

    def test_extract_colleges_requires_seed_in_title(self):
        hits = [
            {
                "title": "HACKTU 7.0 Winners! We are proud to share",
                "snippet": "Congratulations to Manoj Yadav NR on HackToFuture 3.0",
                "url": "https://www.facebook.com/Pietofficial/posts/abc",
                "dork_category": "social_post_search",
                "dork_query": 'site:facebook.com "Manoj Yadav NR" winner',
            }
        ]
        colleges = _extract_colleges(hits, seed_query="ManojYadavNR")
        assert not colleges

    def test_extract_colleges_includes_page_url(self):
        hits = [
            {
                "title": "Cit NC - Congratulations ManojYadavNR",
                "snippet": "Cambridge Institute of Technology is proud",
                "url": "https://www.facebook.com/cit.nc/photos/999",
                "dork_category": "social_post_search",
                "dork_query": 'site:facebook.com "Manoj Yadav NR" hackathon',
            }
        ]
        # Patch attribution through full pipeline
        entities = [
            Entity(
                entity_id="e1",
                type="document",
                value=hits[0]["url"],
                fusion_score=0.9,
                sources=["google_dorking"],
                metadata={
                    "check_type": "google_dork",
                    "url": hits[0]["url"],
                    "title": hits[0]["title"],
                    "snippet": hits[0]["snippet"],
                    "dork_category": hits[0]["dork_category"],
                    "dork_query": hits[0]["dork_query"],
                    "serp_phase": "social_pass1",
                    "username_attributed": True,
                },
            )
        ]
        intel = build_google_search_intel(entities, seed_query="ManojYadavNR")
        assert intel["colleges"]
        assert intel["colleges"][0]["page_url"] == "https://www.facebook.com/cit.nc"
        assert "Cambridge Institute of Technology" in intel["colleges"][0]["college"]

    def test_is_social_highlight_instagram_post(self):
        row = {
            "platform": "instagram",
            "url": "https://www.instagram.com/reel/XYZ/",
        }
        assert _is_social_highlight(row)


if __name__ == "__main__":
    unittest.main()
