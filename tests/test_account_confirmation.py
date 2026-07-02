"""Tests for cross-platform account confirmation logic."""

from services.account_confirmation import account_confirmed


def test_maigret_claimed_confirmed_on_any_platform():
    meta = {
        "check_type": "live_scan",
        "status": "maigret_claimed",
        "url": "https://shop.example.com/manojyadavnr",
        "platform": "shop.example.com",
        "username": "manojyadavnr",
    }
    assert account_confirmed(meta, {"maigret"})


def test_sherlock_single_hit_not_confirmed_without_content():
    meta = {
        "check_type": "username_probe",
        "live_profile_verified": None,
        "content_seed_verified": False,
        "url": "https://imgur.com/user/alice",
        "platform": "imgur.com",
    }
    assert not account_confirmed(meta, {"sherlock"})


def test_platform_probe_alone_never_confirms():
    meta = {
        "check_type": "live_scan",
        "probe_source": "platform_probe",
        "live_profile_verified": True,
        "content_seed_verified": True,
        "url": "https://onlyfans.com/alice",
        "platform": "onlyfans.com",
    }
    assert not account_confirmed(meta, {"platform_probe"})


def test_maigret_plus_sherlock_confirms():
    meta = {
        "check_type": "live_scan",
        "status": "maigret_claimed",
        "content_seed_verified": True,
        "url": "https://github.com/alice",
        "platform": "github.com",
    }
    assert account_confirmed(meta, {"maigret", "sherlock"})


def test_username_probe_never_confirmed_even_with_http_proof():
    meta = {
        "check_type": "username_probe",
        "live_profile_verified": True,
        "content_seed_verified": True,
        "url": "https://github.com/alice",
        "platform": "github.com",
    }
    assert not account_confirmed(meta, {"sherlock"})
    assert not account_confirmed(meta, {"sherlock", "social_analyzer"})


def test_holehe_registration_confirmed_with_matching_seed_email():
    meta = {
        "type": "account_registration",
        "platform": "github.com",
        "email": "manojmanu938055@gmail.com",
        "registered": True,
        "status": "registered",
        "check_type": "live_scan",
    }
    assert account_confirmed(meta, {"holehe"}, seed_email="manojmanu938055@gmail.com")
    assert not account_confirmed(meta, {"holehe"}, seed_email="other@example.com")
    assert not account_confirmed(meta, {"holehe"})


def test_social_analyzer_with_http_proof_confirms_without_maigret():
    meta = {
        "check_type": "live_scan",
        "status": "social_analyzer_detected",
        "content_seed_verified": True,
        "live_profile_verified": True,
        "url": "https://dailykos.com/alice",
        "platform": "dailykos.com",
        "username": "alice",
    }
    assert account_confirmed(meta, {"social_analyzer"})
    assert not account_confirmed(meta, {"sherlock"})
