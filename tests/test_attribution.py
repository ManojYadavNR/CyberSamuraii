"""Tests for username-attributed contact discovery."""

import unittest

from services.discovery.attribution import (
    email_attributed_to_username,
    email_linked_to_seed,
    url_references_seed,
)


class TestAttribution(unittest.TestCase):
    def test_url_references_seed_github_profile(self):
        assert url_references_seed("https://github.com/ManojYadavNR/agilPro", "ManojYadavNR")

    def test_url_does_not_reference_different_github_user(self):
        assert not url_references_seed("https://github.com/manojy5951", "ManojYadavNR")

    def test_email_from_different_user_not_attributed(self):
        assert not email_attributed_to_username(
            "manojy5951@gmail.com",
            "ManojYadavNR",
            source_url="https://github.com/manojy5951",
            title="manojy5951 (manoj yadav)",
            snippet="Email: manojy5951@gmail.com",
        )

    def test_email_on_seed_profile_attributed(self):
        assert email_attributed_to_username(
            "manojyadavnr@gmail.com",
            "ManojYadavNR",
            source_url="https://github.com/manojyadavnr",
            title="ManojYadavNR on GitHub",
            snippet="Contact manojyadavnr@gmail.com",
        )

    def test_email_linked_requires_attribution(self):
        assert not email_linked_to_seed("manojy5951@gmail.com", "ManojYadavNR")
        assert email_linked_to_seed(
            "manojyadavnr@gmail.com",
            "ManojYadavNR",
            profile_url="https://github.com/manojyadavnr",
            handle="manojyadavnr",
        )

    def test_account_handle_matches_seed_on_youtube(self):
        from services.discovery.attribution import account_handle_matches_seed

        assert account_handle_matches_seed("ManojYadavNR", "ManojYadavNR", "https://www.youtube.com/@ManojYadavNR")


if __name__ == "__main__":
    unittest.main()
