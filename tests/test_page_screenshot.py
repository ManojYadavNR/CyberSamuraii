"""Screenshot capture and storage tests."""

from services.screenshot_store import cache_key_for_url, preview_url_for, save_screenshot


def test_save_and_preview_url():
    saved = save_screenshot(b"\x89PNG\r\n\x1a\n", url="https://example.com/post/1")
    assert saved["preview_url"].startswith("/api/intel/screenshots/")
    assert preview_url_for(saved["screenshot_id"]) == saved["preview_url"]


def test_cache_key_stable():
    assert cache_key_for_url("https://a.com") == cache_key_for_url("https://a.com")
