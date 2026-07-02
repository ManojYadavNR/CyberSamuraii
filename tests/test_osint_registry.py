"""Tests for OSINT Framework registry layer."""

from services.osint_registry.registry import registry
from services.osint_registry.router import select_tools, tools_for_feature


def test_registry_loads_catalog():
    count = registry.reload()
    assert count >= 20
    sherlock = registry.get("sherlock")
    assert sherlock is not None
    assert "username" in sherlock.supported_inputs


def test_username_routing_includes_social_analyzer():
    tools = tools_for_feature("username_search")
    assert "social_analyzer" in tools
    assert "sherlock" in tools
    assert "gitfive" not in tools


def test_email_routing_includes_ghunt_gravatar():
    from services.ghunt_session import ghunt_session_available

    tools = tools_for_feature("email_intel", target="alice@example.com")
    assert "holehe" in tools
    assert "gravatar" in tools
    if ghunt_session_available():
        assert "ghunt" in tools
    else:
        assert "ghunt" not in tools


def test_image_routing_fast_profile():
    tools = tools_for_feature("image_intel", profile="fast")
    assert "pillow" in tools or "exiftool" in tools
    assert "insightface" in tools or "opencv_face" in tools


def test_catalog_only_tools_excluded():
    tools = tools_for_feature("username_search")
    assert "profil3r" not in tools


def test_domain_routing_includes_cross_cutting_tools():
    tools = tools_for_feature("domain_intel", target="example.com")
    assert "theharvester" in tools
    assert "recon_ng" in tools
    assert "subfinder" in tools


def test_phone_routing_includes_social_intel():
    tools = tools_for_feature("infra_intel", target="+919164873661")
    assert "phone_social_intel" in tools
    assert "phoneinfoga" in tools
    assert "google_dorking" in tools
    assert "shodan" not in tools
