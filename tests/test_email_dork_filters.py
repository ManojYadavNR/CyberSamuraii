"""Tests for email-targeted Google dork attribution filters."""

import unittest

from services.google_dorking.filters import email_dork_hit_displayable


class TestEmailDorkFilters(unittest.TestCase):
    def test_rejects_generic_gmail_login(self):
        assert not email_dork_hit_displayable(
            url="https://accounts.google.com/v3/signin/identifier?service=mail",
            title="Gmail",
            snippet="Sign in to your Google Account",
            seed_query="mahinayk483@gmail.com",
        )

    def test_rejects_x_homepage_noise(self):
        assert not email_dork_hit_displayable(
            url="https://x.com/",
            title="X - Official Site",
            snippet="From breaking news and entertainment to sports",
            seed_query="mahinayk483@gmail.com",
        )

    def test_accepts_profile_url_with_local_handle(self):
        assert email_dork_hit_displayable(
            url="https://www.figma.com/@mahinayk483",
            title="mahinayk483 on Figma",
            snippet="Designer profile",
            seed_query="mahinayk483@gmail.com",
        )

    def test_accepts_full_email_in_snippet(self):
        assert email_dork_hit_displayable(
            url="https://example.com/team",
            title="Team roster",
            snippet="Contact mahinayk483@gmail.com for details",
            seed_query="mahinayk483@gmail.com",
        )


if __name__ == "__main__":
    unittest.main()
