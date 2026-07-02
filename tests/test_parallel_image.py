"""Tests for parallel image tool orchestration (additive to legacy image_intel)."""

from orchestrator.config import ADAPTER_MAP, get_feature_tools
from orchestrator.parallel_config import IMAGE_PARALLEL_TOOLS, IMAGE_TOOL_GROUPS


def test_image_intel_keeps_legacy_adapter_and_adds_parallel_tools():
    tools = get_feature_tools("image_intel", profile="deep")
    assert "image_intel" in tools
    for group_tools in IMAGE_TOOL_GROUPS.values():
        for tool in group_tools:
            if tool in ADAPTER_MAP:
                assert tool in tools or tool in IMAGE_PARALLEL_TOOLS


def test_all_image_adapters_registered():
    for tool in IMAGE_PARALLEL_TOOLS:
        assert tool in ADAPTER_MAP, f"missing adapter for {tool}"


def test_username_search_registry_driven():
    tools = get_feature_tools("username_search")
    assert "sherlock" in tools
    assert "maigret" in tools
    assert "google_dorking" in tools
