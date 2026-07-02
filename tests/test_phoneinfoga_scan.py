"""PhoneInfoga structured scan tests."""

from services.phone_intelligence.phoneinfoga_scan import rows_from_phoneinfoga_scan


def test_rows_from_phoneinfoga_scan_numverify_and_local():
    scan = {
        "success": True,
        "phoneinfoga_api": True,
        "number": {"e164": "+919164873661", "countryCode": "91", "international": "+91 91648 73661"},
        "local": {"carrier": "Airtel", "location": "Karnataka", "country": "IN"},
        "numverify": {
            "success": True,
            "data": {
                "valid": True,
                "international_format": "+919164873661",
                "carrier": "Airtel",
                "location": "Karnataka",
                "line_type": "mobile",
            },
        },
        "web_footprint": {"total_hits": 2, "categories": {}},
        "googlecse": None,
        "social_accounts": None,
    }
    rows = rows_from_phoneinfoga_scan(scan)
    assert any(r.get("platform") == "_scan_summary" for r in rows)
    assert any(r.get("platform") == "numverify" for r in rows)
    assert any(r.get("carrier") == "Airtel" for r in rows)
    summary = next(r for r in rows if r.get("platform") == "_scan_summary")
    assert summary.get("valid") is True
    assert summary.get("numverify_ok") is True


def test_summary_uses_numverify_when_local_carrier_empty():
    scan = {
        "success": True,
        "phoneinfoga_api": True,
        "number": {"e164": "+919164873661", "countryCode": 91, "carrier": ""},
        "local": {"carrier": "", "country": "IN"},
        "numverify": {
            "success": True,
            "data": {
                "valid": True,
                "carrier": "Vodafone Idea Ltd",
                "location": "Karnataka",
                "line_type": "mobile",
                "country_name": "India (Republic of)",
            },
        },
        "web_footprint": None,
        "googlecse": None,
        "social_accounts": None,
    }
    summary = next(r for r in rows_from_phoneinfoga_scan(scan) if r.get("platform") == "_scan_summary")
    assert summary.get("carrier") == "Vodafone Idea Ltd"
    assert summary.get("location") == "Karnataka"
    assert summary.get("line_type") == "mobile"


def test_phoneinfoga_rows_include_platform_registrations():
    scan = {
        "success": True,
        "phoneinfoga_api": True,
        "number": {"e164": "+919164873661", "countryCode": 91, "international": "919164873661"},
        "local": {"country": "IN"},
        "numverify": {"success": False},
        "web_footprint": None,
        "googlecse": None,
        "social_accounts": {
            "summary": {"registered_accounts_found": 1, "confirmed_links": 1},
            "registered_accounts": {
                "linked_accounts": [{
                    "platform": "instagram",
                    "profile_hint": "https://www.instagram.com/",
                    "confidence": "high",
                }],
                "platforms": [{
                    "platform": "instagram",
                    "account_linked": True,
                    "method": "other",
                }],
            },
            "platforms": {
                "whatsapp": {
                    "platform": "whatsapp",
                    "status": "likely_registered",
                    "profile_url": "https://wa.me/919164873661",
                },
            },
            "confirmed_matches": [],
            "possible_matches": [],
            "profile_links": [],
        },
    }
    rows = rows_from_phoneinfoga_scan(scan)
    regs = [r for r in rows if r.get("check_type") == "platform_registration"]
    assert any(r.get("platform") == "instagram" for r in regs)
    assert any(r.get("platform") == "whatsapp" for r in regs)
