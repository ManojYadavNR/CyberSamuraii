"""Deep profile enrichment tests."""

import pytest

from services.evidence.platform_deep import _parse_page, account_handles_align


def test_handle_alignment_allows_slug_variants():
    assert account_handles_align("ManojYadavNR", "manoj-yadav-nr")
    assert account_handles_align("testuser42", "TestUser42")


def test_collect_videos_from_channel_page():
    html = """
    <html><head>
    <meta property="og:title" content="Creator Channel" />
    <meta property="og:video" content="https://videos.example.org/embed/abc123" />
    </head><body>
    <a href="https://videos.example.org/watch?v=abc123">Latest upload</a>
    </body></html>
    """
    payload = _parse_page(html, "https://videos.example.org/@creatorhandle")
    assert payload.get("media_video")
    assert payload.get("videos")


def test_parse_page_extracts_post_timestamps():
    html = """
    <html><body>
    <script type="application/json">
    {"edges":[{"node":{"caption":"Runner up at regional hackathon #buildfast","created_at":"2024-03-15T23:45:12+0000"}}]}
    </script>
    "created_at":"2024-02-10T18:30:00Z"
    </body></html>
    """
    payload = _parse_page(html, "https://profiles.example.org/user/testuser42")
    posts = payload.get("recent_posts") or []
    assert posts
    assert payload.get("posting_times")
    assert any("hackathon" in str(p).lower() for p in posts)


def test_parse_page_extracts_og_bio_email_stats():
    html = """
    <html><head>
    <meta property="og:title" content="Test User - Engineer" />
    <meta property="og:description" content="1,234 followers · 89 following · Open source" />
    <meta property="og:image" content="https://cdn.example.org/avatars/testuser42/profile.jpg" />
    </head><body>
    <script type="application/json">{"bio":"Building tools","email":"testuser42@example.org","followers":1234,"following":89,"repos":[{"name":"project-alpha"},{"name":"project-beta"}]}</script>
    Contact: testuser42@mail.example.org
    </body></html>
    """
    payload = _parse_page(html, "https://profiles.example.org/user/testuser42")
    assert payload.get("display_name")
    assert payload.get("bio")
    assert payload.get("avatar_url")
    assert payload.get("email")
    assert "testuser42@example.org" in (payload.get("emails") or [])
    assert payload.get("public_metadata", {}).get("followers") or "1234" in str(payload.get("public_metadata"))
    assert "project-alpha" in (payload.get("projects") or [])
