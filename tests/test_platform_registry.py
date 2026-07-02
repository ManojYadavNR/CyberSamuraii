"""Dynamic platform registry."""

from services.platform_registry import (
    build_probe_templates,
    normalize_platform_host,
    platform_label_from_host,
    priority_social_domains,
    profile_slug_from_url,
)


def test_normalize_platform_host():
    assert normalize_platform_host("https://www.instagram.com/user/") == "instagram.com"
    assert normalize_platform_host("in.linkedin.com") == "linkedin.com"


def test_profile_slug_from_url():
    assert profile_slug_from_url("https://www.facebook.com/examplecollege/photos/1") == "examplecollege"
    assert profile_slug_from_url("https://www.linkedin.com/in/janedoe") == "janedoe"


def test_build_probe_templates_not_empty():
    templates = build_probe_templates(max_sites=8)
    assert templates
    assert "{q}" in templates[0]["url"]


def test_priority_social_domains():
    domains = priority_social_domains(5)
    assert len(domains) <= 5
    assert domains


def test_platform_label_from_host():
    assert platform_label_from_host("github.com") == "Github"
    assert platform_label_from_host("x.com") == "X"
