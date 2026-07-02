"""Tests for Google SERP-style dork parsing."""

from services.google_dorking.serp_parser import extract_hit_intelligence, process_search_hit


def test_plain_search_hit_extracts_blog_and_email():
    hit = {
        "title": "alice dev blog",
        "url": "https://blogs.example.org/alice",
        "snippet": "Contact alice@example.org — blog posts about python",
        "dork_query": "alice",
        "dork_category": "google_plain",
        "source": "ddgs_auto",
    }
    processed = process_search_hit(hit, seed_query="alice", query_type="username")
    assert processed is not None
    structured = processed["structured_intelligence"]
    assert "alice@example.org" in structured["emails"]
    assert structured["blogs"] or processed["hit_type"] == "blog"


def test_forum_hit_classified():
    intel = extract_hit_intelligence(
        title="alice on community forum",
        url="https://community.example.org/forum/thread/alice-intro",
        snippet="Discussion thread started by alice about open source",
        dork_category="forum_mentions",
        seed_query="alice",
    )
    assert intel["structured_intelligence"]["forums"] or intel["hit_type"] == "forum"


def test_image_url_extracted_from_snippet():
    intel = extract_hit_intelligence(
        title="alice photo",
        url="https://photos.example.org/user/alice",
        snippet="Profile photo https://photos.example.org/alice/avatar.jpg for alice",
        dork_category="media_images",
        seed_query="alice",
    )
    assert any("avatar.jpg" in img for img in intel["structured_intelligence"]["images"])
