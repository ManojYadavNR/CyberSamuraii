"""Email profile URL resolution for registered platforms."""

from services.email_profile_resolver import (
    build_profile_url,
    enrich_confirmed_findings,
    index_gravatar_accounts,
    resolve_registration_profile,
    username_candidates_from_email,
)


def test_build_profile_url_twitter():
    assert build_profile_url("twitter.com", "manjesh19") == "https://twitter.com/manjesh19"


def test_gravatar_handle_from_about():
    profiles = [{
        "about": "Manjesh shetty / https://gravatar.com/manjesh19",
        "accounts": [],
    }]
    index = index_gravatar_accounts(profiles)
    assert index.get("gravatar.com") == "manjesh19"


def test_enrich_registration_with_gravatar_username():
    email = "manjeshshetty1@gmail.com"
    profiles = [{"about": "https://gravatar.com/manjesh19", "accounts": []}]
    confirmed = [{
        "type": "account_registration",
        "platform": "twitter.com",
        "email": email,
        "source_tool": "holehe",
    }]
    out = enrich_confirmed_findings(confirmed, email=email, public_profiles=profiles)
    assert out[0].get("username") == "manjesh19"
    assert "twitter.com/manjesh19" in str(out[0].get("url"))


def test_email_local_fallback_username():
    username, url = resolve_registration_profile(
        "spotify.com",
        email="manjeshshetty1@gmail.com",
        gravatar_index={},
    )
    assert username in username_candidates_from_email("manjeshshetty1@gmail.com")
    assert url and "spotify.com" in url
