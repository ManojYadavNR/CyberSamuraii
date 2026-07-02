"""Tests for Google dork query generation and fusion integration."""

import os
import unittest
from unittest.mock import AsyncMock, patch

from schemas.common import ToolResult
from services.fusion_engine import DataFusionEngine
from services.google_dorking.queries import build_dork_queries


class TestDorkQueries(unittest.TestCase):
    def test_username_dorks_include_exact_and_generic_queries(self):
        dorks = build_dork_queries("TestUser42", "username")
        queries = [d.query for d in dorks]
        categories = {d.category for d in dorks}
        assert any('"TestUser42"' in d for d in queries)
        assert any("inurl:testuser42" in d for d in queries)
        assert "profile_mentions" in categories

    def test_email_dorks_quote_address(self):
        dorks = build_dork_queries("alice@example.org", "email")
        assert any("alice@example.org" in d.query for d in dorks)
        categories = {d.category for d in dorks}
        assert "email_pastes" in categories
        assert "email_dev_profiles" in categories

    def test_gmail_dorks_include_groups_and_github(self):
        from services.google_dorking.email_queries import build_email_dork_queries

        dorks = build_email_dork_queries("manojmanu938055@gmail.com")
        queries = [d.query for d in dorks]
        categories = {d.category for d in dorks}
        assert any("groups.google.com" in q for q in queries)
        assert "email_gmail_github" in categories
        assert "email_gmail_hackathons" in categories

    def test_domain_dorks_use_site_operator(self):
        dorks = build_dork_queries("example.org", "domain")
        assert dorks[0].query == "site:example.org"


class TestGoogleDorkingFusion(unittest.TestCase):
    def test_google_dork_hits_become_documents_not_accounts(self):
        engine = DataFusionEngine()
        output = engine.fuse(
            [
                ToolResult(
                    tool="google_dorking",
                    success=True,
                    data=[
                        {
                            "platform": "github.com",
                            "url": "https://github.com/alice",
                            "title": "Alice on GitHub",
                            "snippet": "Open source developer alice@example.org",
                            "dork_query": 'site:github.com "alice"',
                            "check_type": "google_dork",
                            "verified": False,
                        }
                    ],
                )
            ],
            "username_search",
            "alice",
        )
        types = {e.type for e in output.deduplicated_entities}
        assert "document" in types
        assert not any(e.type == "account" for e in output.deduplicated_entities)
        assert not any(e.type == "email" for e in output.deduplicated_entities)

    def test_attributed_email_on_seed_profile_creates_email_entity(self):
        engine = DataFusionEngine()
        output = engine.fuse(
            [
                ToolResult(
                    tool="google_dorking",
                    success=True,
                    data=[
                        {
                            "platform": "google_search",
                            "email": "alice@example.org",
                            "dork_query": 'site:github.com "alice"',
                            "check_type": "google_dork",
                            "username_attributed": True,
                            "source_url": "https://github.com/alice",
                            "discovery_source": "username_search",
                        }
                    ],
                )
            ],
            "username_search",
            "alice",
        )
        emails = [e for e in output.deduplicated_entities if e.type == "email"]
        assert len(emails) == 1
        assert emails[0].value == "alice@example.org"
        assert emails[0].metadata.get("username_attributed") is True

    def test_unrelated_email_from_different_profile_not_promoted(self):
        engine = DataFusionEngine()
        output = engine.fuse(
            [
                ToolResult(
                    tool="google_dorking",
                    success=True,
                    data=[
                        {
                            "platform": "github.com",
                            "url": "https://github.com/bob",
                            "title": "bob on GitHub",
                            "snippet": "Email bob@other.com",
                            "dork_query": 'site:github.com "alice"',
                            "check_type": "google_dork",
                        }
                    ],
                )
            ],
            "username_search",
            "alice",
        )
        assert not any(e.type == "email" for e in output.deduplicated_entities)


class TestDdgsClient(unittest.TestCase):
    def test_search_sync_parses_hits(self):
        from services.google_dorking.ddgs_client import _search_sync

        class FakeDDGS:
            def text(self, _q, max_results=5, backend="auto"):
                return [
                    {"title": "Alice GitHub", "href": "https://github.com/alice", "body": "Developer"},
                ]

        import services.google_dorking.ddgs_client as mod

        original = None
        try:
            import ddgs
            original = ddgs.DDGS
            ddgs.DDGS = FakeDDGS
            hits = _search_sync('"alice"', num=5, backend="auto")
            assert len(hits) == 1
            assert hits[0]["url"] == "https://github.com/alice"
            assert hits[0]["source"] == "ddgs_auto"
        finally:
            if original is not None:
                ddgs.DDGS = original


class TestGoogleScraper(unittest.TestCase):
    def test_parse_google_redirect_links(self):
        from services.google_dorking.scraper import _parse_google_html

        html = """
        <a href="/url?q=https://github.com/alice&amp;sa=U&amp;ved=0">
          <h3>Alice GitHub</h3>
        </a>
        <a href="/url?q=https://example.org/profile&amp;sa=U">
          <h3>Profile page</h3>
        </a>
        """
        hits = _parse_google_html(html, '"alice"', max_results=5)
        urls = {h["url"] for h in hits}
        assert "https://github.com/alice" in urls
        assert "https://example.org/profile" in urls


class TestGoogleDorkingAdapter(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_available_without_api_keys(self):
        from adapters.google_dorking import GoogleDorkingAdapter

        adapter = GoogleDorkingAdapter()
        with patch.dict(os.environ, {}, clear=True):
            ok, err = adapter.verify_tool()
            assert ok
            assert err is None

    async def test_adapter_parses_search_hits(self):
        from adapters.google_dorking import GoogleDorkingAdapter

        adapter = GoogleDorkingAdapter()
        mock_hits = [
            {
                "title": "Profile",
                "url": "https://example.org/user/alice",
                "snippet": "Contact alice@example.org",
                "display_link": "example.org",
                "dork_query": '"alice"',
            }
        ]
        with patch(
            "adapters.google_dorking.run_dork_queries",
            new=AsyncMock(return_value=mock_hits),
        ):
            result = await adapter._execute("alice")
        assert result.success
        assert any(item.get("check_type") == "google_dork" for item in result.data)
        assert any(item.get("email") == "alice@example.org" for item in result.data)


    def test_college_facebook_hackathon_displayable_with_seed_in_snippet(self):
        from services.google_dorking.filters import dork_hit_displayable

        ok = dork_hit_displayable(
            url="https://www.facebook.com/CambridgeInstitute/posts/123456789",
            title="Congratulations hackathon winners",
            snippet="Our student manojyadavnr won first place at the national coding hackathon.",
            seed_query="manojyadavnr",
            dork_category="achievements",
        )
        assert ok is True

    def test_random_hackathon_rejected_without_seed(self):
        from services.google_dorking.filters import dork_hit_displayable

        ok = dork_hit_displayable(
            url="https://news.example.edu/other-student-wins",
            title="John wins hackathon",
            snippet="Another student won the coding hackathon at college fest.",
            seed_query="manojyadavnr",
            dork_category="achievements",
        )
        assert ok is False

    def test_dynamic_query_pipeline_from_keywords(self):
        from services.google_dorking.dynamic_queries import build_dynamic_dork_queries
        from services.google_dorking.keyword_discovery import DiscoveredKeyword

        queries = build_dynamic_dork_queries(
            "TestUser42",
            [DiscoveredKeyword(phrase="Regional Coding Fest", category="achievement", score=0.9)],
        )
        assert queries
        assert "Regional Coding Fest" in queries[0].query

    def test_facebook_post_url_attributed_by_slug(self):
        from services.google_dorking.filters import dork_hit_displayable

        ok = dork_hit_displayable(
            url="https://www.facebook.com/cit.nc/photos/congratulations-to-manoj-yadav-nr-kirana-gv-mahanthesh-sk-mah",
            title="Congratulations to Manoj Yadav NR, Kirana GV",
            snippet="Runner-up in HackToFuture 3.0",
            seed_query="ManojYadavNR",
            dork_category="achievements",
        )
        assert ok is True


if __name__ == "__main__":
    unittest.main()
