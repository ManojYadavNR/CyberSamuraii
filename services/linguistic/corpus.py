"""Collect analyzable text from investigation artifacts."""

from __future__ import annotations

import re
from typing import Any

from schemas.linguistic import TextArtifact

_TEXT_KEYS = frozenset({
    "bio", "biography", "about", "description", "snippet", "title", "caption",
    "text", "content", "message", "name", "display_name", "headline", "summary",
    "body", "comment", "post_text", "status", "tagline",
})

_SKIP_VALUES = frozenset({"", "none", "null", "n/a", "unknown"})
_URL_ONLY_RE = re.compile(r"^https?://[^\s<>\"']+$", re.I)
_HANDLE_ONLY_RE = re.compile(r"^@?[\w.-]{2,40}$")
_PLATFORM_SLUGS = frozenset({
    "github", "gitlab", "twitter", "instagram", "facebook", "reddit", "youtube",
    "tiktok", "linkedin", "pinterest", "medium", "twitch", "discord", "telegram",
})
_HIGH_VALUE_REF = frozenset({
    "bio", "biography", "about", "description", "caption", "headline", "summary",
    "body", "post_text", "snippet", "recent_posts", "posts",
})


def _clean(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) < 3 or t.lower() in _SKIP_VALUES:
        return ""
    return t[:2000]


def _artifact(tool: str, platform: str | None, ref: str, text: str) -> TextArtifact | None:
    cleaned = _clean(text)
    if not cleaned:
        return None
    return TextArtifact(
        source_tool=tool,
        source_platform=platform,
        source_ref=ref,
        text=cleaned,
        char_count=len(cleaned),
    )


def _walk_dict(
    obj: Any,
    *,
    tool: str,
    platform: str | None,
    ref_prefix: str,
    out: list[TextArtifact],
    depth: int = 0,
) -> None:
    if depth > 6:
        return
    if isinstance(obj, str):
        art = _artifact(tool, platform, ref_prefix, obj)
        if art:
            out.append(art)
        return
    if isinstance(obj, dict):
        for key, val in obj.items():
            k = str(key).lower()
            child_ref = f"{ref_prefix}.{key}" if ref_prefix else str(key)
            if k in _TEXT_KEYS and isinstance(val, str):
                art = _artifact(tool, platform, child_ref, val)
                if art:
                    out.append(art)
            elif isinstance(val, (dict, list)):
                _walk_dict(val, tool=tool, platform=platform, ref_prefix=child_ref, out=out, depth=depth + 1)
        return
    if isinstance(obj, list):
        for i, item in enumerate(obj[:40]):
            _walk_dict(item, tool=tool, platform=platform, ref_prefix=f"{ref_prefix}[{i}]", out=out, depth=depth + 1)


def _tool_result_dict(tr: Any) -> dict[str, Any] | None:
    if isinstance(tr, dict):
        return tr
    if hasattr(tr, "model_dump"):
        try:
            return tr.model_dump()
        except Exception:
            pass
    tool = getattr(tr, "tool", None)
    if tool is not None:
        return {
            "tool": tool,
            "success": getattr(tr, "success", False),
            "data": getattr(tr, "data", None) or [],
            "raw_output": getattr(tr, "raw_output", None),
        }
    return None


def collect_from_tool_results(tool_results: list[Any] | None) -> list[TextArtifact]:
    artifacts: list[TextArtifact] = []
    for tr in tool_results or []:
        tr = _tool_result_dict(tr)
        if not tr:
            continue
        tool = str(tr.get("tool") or "unknown")
        data = tr.get("data")
        if isinstance(data, list):
            for i, row in enumerate(data[:60]):
                platform = None
                if isinstance(row, dict):
                    platform = str(row.get("platform") or row.get("site") or row.get("source") or "") or None
                _walk_dict(row, tool=tool, platform=platform, ref_prefix=f"{tool}[{i}]", out=artifacts)
        elif isinstance(data, dict):
            _walk_dict(data, tool=tool, platform=None, ref_prefix=tool, out=artifacts)
        raw = tr.get("raw_output")
        if isinstance(raw, str) and len(raw) > 20:
            art = _artifact(tool, None, f"{tool}.raw_output", raw[:4000])
            if art:
                artifacts.append(art)
    return _dedupe_artifacts(artifacts)


def collect_from_evidence(evidence: Any) -> list[TextArtifact]:
    artifacts: list[TextArtifact] = []
    if evidence is None:
        return artifacts

    unified = getattr(evidence, "unified_profile", None) or (
        evidence.get("unified_profile") if isinstance(evidence, dict) else None
    )
    if isinstance(unified, dict):
        for field in ("bios", "names", "locations", "organizations", "search_findings"):
            for item in unified.get(field) or []:
                if isinstance(item, dict):
                    val = str(item.get("value") or "")
                    tool = str(item.get("source_tool") or "evidence")
                    plat = str(item.get("source_platform") or "") or None
                    art = _artifact(tool, plat, f"unified.{field}", val)
                    if art:
                        artifacts.append(art)

    gsi = getattr(evidence, "google_search_intel", None) or (
        evidence.get("google_search_intel") if isinstance(evidence, dict) else None
    )
    if isinstance(gsi, dict):
        for bucket, hits in gsi.items():
            if not isinstance(hits, list):
                continue
            for i, hit in enumerate(hits[:30]):
                if not isinstance(hit, dict):
                    continue
                blob = f"{hit.get('title', '')} {hit.get('snippet', '')}"
                art = _artifact("google_search_intel", str(bucket), f"gsi.{bucket}[{i}]", blob)
                if art:
                    artifacts.append(art)

    samurai = getattr(evidence, "samurai_social_intel", None) or (
        evidence.get("samurai_social_intel") if isinstance(evidence, dict) else None
    )
    if isinstance(samurai, dict):
        _walk_dict(samurai, tool="samurai", platform="social", ref_prefix="samurai_intel", out=artifacts)

    return _dedupe_artifacts(artifacts)


def _dedupe_artifacts(artifacts: list[TextArtifact]) -> list[TextArtifact]:
    seen: set[str] = set()
    out: list[TextArtifact] = []
    for art in artifacts:
        key = art.text[:120].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(art)
    return out[:200]


_TOOL_STATUS_RE = re.compile(
    r"skipped (theharvester|ghunt|spiderfoot|holehe)|"
    r"no gravatar profile|not configured|batch time budget|wall timeout|"
    r"use a company/organization domain",
    re.I,
)


def is_noise_text(text: str, *, seed_query: str = "") -> bool:
    t = (text or "").strip()
    if len(t) < 4:
        return True
    if _URL_ONLY_RE.match(t):
        return True
    if _HANDLE_ONLY_RE.match(t):
        return True
    low = t.lower()
    if low in _PLATFORM_SLUGS:
        return True
    seed = re.sub(r"[^a-z0-9]", "", (seed_query or "").lower())
    compact = re.sub(r"[^a-z0-9]", "", low)
    if seed and compact == seed:
        return True
    # Template / error pages
    if low.startswith("page not found") or low.startswith("404"):
        return True
    if _TOOL_STATUS_RE.search(t):
        return True
    return False


def _artifact_priority(art: TextArtifact) -> int:
    ref = (art.source_ref or "").lower()
    score = 0
    if any(token in ref for token in _HIGH_VALUE_REF):
        score += 4
    if art.source_platform:
        score += 2
    score += min(3, art.char_count // 80)
    return score


def refine_corpus(
    artifacts: list[TextArtifact],
    *,
    seed_query: str = "",
) -> tuple[list[TextArtifact], dict[str, int]]:
    """Drop URL/handle noise and prioritize bios and post text for ML analysis."""
    kept: list[TextArtifact] = []
    dropped_noise = 0
    for art in artifacts:
        if is_noise_text(art.text, seed_query=seed_query):
            dropped_noise += 1
            continue
        kept.append(art)
    kept.sort(key=_artifact_priority, reverse=True)
    kept = kept[:150]
    return kept, {
        "raw_artifacts": len(artifacts),
        "kept_artifacts": len(kept),
        "dropped_noise": dropped_noise,
    }
