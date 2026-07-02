"""Tests for dork document parsing."""

import unittest

from services.evidence.document_parser import parse_dork_document


class TestDocumentParser(unittest.TestCase):
    def test_media_video_extracted(self):
        fields = parse_dork_document(
            {
                "title": "TestUser - Channel",
                "url": "https://videos.example.org/@TestUser42",
                "snippet": "11 subscribers · 12 videos",
                "dork_category": "media_video",
                "check_type": "google_dork",
            },
            entity_value="videos.example.org/@testuser42",
            seed_query="TestUser42",
        )
        assert any(f[0] == "media_video" for f in fields)

    def test_hackathon_event_extracted(self):
        fields = parse_dork_document(
            {
                "title": "Innovation Ignitors Hackathon Winner",
                "url": "https://code.example.org/TestUser42/innovation-ignitors",
                "snippet": "hackathon winner project",
                "dork_category": "achievements",
                "check_type": "google_dork",
            },
            entity_value="code.example.org/testuser42/innovation-ignitors",
            seed_query="TestUser42",
        )
        assert any(f[0] == "event" for f in fields)
        assert any(f[0] == "achievement" for f in fields)


    def test_conference_event_extracted(self):
        fields = parse_dork_document(
            {
                "title": "TestUser42 spoke at Global Tech Summit 2025",
                "url": "https://events.example.org/summit-2025/speakers",
                "snippet": "Keynote speaker TestUser42 presented on distributed systems",
                "dork_category": "events_general",
                "check_type": "google_dork",
            },
            entity_value="events.example.org/summit-2025",
            seed_query="TestUser42",
        )
        assert any(f[0] == "event" for f in fields)

    def test_news_article_blog_extracted(self):
        news = parse_dork_document(
            {
                "title": "TestUser42 wins innovation award",
                "url": "https://news.example.org/tech/testuser42-award",
                "snippet": "Local developer TestUser42 recognized for open source work",
                "dork_category": "news_mentions",
                "check_type": "google_dork",
            },
            entity_value="news.example.org/tech/testuser42",
            seed_query="TestUser42",
        )
        assert any(f[0] == "news" for f in news)

        blog = parse_dork_document(
            {
                "title": "Building scalable APIs — TestUser42",
                "url": "https://blogs.example.org/posts/testuser42-apis",
                "snippet": "A technical blog by TestUser42",
                "dork_category": "blog_search",
                "check_type": "google_dork",
            },
            entity_value="blogs.example.org/posts/testuser42",
            seed_query="TestUser42",
        )
        assert any(f[0] == "blog" for f in blog)

        article = parse_dork_document(
            {
                "title": "Profile: TestUser42, community engineer",
                "url": "https://magazine.example.org/article/testuser42-profile",
                "snippet": "Feature story on TestUser42",
                "dork_category": "article_search",
                "check_type": "google_dork",
            },
            entity_value="magazine.example.org/article/testuser42",
            seed_query="TestUser42",
        )
        assert any(f[0] == "article" for f in article)


if __name__ == "__main__":
    unittest.main()
