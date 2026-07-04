"""Run individual reverse image sources for parallel adapter streaming."""

from __future__ import annotations

from adapters.image_common import resolve_image_source
from schemas.common import ToolResult
from services.image_intelligence.adapter_bridge import findings_to_tool_result

# Adapter name → registry source names (prefer fast DDGS over browser upload).
_ADAPTER_SOURCES: dict[str, list[str]] = {
    "google_lens": ["google_lens_ddgs", "google_lens"],
    "bing_visual": ["bing_visual_ddgs"],
    "yandex_images": ["yandex_images"],
    "tineye": ["tineye"],
}


async def _run_reverse_source(tool: str, query: str, platform: str) -> ToolResult:
    path, url, err = await resolve_image_source(query)
    if err or not path:
        return ToolResult(tool=tool, success=False, error=err or "no image source")
    try:
        from services.reverse_image.engine import ReverseImageDiscoveryEngine

        source_names = _ADAPTER_SOURCES.get(tool, [tool])
        # Try fast sources first; stop once we have matches.
        all_matches = []
        sources_tried: list[str] = []
        for name in source_names:
            engine = ReverseImageDiscoveryEngine(source_names=[name])
            discovery = await engine.discover(query, seed_query=query)
            sources_tried.append(name)
            all_matches.extend(discovery.matches)
            if all_matches:
                break

        from schemas.image_intelligence import ImageFinding

        findings = [
            ImageFinding(
                category="reverse_image",
                field="reverse_match",
                value=m.match_url,
                source_tool=tool,
                extraction_strategy=f"{tool}_reverse_search",
                confidence=m.confidence,
                evidence={
                    "match_type": m.match_type,
                    "page_url": m.page_url,
                    "title": m.title,
                    "snippet": m.snippet,
                    "platform": m.platform,
                    "profile_urls": m.profile_urls,
                    "organizations": m.organizations,
                    "linked_profiles": m.profile_urls,
                    "similarity_matches": [m.match_url],
                    "evidence_path": m.evidence_path,
                    "sources_tried": sources_tried,
                    "file": path,
                    "url": url,
                },
            )
            for m in all_matches
        ]
        return findings_to_tool_result(tool, findings, platform=platform, group="reverse_image_search")
    except Exception as exc:
        return ToolResult(tool=tool, success=False, error=str(exc))


async def run_google_lens(query: str) -> ToolResult:
    return await _run_reverse_source("google_lens", query, "google_reverse_image")


async def run_bing_visual(query: str) -> ToolResult:
    return await _run_reverse_source("bing_visual", query, "bing_visual_search")


async def run_yandex_images(query: str) -> ToolResult:
    return await _run_reverse_source("yandex_images", query, "yandex_images")


async def run_tineye(query: str) -> ToolResult:
    return await _run_reverse_source("tineye", query, "tineye")
