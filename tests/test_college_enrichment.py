"""Tests for dynamic college page enrichment."""

import unittest
from unittest.mock import AsyncMock, patch

from services.evidence.college_enrichment import (
    build_college_campus_search_queries,
    institution_name_from_text,
    _strip_platform_title,
)
from services.evidence.college_enrichment import CollegeCampusTarget


class TestCollegeEnrichment(unittest.TestCase):
    def test_institution_name_jalappa(self):
        name = institution_name_from_text("Jalappa Engineering College congratulates students")
        assert name == "Jalappa Engineering College"

    def test_institution_name_cambridge(self):
        name = institution_name_from_text("Cambridge Institute of Technology | Facebook")
        assert name == "Cambridge Institute of Technology"

    def test_strip_platform_title(self):
        assert _strip_platform_title("RV College of Engineering | Facebook") == "RV College of Engineering"

    def test_campus_queries_include_slug_hackathon_and_website(self):
        target = CollegeCampusTarget(
            facebook_slug="cit.nc",
            facebook_page_url="https://www.facebook.com/cit.nc",
            official_name="Cambridge Institute of Technology",
            instagram_handles={"cambridge_nc_official"},
            website_domain="cambridge.edu.in",
            hackathons={"HackToFuture 3.0"},
        )
        queries = [q.query for q in build_college_campus_search_queries("SomeUser42", [target])]
        assert any("site:facebook.com/cit.nc" in q for q in queries)
        assert any("HackToFuture" in q for q in queries)
        assert any("site:cambridge.edu.in" in q for q in queries)
        assert any("cambridge_nc_official" in q for q in queries)

    def test_enrich_colleges_from_page_og(self):
        from services.evidence.college_enrichment import enrich_google_search_intel_colleges

        html = """
        <html><head>
        <meta property="og:title" content="Jalappa Engineering College | Facebook" />
        <meta property="og:description" content="Official page" />
        <a href="https://jalappa.edu.in">Website</a>
        <a href="https://instagram.com/jalappa_college">Instagram</a>
        </head></html>
        """
        intel = {
            "colleges": [{
                "college": "Jalappa",
                "page_url": "https://www.facebook.com/jalappaenggcollege",
                "url": "https://www.facebook.com/jalappaenggcollege/posts/1",
                "platform": "facebook",
            }],
            "hackathon_wins": [],
        }

        async def run():
            with patch("services.evidence.college_enrichment._fetch_html", new=AsyncMock(return_value=html)):
                return await enrich_google_search_intel_colleges(intel, seed_query="SomeUser42")

        import asyncio
        out = asyncio.run(run())
        assert out["colleges"][0]["college"] == "Jalappa Engineering College"
        assert out["colleges"][0].get("website_url", "").endswith("jalappa.edu.in")


if __name__ == "__main__":
    unittest.main()
