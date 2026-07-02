"""Lossless investigation packs + chunked context assembly for the LLM copilot."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from services.json_utils import to_json_safe

PACK_VERSION = 3

_SECTION_KEYS = (
    "merged_results",
    "confirmed_findings",
    "public_profile_data",
    "investigation_leads",
    "scan_summary",
    "fusion",
    "correlation",
    "graph",
    "discovery",
    "evidence_extraction",
    "identity_profile",
    "reverse_image_discovery",
    "image_correlation",
    "lead_visuals",
    "confidence_raw_inputs",
    "warnings",
)

_BROAD_QUERY_RE = re.compile(
    r"\b(everything|all\s+data|full\s+analysis|complete\s+picture|entire\s+investigation|"
    r"summarize\s+all|analyze\s+all|overview\s+of\s+everything)\b",
    re.I,
)

_TOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "google_dorking": ("dork", "google", "serp", "search intel", "hackathon", "college", "school", "news"),
    "samurai": ("samurai", "instagram", "facebook", " ig ", " fb ", "reel", "reels", "bio", "comment"),
    "maigret": ("maigret",),
    "sherlock": ("sherlock",),
    "whatsmyname": ("whatsmyname", "what's my name"),
    "social_analyzer": ("social analyzer", "social_analyzer"),
    "email_intel": ("email", "gravatar", "breach"),
    "image_intel": ("image intel", "ocr", "face", "metadata", "exif"),
    "reverse_image": ("reverse image", "lens", "tineye", "saucenao"),
}


def build_raw_investigation_pack(
    result: dict[str, Any],
    *,
    investigation_id: str = "",
    query: str = "",
) -> dict[str, Any]:
    """Store the investigation result verbatim — no field filtering."""
    raw_full = to_json_safe(result or {})
    seed_query = query or str(raw_full.get("query") or "")

    return {
        "pack_version": PACK_VERSION,
        "investigation_id": investigation_id,
        "query": seed_query,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "raw_full": raw_full,
        "chunk_digests": {},
        "chat_history": [],
    }


def get_raw_full(pack: dict[str, Any]) -> dict[str, Any]:
    """Support v1 packs that used `raw` instead of `raw_full`."""
    if pack.get("raw_full"):
        return pack["raw_full"]
    legacy = pack.get("raw")
    return legacy if isinstance(legacy, dict) else {}


def _json_len(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def iter_investigation_chunks(raw_full: dict[str, Any]) -> list[dict[str, Any]]:
    """Split investigation into analyzable chunks — each holds a full payload slice."""
    chunks: list[dict[str, Any]] = []

    for idx, tr in enumerate(raw_full.get("tool_results") or []):
        if not isinstance(tr, dict):
            continue
        tool = str(tr.get("tool") or f"tool_{idx}")
        chunks.append({
            "chunk_id": f"tool:{tool}:{idx}",
            "label": tool,
            "kind": "tool_result",
            "payload": tr,
        })

    meta = {
        "query": raw_full.get("query"),
        "query_normalized": raw_full.get("query_normalized"),
        "feature": raw_full.get("feature"),
        "execution_mode": raw_full.get("execution_mode"),
        "tools_succeeded": raw_full.get("tools_succeeded"),
        "tools_failed": raw_full.get("tools_failed"),
        "total_execution_time_ms": raw_full.get("total_execution_time_ms"),
    }
    if any(v is not None for v in meta.values()):
        chunks.append({
            "chunk_id": "section:run_metadata",
            "label": "run_metadata",
            "kind": "metadata",
            "payload": meta,
        })

    for key in _SECTION_KEYS:
        value = raw_full.get(key)
        if value is None:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        chunks.append({
            "chunk_id": f"section:{key}",
            "label": key,
            "kind": "section",
            "payload": value,
        })

    return chunks


def expand_oversized_chunks(
    chunks: list[dict[str, Any]],
    *,
    max_chars: int,
    items_per_part: int | None = None,
) -> list[dict[str, Any]]:
    """Split huge chunks into batched sub-chunks — no payload dropped, fewer LLM calls."""
    import os

    batch_n = items_per_part or max(1, int(os.getenv("COPILOT_ITEMS_PER_CHUNK", "12")))
    expanded: list[dict[str, Any]] = []
    for chunk in chunks:
        payload = chunk["payload"]
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(body) <= max_chars:
            expanded.append(chunk)
            continue

        if chunk["kind"] == "tool_result" and isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list) and len(data) > 1:
                base = {k: v for k, v in payload.items() if k != "data"}
                raw_out = payload.get("raw_output")
                part_lists = [data[i : i + batch_n] for i in range(0, len(data), batch_n)]
                total_parts = len(part_lists)
                for part_idx, part_items in enumerate(part_lists):
                    part_payload = {**base, "data": part_items, "_part": f"{part_idx + 1}/{total_parts}"}
                    expanded.append({
                        "chunk_id": f"{chunk['chunk_id']}:part{part_idx}",
                        "label": f"{chunk['label']} (part {part_idx + 1}/{total_parts})",
                        "kind": chunk["kind"],
                        "payload": part_payload,
                    })
                if raw_out and isinstance(raw_out, str) and len(raw_out) > 500:
                    expanded.append({
                        "chunk_id": f"{chunk['chunk_id']}:raw_output",
                        "label": f"{chunk['label']} raw_output",
                        "kind": "tool_raw_output",
                        "payload": {"tool": payload.get("tool"), "raw_output": raw_out},
                    })
                continue

        if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
            nodes = payload["nodes"]
            edges = payload.get("edges") or []
            base = {k: v for k, v in payload.items() if k not in ("nodes", "edges")}
            step = max(1, len(nodes) // max(1, (len(body) // max_chars) + 1))
            for part_idx in range(0, len(nodes), step):
                part_nodes = nodes[part_idx : part_idx + step]
                expanded.append({
                    "chunk_id": f"{chunk['chunk_id']}:nodes{part_idx}",
                    "label": f"{chunk['label']} nodes {part_idx + 1}-{part_idx + len(part_nodes)}",
                    "kind": chunk["kind"],
                    "payload": {**base, "nodes": part_nodes, "edges": edges, "_part": f"nodes {part_idx + 1}-{part_idx + len(part_nodes)}"},
                })
            continue

        expanded.append(chunk)
    return expanded


def build_investigation_index(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "chunk_count": len(chunks),
        "chunks": [
            {
                "chunk_id": c["chunk_id"],
                "label": c["label"],
                "kind": c["kind"],
                "bytes": _json_len(c["payload"]),
            }
            for c in chunks
        ],
    }


def needs_full_coverage(message: str) -> bool:
    return bool(_BROAD_QUERY_RE.search(message))


def select_chunk_ids(message: str, chunks: list[dict[str, Any]]) -> set[str] | None:
    """
    Return chunk ids relevant to the user message, or None to mean all chunks.
    Focused questions still use all cached digests at answer time; this only limits new map work.
    """
    if needs_full_coverage(message):
        return None

    msg = f" {message.lower()} "
    matched: set[str] = set()

    for chunk in chunks:
        label = chunk["label"].lower()
        if label in msg or label.replace("_", " ") in msg:
            matched.add(chunk["chunk_id"])

    for tool, aliases in _TOOL_ALIASES.items():
        if any(alias in msg for alias in aliases):
            for chunk in chunks:
                if tool in chunk["label"].lower() or tool in chunk["chunk_id"]:
                    matched.add(chunk["chunk_id"])

    topic_map = {
        "college": ("google_dorking", "google_search", "evidence_extraction", "lead_visual"),
        "school": ("google_dorking", "google_search", "evidence_extraction"),
        "hackathon": ("google_dorking", "google_search", "lead_visual"),
        "account": ("fusion", "correlation", "sherlock", "maigret", "confirmed_findings"),
        "graph": ("graph", "correlation"),
        "pivot": ("discovery",),
        "image": ("image_intel", "reverse_image", "image_correlation", "lead_visual"),
        "face": ("image_intel", "face"),
    }
    for keyword, labels in topic_map.items():
        if keyword in msg:
            for chunk in chunks:
                if any(lbl in chunk["label"].lower() or lbl in chunk["chunk_id"] for lbl in labels):
                    matched.add(chunk["chunk_id"])

    return matched if matched else None


_CORE_CHUNK_LABELS = frozenset({
    "run_metadata", "fusion", "correlation", "identity_profile", "evidence_extraction",
})


def chunks_for_message(
    message: str,
    chunks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """
    Pick chunks for this question.
    - focused: only relevant tools/sections (+ small core context) — fast
    - full: every chunk — used for broad 'summarize everything' questions
    """
    if needs_full_coverage(message):
        return chunks, "full"

    selected_ids = select_chunk_ids(message, chunks)
    if selected_ids is None:
        # General question — compact core + key tools only (not all Maigret rows).
        compact_ids = {
            c["chunk_id"] for c in chunks
            if c["label"] in _CORE_CHUNK_LABELS
            or c["kind"] == "metadata"
            or c["label"] in ("samurai", "google_dorking", "sherlock", "platform_probe", "blackbird")
        }
        active = [c for c in chunks if c["chunk_id"] in compact_ids]
        return active, "compact"

    for chunk in chunks:
        if chunk["label"] in _CORE_CHUNK_LABELS or chunk["kind"] == "metadata":
            selected_ids.add(chunk["chunk_id"])

    active = [c for c in chunks if c["chunk_id"] in selected_ids]
    return active, "focused"


def chunk_to_json(chunk: dict[str, Any]) -> str:
    return json.dumps(
        {"chunk_id": chunk["chunk_id"], "label": chunk["label"], "data": chunk["payload"]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def pack_single_pass_context(chunks: list[dict[str, Any]], *, query: str) -> str:
    """When everything fits in one window, send full chunk payloads directly."""
    body = {
        "query": query,
        "coverage": "complete_single_pass",
        "chunks": [
            {"chunk_id": c["chunk_id"], "label": c["label"], "data": c["payload"]}
            for c in chunks
        ],
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def total_chunks_size(chunks: list[dict[str, Any]]) -> int:
    return sum(_json_len(c["payload"]) for c in chunks)


_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|hlo|howdy|yo|sup|good\s+(morning|afternoon|evening))\s*[!?.]*\s*$",
    re.I,
)


def is_greeting(message: str) -> bool:
    return bool(_GREETING_RE.match(message.strip()))


def build_fast_chat_context(raw_full: dict[str, Any], *, max_chars: int = 22000) -> str:
    """
    One JSON blob for fast copilot replies — curated intel layers, not every Maigret row.
    Full raw pack remains on disk for deep 'summarize everything' questions.
    """
    evidence = raw_full.get("evidence_extraction") or {}
    if not isinstance(evidence, dict):
        evidence = {}

    slim: dict[str, Any] = {
        "query": raw_full.get("query"),
        "tools": [
            {
                "tool": tr.get("tool"),
                "success": tr.get("success"),
                "error": tr.get("error"),
                "record_count": len(tr.get("data") or []) if isinstance(tr.get("data"), list) else 0,
            }
            for tr in (raw_full.get("tool_results") or [])
            if isinstance(tr, dict)
        ],
        "fusion": raw_full.get("fusion"),
        "identity_profile": raw_full.get("identity_profile"),
        "correlation": raw_full.get("correlation"),
        "google_search_intel": evidence.get("google_search_intel"),
        "samurai_social_intel": evidence.get("samurai_social_intel"),
        "unified_profile": evidence.get("unified_profile"),
        "confirmed_findings": raw_full.get("confirmed_findings"),
        "investigation_leads": raw_full.get("investigation_leads"),
        "scan_summary": raw_full.get("scan_summary"),
    }

    # Include full Samurai + dorking tool payloads (posts, bios) when present.
    for tr in raw_full.get("tool_results") or []:
        if not isinstance(tr, dict):
            continue
        tool = str(tr.get("tool") or "")
        if tool in ("samurai", "google_dorking", "sherlock", "platform_probe", "blackbird"):
            slim[f"tool_{tool}"] = tr

    body = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    if len(body) <= max_chars:
        return body
    return body[:max_chars]


def build_copilot_llm_context(raw_full: dict[str, Any], *, max_chars: int = 3500) -> str:
    """
    Slim context for fast copilot LLM turns — skips huge identity blobs and caps scanner rows.
    """
    evidence = raw_full.get("evidence_extraction") or {}
    if not isinstance(evidence, dict):
        evidence = {}

    fusion = raw_full.get("fusion") or {}
    correlation = raw_full.get("correlation") or {}

    ling = evidence.get("linguistic_analysis")
    ling_slim: dict[str, Any] | None = None
    if isinstance(ling, dict):
        ling_slim = {
            "language": (ling.get("language_profile") or {}).get("primary"),
            "topics": [
                t.get("topic")
                for t in (ling.get("topics") or [])[:8]
                if isinstance(t, dict) and t.get("topic")
            ],
            "keywords": (ling.get("keywords") or [])[:15],
            "entity_count": len(ling.get("named_entities") or []),
            "cross_links": (ling.get("cross_links") or [])[:6],
            "contradictions": ling.get("contradictions") or [],
            "sentiment": ling.get("sentiment_overview"),
        }

    slim: dict[str, Any] = {
        "query": raw_full.get("query"),
        "tools": [
            {
                "tool": tr.get("tool"),
                "success": tr.get("success"),
                "error": tr.get("error"),
                "record_count": len(tr.get("data") or []) if isinstance(tr.get("data"), list) else 0,
            }
            for tr in (raw_full.get("tool_results") or [])
            if isinstance(tr, dict)
        ],
        "fusion_score": fusion.get("fusion_score") if isinstance(fusion, dict) else None,
        "correlation_clusters": (correlation.get("clusters") or [])[:2] if isinstance(correlation, dict) else [],
        "samurai_social_intel": evidence.get("samurai_social_intel"),
        "google_search_intel": evidence.get("google_search_intel"),
        "confirmed_findings": raw_full.get("confirmed_findings"),
        "scan_summary": raw_full.get("scan_summary"),
    }
    if ling_slim:
        slim["linguistic_analysis"] = ling_slim

    _rich = ("samurai", "google_dorking", "platform_probe", "blackbird")
    _scan = ("maigret", "social_analyzer", "whatsmyname", "sherlock")

    for tr in raw_full.get("tool_results") or []:
        if not isinstance(tr, dict):
            continue
        tool = str(tr.get("tool") or "")
        if tool in _rich:
            slim[f"tool_{tool}"] = tr
        elif tool in _scan:
            data = tr.get("data")
            hits = data[:8] if isinstance(data, list) else data
            slim[f"tool_{tool}"] = {
                "tool": tool,
                "success": tr.get("success"),
                "hit_count": len(data) if isinstance(data, list) else 0,
                "hits": hits,
            }

    return _fit_llm_context(slim, max_chars=max_chars)


def _fit_llm_context(slim: dict[str, Any], *, max_chars: int) -> str:
    """Shrink payload progressively while keeping linguistic signals when present."""

    def _encode(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    body = _encode(slim)
    if len(body) <= max_chars:
        return body

    working = dict(slim)
    for key in list(working.keys()):
        if not key.startswith("tool_"):
            continue
        entry = working.get(key)
        if isinstance(entry, dict) and isinstance(entry.get("hits"), list):
            working[key] = {**entry, "hits": entry["hits"][:4]}

    body = _encode(working)
    if len(body) <= max_chars:
        return body

    clusters = working.get("correlation_clusters") or []
    if isinstance(clusters, list):
        working["correlation_clusters"] = [
            {
                "account_cluster_id": c.get("account_cluster_id"),
                "linked_accounts": (c.get("linked_accounts") or [])[:2],
            }
            for c in clusters[:1]
            if isinstance(c, dict)
        ]

    body = _encode(working)
    if len(body) <= max_chars:
        return body

    ling = working.get("linguistic_analysis")
    for key in [k for k in working if k.startswith("tool_")]:
        working.pop(key, None)
    working.pop("samurai_social_intel", None)
    working.pop("google_search_intel", None)

    body = _encode(working)
    if len(body) <= max_chars:
        return body

    essential = {
        "query": working.get("query"),
        "tools": working.get("tools"),
        "fusion_score": working.get("fusion_score"),
        "linguistic_analysis": ling,
    }
    body = _encode({k: v for k, v in essential.items() if v is not None})
    return body[:max_chars] if len(body) > max_chars else body


_LARGE_TOOL_PAYLOADS = frozenset({"maigret", "social_analyzer", "whatsmyname", "sherlock"})
_LARGE_TOOL_MAX_ROWS = 80


def _slim_tool_payload(tr: dict[str, Any]) -> dict[str, Any]:
    """Keep full payloads for rich tools; cap huge username scanners."""
    tool = str(tr.get("tool") or "")
    if tool not in _LARGE_TOOL_PAYLOADS:
        return tr
    data = tr.get("data")
    if not isinstance(data, list) or len(data) <= _LARGE_TOOL_MAX_ROWS:
        return tr
    return {
        **tr,
        "data": data[:_LARGE_TOOL_MAX_ROWS],
        "_data_truncated": len(data) - _LARGE_TOOL_MAX_ROWS,
        "_data_total": len(data),
    }


def build_chat_context(
    raw_full: dict[str, Any],
    *,
    brief: dict[str, Any] | None = None,
    message: str = "",
    max_chars: int = 22000,
) -> tuple[str, str]:
    """
    Assemble investigation-only context for any analyst question.
    Uses indexed brief + tool payloads + intel layers — never external knowledge.
    """
    query = str(raw_full.get("query") or "")

    if needs_full_coverage(message):
        chunks = expand_oversized_chunks(
            iter_investigation_chunks(raw_full),
            max_chars=max(4000, max_chars // 4),
        )
        text = pack_single_pass_context(chunks, query=query)
        return text[:max_chars], "full_raw"

    evidence = raw_full.get("evidence_extraction") or {}
    if not isinstance(evidence, dict):
        evidence = {}

    body: dict[str, Any] = {"query": query}
    if brief:
        body["brief"] = {
            "status": brief.get("status"),
            "tools_done": brief.get("tools_done"),
            "facts": brief.get("facts"),
            "by_tool": brief.get("by_tool"),
            "fusion": brief.get("fusion"),
            "identity_profile": brief.get("identity_profile"),
            "correlation_summary": brief.get("correlation_summary"),
            "llm_notes": brief.get("llm_notes"),
        }

    body["investigation"] = {
        "fusion": raw_full.get("fusion"),
        "correlation": raw_full.get("correlation"),
        "identity_profile": raw_full.get("identity_profile"),
        "graph": raw_full.get("graph"),
        "google_search_intel": evidence.get("google_search_intel"),
        "samurai_social_intel": evidence.get("samurai_social_intel"),
        "unified_profile": evidence.get("unified_profile"),
        "confirmed_findings": raw_full.get("confirmed_findings"),
        "investigation_leads": raw_full.get("investigation_leads"),
        "scan_summary": raw_full.get("scan_summary"),
        "discovery": raw_full.get("discovery"),
    }

    tool_payloads: dict[str, Any] = {}
    for tr in raw_full.get("tool_results") or []:
        if isinstance(tr, dict) and tr.get("tool"):
            tool_payloads[str(tr["tool"])] = _slim_tool_payload(tr)
    if tool_payloads:
        body["tool_payloads"] = tool_payloads

    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text, "investigation_data"

    # Drop bulky by_tool payloads first, keep structured facts.
    if brief and isinstance(body.get("brief"), dict):
        body["brief"].pop("by_tool", None)
        text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text, "investigation_data"

    return text[:max_chars], "investigation_data"
