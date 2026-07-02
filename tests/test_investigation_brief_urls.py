"""Tests for investigation brief URL sanitization."""

from services.investigation_brief import (
    empty_brief,
    finalize_brief_from_result,
    format_account_line,
    is_template_text,
    merge_brief_tool,
    resolve_investigation_url,
    search_brief_with_match,
)


def test_template_url_detected():
    assert is_template_text("https://github.com/{username}")
    assert not is_template_text("https://github.com/alice")


def test_resolve_url_with_query():
    url = resolve_investigation_url("https://github.com/{username}", "manojyadavnr")
    assert url == "https://github.com/manojyadavnr"


def test_format_account_line_real_url():
    line = format_account_line(
        {"tool": "sherlock", "platform": "GitHub", "handle": "alice", "url": "https://github.com/alice"},
        "alice",
    )
    assert line is not None
    assert "https://github.com/alice" in line
    assert "{username}" not in line


def test_search_brief_instagram_question():
    brief = empty_brief(query="manojyadavnr")
    merge_brief_tool(
        brief,
        {
            "tool": "samurai",
            "success": True,
            "data": [
                {
                    "platform": "instagram",
                    "handle": "manojyadavnr",
                    "url": "https://instagram.com/manojyadavnr",
                }
            ],
        },
    )
    finalize_brief_from_result(brief, {"fusion": {}, "correlation": {}})
    answer, matched = search_brief_with_match("iska instagram hai", brief)
    assert matched
    assert "instagram" in answer.lower()
    assert "{username}" not in answer
