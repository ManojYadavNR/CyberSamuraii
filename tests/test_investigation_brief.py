"""Tests for Investigation Brief rule extraction and instant answers."""

from __future__ import annotations

from services.investigation_brief import (
    empty_brief,
    extract_tool_facts,
    finalize_brief_from_result,
    merge_brief_tool,
    search_brief_answer,
)


def test_extract_samurai_and_dork_facts() -> None:
    samurai = {
        "tool": "samurai",
        "success": True,
        "data": [{
            "platform": "instagram",
            "profile": {"biography": "Developer at CIT", "username": "manojyadavnr"},
            "recent_posts": [{"caption": "Hello world", "url": "https://instagram.com/p/abc"}],
        }],
    }
    facts = extract_tool_facts(samurai)
    assert facts["facts"]["bios"]
    assert facts["facts"]["instagram_posts"]

    dork = {
        "tool": "google_dorking",
        "success": True,
        "data": [{"title": "Hackathon winner Manoj", "snippet": "Smart India Hackathon", "url": "https://x.com"}],
    }
    df = extract_tool_facts(dork)
    assert df["facts"]["hackathons"]


def test_brief_search_finds_accounts() -> None:
    brief = empty_brief(investigation_id="i1", query="manojyadavnr")
    merge_brief_tool(brief, {
        "tool": "sherlock",
        "success": True,
        "data": [{"platform": "GitHub", "handle": "manojyadavnr", "url": "https://github.com/manojyadavnr"}],
    })
    brief["status"] = "ready"
    out = search_brief_answer("linked github accounts", brief)
    assert "manojyadavnr" in out.lower()
    assert "github" in out.lower()


def test_brief_indexes_accounts() -> None:
    brief = empty_brief(investigation_id="i1", query="manojyadavnr")
    merge_brief_tool(brief, {
        "tool": "sherlock",
        "success": True,
        "data": [{"platform": "GitHub", "handle": "manojyadavnr", "url": "https://github.com/manojyadavnr"}],
    })
    brief["status"] = "ready"
    accounts = brief["facts"]["accounts"]
    assert accounts
    assert "manojyadavnr" in str(accounts[0]).lower()


def test_finalize_adds_evidence() -> None:
    brief = empty_brief(query="test")
    result = {
        "query": "test",
        "evidence_extraction": {
            "google_search_intel": {
                "hits": [{"title": "Cambridge Institute college", "snippet": "college campus", "url": "https://cit.edu"}],
            },
        },
        "fusion": {"fusion_score": 0.8},
    }
    finalize_brief_from_result(brief, result)
    assert brief["status"] == "ready"
    assert brief["facts"]["colleges"]
