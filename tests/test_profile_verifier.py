"""Tests for live profile URL verification."""

import unittest

from services.discovery.validators import is_junk_profile_url, is_parking_page_html, is_service_error_html
from services.evidence.profile_verifier import is_profile_page_available


class TestProfileVerifier(unittest.TestCase):
    def test_facebook_unavailable_page_rejected(self):
        html = """
        <html><title>Facebook</title>
        <body>This content isn't available at the moment</body></html>
        """
        ok, reason = is_profile_page_available(html, "https://www.facebook.com/manojyadavnr")
        assert not ok
        assert reason in ("unavailable_page", "login_wall", "error_title")

    def test_github_profile_accepted(self):
        html = """
        <html><title>manojyadavnr (Manoj Yadav) · GitHub</title>
        <body><meta property="og:image" content="https://avatars.githubusercontent.com/u/123?v=4" />
        Repositories and followers for this developer profile.</body></html>
        """
        ok, _ = is_profile_page_available(html, "https://github.com/manojyadavnr")
        assert ok

    def test_mastodon_hosting_placeholder_rejected(self):
        url = "https://media.mastodon.cloud/cloud-093img.html"
        assert is_junk_profile_url(url)
        html = """
        <html><title>mastodon.cloud</title>
        <body>We currently do not provide services in your area.
        Service code 093 Service email info@sujitech.com</body></html>
        """
        assert is_service_error_html(html)
        ok, reason = is_profile_page_available(html, url)
        assert not ok
        assert reason in ("junk_profile_url", "service_error_page")

    def test_mastodon_vanity_parking_page_rejected(self):
        url = "https://mastodon.cloud/madendradm"
        assert is_junk_profile_url(url)
        html = """
        <html><head>
        <meta property="og:title" content="093" />
        <meta property="og:type" content="093" />
        <meta property="og:image" content="https://vip2.loli.io/2023/10/03/McOTYLwVylqI6HW.png" />
        <title>093-mastodon.cloud</title></head>
        <body><img src="https://vip2.loli.io/2023/10/03/McOTYLwVylqI6HW.png"></body></html>
        """
        assert is_parking_page_html(html)
        ok, reason = is_profile_page_available(html, url)
        assert not ok
        assert reason in ("junk_profile_url", "parking_page")

    def test_facebook_login_shell_rejected(self):
        html = """
        <html id="facebook"><head><title>Facebook</title></head>
        <body><div id="splash-screen">Loading</div></body></html>
        """
        ok, reason = is_profile_page_available(html, "https://www.facebook.com/someuser")
        assert not ok
        assert reason == "login_wall"


if __name__ == "__main__":
    unittest.main()
