"""Phone intelligence parsing and result shaping."""

from services.phone_intelligence.number_parser import parse_phone_number
from services.phone_intelligence.results import rows_from_social_intel


def test_parse_indian_mobile():
    info = parse_phone_number("919164873661", default_region="IN")
    assert info is not None
    assert info["countryCode"] == "91"
    assert info["e164"].startswith("+")


def test_rows_from_social_intel_confirmed_match():
    number_info = {"e164": "+919164873661", "international": "+91 91648 73661", "countryCode": "91"}
    social = {
        "summary": {"registered_accounts_found": 1, "confirmed_links": 1, "possible_links": 0},
        "confirmed_matches": [{
            "platform": "instagram",
            "url": "https://www.instagram.com/example/",
            "confidence": "high",
            "evidence": "test",
        }],
        "possible_matches": [],
        "profile_links": [],
        "registered_accounts": {"platforms": []},
    }
    rows = rows_from_social_intel(number_info, social)
    assert any(r.get("platform") == "instagram" for r in rows)
    assert any(r.get("platform") == "_scan_summary" for r in rows)


def test_rows_from_full_scan_shape():
    from services.phone_intelligence.results import rows_from_full_scan

    scan = {
        "success": True,
        "phoneinfoga_api": False,
        "number": {"e164": "+919164873661", "countryCode": "91"},
        "local": {"carrier": "Airtel"},
        "numverify": {"success": False, "error": "not configured"},
        "social_accounts": {
            "summary": {"confirmed_links": 0, "possible_links": 0, "registered_accounts_found": 0},
            "confirmed_matches": [],
            "possible_matches": [],
            "profile_links": [],
            "registered_accounts": {"platforms": []},
        },
        "web_footprint": {"total_hits": 0, "categories": {}},
        "googlecse": None,
    }
    rows = rows_from_full_scan(scan)
    assert any(r.get("platform") == "_scan_summary" for r in rows)
