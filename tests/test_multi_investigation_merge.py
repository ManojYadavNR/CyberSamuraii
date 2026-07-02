"""Multi-input merge — attribution seed and email branch preservation."""

import pytest

from schemas.common import FeatureResult, ToolResult
from services.multi_input import attribution_seed_from_raw, parse_investigation_input
from services.multi_investigation import merge_feature_results


def test_attribution_seed_uses_username_not_pipe_string():
    raw = "ManojYadavNR | manojmanu938055@gmail.com"
    parsed = parse_investigation_input(raw)
    assert parsed.is_multi
    assert attribution_seed_from_raw(raw) == "ManojYadavNR"


@pytest.mark.asyncio
async def test_merge_preserves_email_confirmed_findings():
    email_finding = {
        "type": "account_registration",
        "platform": "twitter.com",
        "email": "alice@example.com",
        "source_tool": "holehe",
        "registered": True,
    }
    username_result = FeatureResult(
        feature="username_search",
        query="alice",
        tool_results=[
            ToolResult(tool="sherlock", success=True, data=[]),
        ],
    )
    email_result = FeatureResult(
        feature="email_intel",
        query="alice@example.com",
        tool_results=[
            ToolResult(
                tool="holehe",
                success=True,
                data=[{"platform": "twitter.com", "email": "alice@example.com", "registered": True}],
            ),
        ],
        confirmed_findings=[email_finding],
    )
    parsed = parse_investigation_input("alice | alice@example.com")
    merged = await merge_feature_results(
        [username_result, email_result],
        seed_query=parsed.raw,
        parsed=parsed,
    )
    values = {e.value for e in merged.fusion.deduplicated_entities}
    assert any("twitter.com" in v and "alice@example.com" in v for v in values)
    assert merged.identity_profile is not None
    emails = [e.value for e in merged.identity_profile.emails]
    assert "alice@example.com" in emails


@pytest.mark.asyncio
async def test_merge_empty_email_lists_do_not_break_feature_result():
    """Empty public_profile_data must stay [] — not None (Pydantic list validation)."""
    username_result = FeatureResult(
        feature="username_search",
        query="alice",
        tool_results=[ToolResult(tool="sherlock", success=True, data=[])],
    )
    email_result = FeatureResult(
        feature="email_intel",
        query="alice@example.com",
        tool_results=[ToolResult(tool="holehe", success=True, data=[])],
    )
    parsed = parse_investigation_input("alice | alice@example.com")
    merged = await merge_feature_results(
        [username_result, email_result],
        seed_query=parsed.raw,
        parsed=parsed,
    )
    assert merged.public_profile_data == []
    assert merged.confirmed_findings == []
    assert merged.investigation_leads == []
