"""Tests for legacy fuse_results merge helper."""

from services.fusion import fuse_results


def test_fuse_results_skips_scan_summary():
    normalized = [
        {"platform": "_scan_summary", "source_tool": "sherlock", "url": None, "metadata": {"sites_checked": 482}},
        {"platform": "GitHub", "source_tool": "sherlock", "url": "https://github.com/user", "metadata": {}},
    ]
    merged = fuse_results(normalized)
    assert len(merged) == 1
    assert merged[0]["platform"] == "GitHub"


def test_fuse_results_handles_null_url():
    normalized = [
        {
            "platform": "google_search",
            "source_tool": "google_dorking",
            "url": None,
            "metadata": {"email": "a@b.com"},
        },
        {
            "platform": "google_search",
            "source_tool": "holehe",
            "url": None,
            "metadata": {"email": "a@b.com"},
        },
    ]
    merged = fuse_results(normalized)
    assert len(merged) == 1
    assert merged[0]["source_count"] == 2


def test_fuse_results_merges_same_url():
    normalized = [
        {"platform": "GitHub", "source_tool": "sherlock", "url": "https://github.com/user/", "metadata": {}},
        {"platform": "GitHub", "source_tool": "maigret", "url": "https://github.com/user", "metadata": {}},
    ]
    merged = fuse_results(normalized)
    assert len(merged) == 1
    assert set(merged[0]["sources"]) == {"sherlock", "maigret"}
