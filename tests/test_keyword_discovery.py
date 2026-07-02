"""Tests for dynamic Google SERP keyword discovery."""

from services.google_dorking.dynamic_queries import build_dynamic_dork_queries, is_social_post_url
from services.google_dorking.keyword_discovery import DiscoveredKeyword, extract_keywords_from_serp


def test_extract_event_name_from_google_snippet():
    hits = [{
        "title": "College - Congratulations to alexdev42, team lead",
        "snippet": "alexdev42 was runner-up in National Coding Fest 2025 competing against 750+ teams.",
        "url": "https://www.facebook.com/examplecollege/photos/congratulations-alexdev42-team",
    }]
    keywords = extract_keywords_from_serp(hits, seed_query="alexdev42")
    phrases = {k.phrase.lower() for k in keywords}
    assert any("national coding fest" in p for p in phrases)


def test_extract_professional_org_without_hardcoding():
    hits = [{
        "title": "Jane Smith - Acme Robotics | LinkedIn",
        "snippet": "Software Engineer at Acme Robotics · Experience: Acme Robotics",
        "url": "https://www.linkedin.com/in/jane-smith-dev",
    }]
    keywords = extract_keywords_from_serp(hits, seed_query="janesmithdev")
    phrases = {k.phrase.lower() for k in keywords}
    assert any("acme" in p or "software engineer" in p for p in phrases)


def test_dynamic_queries_include_social_sites_per_term():
    from services.platform_registry import priority_social_domains

    social = priority_social_domains(2)
    keywords = [
        DiscoveredKeyword(phrase="National Coding Fest 2025", category="achievement", score=0.9),
        DiscoveredKeyword(phrase="State Polytechnic Institute", category="education", score=0.8),
    ]
    queries = build_dynamic_dork_queries("alexdev42", keywords)
    texts = [q.query.lower() for q in queries]
    assert any(f"site:{social[0]}" in t and "national coding fest" in t for t in texts)
    assert any(f"site:{social[1]}" in t and "state polytechnic" in t for t in texts)
    assert not any("hacktofuture" in t for t in texts)


def test_generic_hackathon_hit_rejected_without_seed():
    hits = [{
        "title": "Random hackathon winners",
        "snippet": "Another student won the coding hackathon.",
        "url": "https://example.edu/news",
    }]
    keywords = extract_keywords_from_serp(hits, seed_query="alexdev42")
    assert keywords == []


def test_is_social_post_url():
    assert is_social_post_url("https://www.facebook.com/college/posts/winners/123")
    assert is_social_post_url("https://www.instagram.com/p/ABC123/")
    assert not is_social_post_url("https://www.facebook.com/college/")


def test_display_name_seed_queries():
    from services.google_dorking.dynamic_queries import build_display_name_seed_queries, build_fallback_social_queries
    from services.platform_registry import priority_social_domains

    social = priority_social_domains(2)

    seeds = build_display_name_seed_queries("ManojYadavNR")
    assert any('"Manoj Yadav NR"' in s.query for s in seeds)
    assert not any("HackToFuture" in s.query for s in seeds)

    fallback = build_fallback_social_queries("ManojYadavNR")
    texts = [q.query.lower() for q in fallback]
    assert any(f"site:{social[0]}" in t and "manoj yadav nr" in t for t in texts)
    assert any(f"site:{social[1]}" in t and "hackathon" in t for t in texts)
