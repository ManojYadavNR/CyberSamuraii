"""Tests for reverse image quality filters."""

from __future__ import annotations

from services.reverse_image.extractors import extract_organizations, extract_profile_urls
from services.reverse_image.filters import (
    confidence_from_hash,
    is_junk_url,
    is_real_profile_url,
)


def test_junk_search_landing_pages():
    assert is_junk_url("https://www.bing.com/images/?cc=us")
    assert is_junk_url("https://gravatar.com/")
    assert is_junk_url("https://learn.microsoft.com/en-us/training/modules/personalize-profile/")


def test_real_profile_by_structure():
    assert is_real_profile_url("https://profiles.example.org/user/octocat")
    assert not is_real_profile_url("https://learn.microsoft.com/en/foo")


def test_confidence_requires_hash_proof():
    assert confidence_from_hash(0.95) >= 0.85
    assert confidence_from_hash(0.5) == 0.0


def test_extract_organizations_filters_generic_titles():
    orgs = extract_organizations("Your Free Avatar Profile Visual Search Microsoft Bing")
    assert "Your Free Avatar" not in orgs
    assert "Visual Search" not in orgs


def test_extract_profile_urls_skips_docs():
    profiles = extract_profile_urls(
        "https://learn.microsoft.com/en/training/modules/personalize-profile/",
        title="Personalize your profile - Docs",
    )
    assert profiles == []
