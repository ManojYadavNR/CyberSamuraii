"""GHunt session gating."""

from services.ghunt_session import ghunt_creds_path, ghunt_session_available
from services.osint_registry.router import tools_for_feature


def test_ghunt_excluded_without_login():
    if ghunt_session_available():
        return
    tools = tools_for_feature("email_intel", target="test@gmail.com")
    assert "ghunt" not in tools


def test_ghunt_creds_path_under_malfrats():
    assert ghunt_creds_path().name == "creds.m"
    assert ".malfrats" in str(ghunt_creds_path())
