"""Accuracy guards for username probe tools — blocks known false positives."""

from adapters.external_osint import NexfilAdapter, _username_probe_url
from services.google_dorking.filters import dork_hit_displayable, is_junk_dork_url
from services.platform_probe import classify_probe_response


def test_nexfil_rejects_tool_author_banner_urls():
    assert not _username_probe_url("https://twitter.com/thewhiteh4t", "ManojYadavNR")
    assert not _username_probe_url("https://twc1rcle.com/", "ManojYadavNR")


def test_nexfil_accepts_real_profile_urls():
    assert _username_probe_url("https://github.com/ManojYadavNR", "ManojYadavNR")
    assert _username_probe_url("https://www.instagram.com/ManojYadavNR/", "ManojYadavNR")


def test_nexfil_parse_skips_banner_stdout():
    adapter = NexfilAdapter()
    stdout = (
        "\x1b[32m[+] Twitter : https://twitter.com/thewhiteh4t\x1b[0m\n"
        "\x1b[32m[+] Community : https://twc1rcle.com/\x1b[0m\n"
    )
    assert adapter._parse_urls(stdout, "ManojYadavNR") == []


def test_justdial_directory_listing_is_junk():
    url = "https://www.justdial.com/Rewari/Manoj-Yadav-Nr-Bsnl-Tower-Dharuhera/9999P1274"
    assert is_junk_dork_url(url)
    assert not dork_hit_displayable(
        url=url,
        title="Manoj Yadav Nr Bsnl Tower Dharuhera",
        snippet="Business listing in Rewari",
        seed_query="ManojYadavNR",
        dork_category="achievements",
    )


def test_hackerrank_error_page_not_available():
    html = "<html><title>HackerRank</title><body>Something went wrong! Please try again.</body></html>"
    ok, reason = classify_probe_response("https://www.hackerrank.com/ManojYadavNR", 200, html)
    assert ok is not True
    assert reason in ("service_error_page", "unavailable_page", "not_found", "error_title")


def test_facebook_login_wall_not_counted_as_probe_hit():
    html = "<html><title>Facebook</title><body>Log into Facebook<br>Create new account</body></html>"
    ok, reason = classify_probe_response("https://facebook.com/ManojYadavNR", 200, html)
    assert ok is not True
