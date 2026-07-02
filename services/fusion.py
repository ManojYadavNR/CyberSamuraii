from typing import Any

from schemas.fusion import FusionOutput
from services.fusion_engine import fusion_engine

_SKIP_PLATFORMS = frozenset({"_scan_summary"})


def _norm_url(url: Any) -> str:
    if not url or not isinstance(url, str):
        return ""
    return url.lower().rstrip("/")


def fuse_results(normalized: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Legacy merge helper — maps normalized entries to simplified fused rows.
    Prefer DataFusionEngine.fuse() for full intelligence output.
    """
    seen_urls: set[str] = set()
    seen_keys: set[str] = set()
    merged: list[dict[str, Any]] = []

    for entry in normalized:
        platform = entry.get("platform", "unknown")
        if platform in _SKIP_PLATFORMS:
            continue

        url = entry.get("url")
        metadata = entry.get("metadata", {})
        email = metadata.get("email", "")
        hostname = metadata.get("hostname", "")
        if email and platform:
            dedupe_key = f"{platform}:{email.lower()}"
        elif hostname:
            dedupe_key = f"host:{hostname.lower()}"
        elif email:
            dedupe_key = email.lower()
        else:
            dedupe_key = ""

        if dedupe_key:
            if dedupe_key in seen_keys:
                for existing in merged:
                    existing_key = ""
                    em = existing.get("metadata", {}).get("email", "")
                    hn = existing.get("metadata", {}).get("hostname", "")
                    ep = existing.get("platform", "")
                    if em and ep:
                        existing_key = f"{ep}:{em.lower()}"
                    elif hn:
                        existing_key = f"host:{hn.lower()}"
                    elif em:
                        existing_key = em.lower()
                    if existing_key == dedupe_key:
                        sources = existing.setdefault("sources", [existing.get("source_tool")])
                        new_source = entry.get("source_tool")
                        if new_source and new_source not in sources:
                            sources.append(new_source)
                        existing["source_count"] = len(sources)
                        break
                continue
            seen_keys.add(dedupe_key)

        url_key = _norm_url(url)
        if url_key:
            if url_key in seen_urls:
                for existing in merged:
                    if _norm_url(existing.get("url")) == url_key:
                        sources = existing.setdefault("sources", [existing.get("source_tool")])
                        new_source = entry.get("source_tool")
                        if new_source and new_source not in sources:
                            sources.append(new_source)
                        existing["source_count"] = len(sources)
                        break
                continue
            seen_urls.add(url_key)
        elif dedupe_key:
            pass
        elif platform in seen_keys and not metadata:
            continue
        else:
            seen_keys.add(platform)

        fused_entry = {
            "platform": platform,
            "url": url,
            "source_tool": entry.get("source_tool"),
            "sources": [entry.get("source_tool")],
            "source_count": 1,
            "metadata": entry.get("metadata", {}),
        }
        merged.append(fused_entry)

    merged.sort(key=lambda x: (-x.get("source_count", 1), x.get("platform", "")))
    return merged


def build_fusion_output(
    tool_results: list,
    feature: str,
    query: str,
    **kwargs: Any,
) -> FusionOutput:
    """Run the data fusion engine on orchestrator tool outputs."""
    return fusion_engine.fuse(tool_results, feature, query, **kwargs)
