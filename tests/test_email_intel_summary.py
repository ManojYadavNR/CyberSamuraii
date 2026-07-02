"""Tests for email investigation scan summaries."""

from schemas.common import ToolResult
from services.email_intel import build_email_investigation


def test_theharvester_skip_note_in_scan_summary():
    results = [
        ToolResult(
            tool="theharvester",
            success=True,
            data=[],
            raw_output="Skipped theHarvester for consumer mail domain 'gmail.com'.",
        ),
    ]
    confirmed, _public, _leads, summary = build_email_investigation(
        results, "user@gmail.com", []
    )
    assert confirmed == []
    assert summary["theharvester"]["status"] == "skipped"
    assert "gmail.com" in summary["theharvester"]["note"]


def test_google_dorking_hits_in_scan_summary():
    results = [
        ToolResult(
            tool="google_dorking",
            success=True,
            data=[
                {
                    "platform": "github.com",
                    "url": "https://github.com/foo",
                    "title": "Foo repo",
                    "check_type": "google_dork",
                    "dork_category": "email_gmail_github",
                },
                {"platform": "_scan_summary", "sites_checked": 20, "sites_found": 1},
            ],
        ),
    ]
    confirmed, _public, _leads, summary = build_email_investigation(
        results, "user@gmail.com", []
    )
    assert summary["google_dorking"]["hits"] == 1
    assert any(c["type"] == "email_web_mention" for c in confirmed)
