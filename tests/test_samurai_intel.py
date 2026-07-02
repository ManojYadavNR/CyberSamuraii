from schemas.common import ToolResult
from services.evidence.samurai_intel import build_samurai_social_intel


def test_build_samurai_social_intel_from_tool_results():
    payload = {
        "platform": "samurai_intel",
        "check_type": "samurai_intel",
        "username": "testuser",
        "instagram": {"profile": {"username": "testuser"}, "recent_posts": [{"url": "https://instagram.com/p/abc"}]},
        "facebook": None,
    }
    results = [
        ToolResult(tool="samurai", success=True, data=[payload]),
    ]
    intel = build_samurai_social_intel(results)
    assert intel is not None
    assert intel["has_instagram"] is True
    assert intel["instagram_post_count"] == 1


def test_build_samurai_social_intel_preserves_instagram_api_response():
    payload = {
        "platform": "samurai_intel",
        "check_type": "samurai_intel",
        "username": "manojyadav_.27",
        "instagram": {
            "profile": {"username": "manojyadav_.27"},
            "api_response": {
                "data": {"user": {"username": "manojyadav_.27", "is_private": True}},
                "status": "ok",
            },
        },
    }
    results = [ToolResult(tool="samurai", success=True, data=[payload])]
    intel = build_samurai_social_intel(results)
    assert intel is not None
    ig = intel["instagram"]
    assert ig["api_response"]["status"] == "ok"
    assert ig["api_response"]["data"]["user"]["username"] == "manojyadav_.27"
