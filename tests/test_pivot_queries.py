"""Entity pivot dork generation."""

from services.google_dorking.pivot_queries import build_pivot_dork_queries, extract_entity_pivots


def test_extract_hashtag_and_facebook_slug():
    hits = [{
        "title": "Cambridge Institute - Congrats to alexdev42",
        "snippet": "Runner-up #HackFest2025 with alexdev42",
        "url": "https://www.facebook.com/examplecollege/photos/winners",
    }]
    pivots = extract_entity_pivots(hits, seed_query="alexdev42")
    site_slugs = pivots["site_slugs"]
    assert isinstance(site_slugs, dict)
    assert "examplecollege" in site_slugs.get("facebook.com", set())
    assert "#hackfest2025" in pivots["hashtags"]


def test_build_pivot_queries_from_slug():
    pivots = {
        "site_slugs": {"facebook.com": {"examplecollege"}},
        "hashtags": set(),
        "domains": set(),
        "institutions": set(),
        "events": set(),
    }
    queries = build_pivot_dork_queries("ManojYadavNR", pivots)
    texts = [q.query.lower() for q in queries]
    assert any("site:facebook.com/examplecollege" in t for t in texts)
