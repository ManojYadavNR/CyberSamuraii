"""Handle quality tests for correlation."""

from services.correlation.handle_quality import (
    is_correlatable_handle,
    is_plausible_handle_for_correlation,
    normalize_profile_handle,
)


def test_normalize_skips_generic_path_segments():
    assert normalize_profile_handle(
        "https://imgur.com/user/ManojYadavNR",
        "imgur.com",
        {},
    ) == "manojyadavnr"
    assert normalize_profile_handle(
        "https://linkedin.com/in/manoj-yadav-nr",
        "linkedin.com",
        {},
    ) == "manoj-yadav-nr"


def test_rejects_junk_handles():
    assert not is_plausible_handle_for_correlation("user")
    assert not is_plausible_handle_for_correlation("p")
    assert is_plausible_handle_for_correlation("manojyadavnr")


def test_normalize_prefers_url_over_generic_meta_username():
    assert normalize_profile_handle(
        "https://imgur.com/user/ManojYadavNR",
        "imgur.com",
        {"username": "user"},
    ) == "manojyadavnr"
    assert normalize_profile_handle(
        "https://reddit.com/user/ManojYadavNR",
        "reddit.com",
        {"username": "user"},
    ) == "manojyadavnr"


    assert is_correlatable_handle("manojyadavnr", "ManojYadavNR", "https://github.com/ManojYadavNR")
    assert not is_correlatable_handle("unrelated_person", "ManojYadavNR", "https://twitter.com/unrelated_person")
