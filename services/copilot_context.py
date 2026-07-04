"""Lossless investigation packs + chunked context assembly for the LLM copilot."""

from __future__ import annotations

import json
import os
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


def _build_verification_summary(raw_full: dict[str, Any]) -> dict[str, Any]:
    """Signals the LLM can use to judge reliability of tool output."""
    tools = raw_full.get("tool_results") or []
    failed: list[str] = []
    succeeded: list[str] = []
    for tr in tools:
        if not isinstance(tr, dict):
            continue
        name = str(tr.get("tool") or "unknown")
        if tr.get("success"):
            succeeded.append(name)
        else:
            failed.append(name)

    warnings = [str(w) for w in (raw_full.get("warnings") or [])[:8]]
    confirmed = [c for c in (raw_full.get("confirmed_findings") or []) if isinstance(c, dict)]
    leads = [l for l in (raw_full.get("investigation_leads") or []) if isinstance(l, dict)]

    fusion = raw_full.get("fusion") or {}
    entities = []
    if isinstance(fusion, dict):
        entities = fusion.get("deduplicated_entities") or fusion.get("entities") or []

    corroborated: list[dict[str, Any]] = []
    single_source: list[dict[str, Any]] = []
    for ent in entities[:20]:
        if not isinstance(ent, dict):
            continue
        sources = ent.get("sources") or []
        val = ent.get("value") or ent.get("canonical_value")
        if not val:
            continue
        entry = {
            "type": ent.get("type"),
            "value": val,
            "fusion_score": ent.get("fusion_score"),
            "reliability_score": ent.get("reliability_score"),
        }
        if len(sources) >= 2:
            entry["sources"] = sources[:4]
            corroborated.append(entry)
        else:
            entry["source"] = sources[0] if sources else "single_tool"
            single_source.append(entry)

    evidence = raw_full.get("evidence_extraction") or {}
    ling = evidence.get("linguistic_analysis") if isinstance(evidence, dict) else {}
    contradictions = ling.get("contradictions") or [] if isinstance(ling, dict) else []

    scan = raw_full.get("scan_summary") or {}
    scan_note = ""
    if isinstance(scan, dict):
        scan_note = str(scan.get("summary") or scan.get("note") or "")

    return {
        "trust_note": "Tool output is unverified until corroborated. Treat scanner hits as leads.",
        "tools_succeeded": succeeded,
        "tools_failed": failed,
        "warnings": warnings,
        "confirmed_findings_count": len(confirmed),
        "confirmed_findings": confirmed[:6],
        "investigation_leads_count": len(leads),
        "investigation_leads": leads[:6],
        "corroborated_entities": corroborated[:8],
        "single_source_entities": single_source[:8],
        "contradictions": contradictions[:5] if isinstance(contradictions, list) else [],
        "global_fusion_score": fusion.get("fusion_score") if isinstance(fusion, dict) else None,
        "scan_summary_note": scan_note[:300] if scan_note else None,
    }


def _compact_verification_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    """Small verification block that survives tight per-investigation budgets."""
    if not isinstance(summary, dict):
        return {}
    return {
        k: v
        for k, v in {
            "trust_note": summary.get("trust_note"),
            "tools_failed": summary.get("tools_failed"),
            "warnings": (summary.get("warnings") or [])[:3],
            "confirmed_findings_count": summary.get("confirmed_findings_count"),
            "investigation_leads_count": summary.get("investigation_leads_count"),
            "corroborated_entities": (summary.get("corroborated_entities") or [])[:4],
            "single_source_entities": (summary.get("single_source_entities") or [])[:4],
            "global_fusion_score": summary.get("global_fusion_score"),
        }.items()
        if v not in (None, [], "", 0)
    }


def _fit_investigation_for_case_llm(result: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    """Build per-investigation case slice — keep verification signals even when budget is tight."""
    slim = _slim_investigation_for_llm(result)
    compact_vs = _compact_verification_summary(slim.get("verification_summary"))
    if compact_vs:
        slim["verification_summary"] = compact_vs

    for key in list(slim.keys()):
        if key.startswith("tool_"):
            slim.pop(key, None)
    slim.pop("samurai_social_intel", None)
    slim.pop("google_search_intel", None)

    try:
        fitted = json.loads(_fit_llm_context(slim, max_chars=max_chars))
    except Exception:
        fitted = slim
    if isinstance(fitted, dict) and compact_vs and "verification_summary" not in fitted:
        fitted["verification_summary"] = compact_vs
    return fitted if isinstance(fitted, dict) else {"query": result.get("query"), "verification_summary": compact_vs}


def _slim_investigation_for_llm(raw_full: dict[str, Any]) -> dict[str, Any]:
    """Curated single-investigation payload (shared by single + case scopes)."""
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

    entities = []
    if isinstance(fusion, dict):
        for ent in (fusion.get("deduplicated_entities") or fusion.get("entities") or [])[:20]:
            if not isinstance(ent, dict):
                continue
            entities.append({
                "type": ent.get("type"),
                "value": ent.get("value") or ent.get("canonical_value"),
                "sources": (ent.get("sources") or [])[:4],
                "fusion_score": ent.get("fusion_score"),
                "reliability_score": ent.get("reliability_score"),
            })

    slim: dict[str, Any] = {
        "query": raw_full.get("query"),
        "feature": raw_full.get("feature"),
        "warnings": (raw_full.get("warnings") or [])[:6],
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
        "entities": entities,
        "fusion_score": fusion.get("fusion_score") if isinstance(fusion, dict) else None,
        "correlation_clusters": (correlation.get("clusters") or [])[:2] if isinstance(correlation, dict) else [],
        "samurai_social_intel": evidence.get("samurai_social_intel"),
        "google_search_intel": evidence.get("google_search_intel"),
        "confirmed_findings": raw_full.get("confirmed_findings"),
        "investigation_leads": (raw_full.get("investigation_leads") or [])[:8],
        "scan_summary": raw_full.get("scan_summary"),
        "verification_summary": _build_verification_summary(raw_full),
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
    return slim


def build_copilot_llm_context(raw_full: dict[str, Any], *, max_chars: int = 3500) -> str:
    """
    Slim context for fast copilot LLM turns — skips huge identity blobs and caps scanner rows.
    """
    slim = _slim_investigation_for_llm(raw_full)
    return _fit_llm_context(slim, max_chars=max_chars)


def load_case_investigation_payloads(
    case_id: str,
    *,
    current_investigation_id: str = "",
    current_result: dict[str, Any] | None = None,
    current_query: str = "",
) -> list[dict[str, Any]]:
    """Load every investigation linked to a case (newest first), with result payloads."""
    from services.copilot_store import load_copilot_pack
    from services.enterprise.cases import list_case_investigations
    from services.investigation_runner import get_investigation

    links = list_case_investigations(case_id)
    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()

    for link in links:
        inv_id = str(link.get("investigation_id") or "")
        if not inv_id or inv_id in seen:
            continue
        seen.add(inv_id)

        result: dict[str, Any] = {}
        query = str(link.get("query") or "")
        query_type = ""
        status = "unknown"

        if inv_id == current_investigation_id and current_result:
            result = current_result if isinstance(current_result, dict) else {}
            query = current_query or query or str(result.get("query") or "")
            status = "complete" if result else status
        else:
            inv = get_investigation(inv_id) or {}
            result = inv.get("result") if isinstance(inv.get("result"), dict) else {}
            query = query or str(inv.get("query") or result.get("query") or "")
            query_type = str(inv.get("query_type") or result.get("feature") or "")
            status = str(inv.get("status") or ("complete" if result else "unknown"))

        if not result:
            pack = load_copilot_pack(inv_id)
            result = get_raw_full(pack) if pack else {}
            if not query and pack:
                query = str(pack.get("query") or "")

        if not result and not query:
            continue

        payloads.append({
            "investigation_id": inv_id,
            "query": query,
            "query_type": query_type or str(result.get("feature") or ""),
            "created_at": str(link.get("created_at") or ""),
            "status": status,
            "is_current": inv_id == current_investigation_id,
            "result": result,
        })

    # Include live investigation only when it belongs to this case (same-case race).
    if current_investigation_id and current_investigation_id not in seen and current_result:
        if investigation_linked_to_case(case_id, current_investigation_id):
            payloads.insert(0, {
            "investigation_id": current_investigation_id,
            "query": current_query or str(current_result.get("query") or ""),
            "query_type": str(current_result.get("feature") or ""),
            "created_at": "",
            "status": "complete",
            "is_current": True,
            "result": current_result,
        })

    return payloads


def investigation_linked_to_case(case_id: str, investigation_id: str) -> bool:
    """True when investigation_id is linked to case_id in enterprise DB."""
    from services.enterprise.cases import list_case_investigations

    if not case_id or not investigation_id:
        return False
    for link in list_case_investigations(case_id):
        if str(link.get("investigation_id") or "") == investigation_id:
            return True
    return False


def _case_context_max_investigations() -> int:
    raw = os.getenv("COPILOT_CASE_MAX_INVESTIGATIONS", "999")
    try:
        n = int(raw)
        return max(1, n)
    except ValueError:
        return 999


def _shrink_investigation_data(data: dict[str, Any]) -> dict[str, Any]:
    """Minimal per-investigation snapshot when case-wide context must shrink."""
    if not isinstance(data, dict):
        return {"note": str(data)[:200]}
    essential: dict[str, Any] = {
        "query": data.get("query"),
        "feature": data.get("feature"),
        "warnings": (data.get("warnings") or [])[:4],
        "tools": data.get("tools"),
        "fusion_score": data.get("fusion_score"),
        "entities": (data.get("entities") or [])[:10],
        "confirmed_findings": (data.get("confirmed_findings") or [])[:4],
        "investigation_leads": (data.get("investigation_leads") or [])[:4],
        "verification_summary": data.get("verification_summary"),
        "linguistic_analysis": data.get("linguistic_analysis"),
    }
    return {k: v for k, v in essential.items() if v is not None}


def build_case_copilot_llm_context(
    case_id: str,
    *,
    current_investigation_id: str = "",
    current_result: dict[str, Any] | None = None,
    current_query: str = "",
    max_chars: int = 32000,
    max_investigations: int | None = None,
) -> str:
    """
    Case-wide LLM context: every investigation under the case, not only the active one.
    Current investigation gets a larger share of the character budget.
    """
    from services.enterprise.cases import get_case

    case = get_case(case_id) or {}
    inv_limit = max_investigations if max_investigations is not None else _case_context_max_investigations()
    payloads = load_case_investigation_payloads(
        case_id,
        current_investigation_id=current_investigation_id,
        current_result=current_result,
        current_query=current_query,
    )[:inv_limit]

    if not payloads and current_result:
        return build_copilot_llm_context(current_result, max_chars=max_chars)

    header_budget = min(400, max_chars // 8)
    remaining = max(1200, max_chars - header_budget)
    n = max(1, len(payloads))
    # Current inv gets ~2x share; others share the rest.
    current_share = remaining // 2 if any(p.get("is_current") for p in payloads) and n > 1 else remaining // n
    other_share = max(400, (remaining - current_share) // max(1, n - (1 if any(p.get("is_current") for p in payloads) else 0)))

    investigations: list[dict[str, Any]] = []
    for item in payloads:
        budget = current_share if item.get("is_current") else other_share
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if result:
            data = _fit_investigation_for_case_llm(result, max_chars=budget)
        else:
            data = {"note": "No stored result payload yet", "query": item.get("query")}

        investigations.append({
            "investigation_id": item.get("investigation_id"),
            "query": item.get("query"),
            "query_type": item.get("query_type"),
            "created_at": item.get("created_at"),
            "status": item.get("status"),
            "is_current": bool(item.get("is_current")),
            "data": data,
        })

    case_payload = {
        "scope": "case",
        "case_id": case_id,
        "case_number": case.get("case_number") or "",
        "title": case.get("title") or "",
        "status": case.get("status") or "",
        "investigation_count": len(investigations),
        "investigations": investigations,
        "instruction": (
            "This is CASE-WIDE intelligence. Cross-check findings across ALL investigations below. "
            "Treat tool output as unverified unless corroborated or in confirmed_findings. "
            "Label reliability (CONFIRMED / LIKELY / UNVERIFIED LEAD / WEAK) and cite which query each finding came from."
        ),
    }
    return _fit_llm_context(case_payload, max_chars=max_chars)


def _compact_inv_research(research: dict[str, Any]) -> dict[str, Any]:
    """Shrink per-investigation research so more case runs fit in context."""
    if not isinstance(research, dict):
        return {}
    out = dict(research)
    hits = out.get("google_dork_hits") or []
    if isinstance(hits, list) and len(hits) > 12:
        out["google_dork_hits"] = hits[:12]
        out["_dork_truncated"] = len(hits) - 12
    sam = out.get("samurai_content") or {}
    if isinstance(sam, dict):
        out["samurai_content"] = {
            **sam,
            "reels": (sam.get("reels") or [])[:4],
            "posts": (sam.get("posts") or [])[:4],
            "links": (sam.get("links") or [])[:6],
        }
    gsi = out.get("google_search_intel") or {}
    if isinstance(gsi, dict):
        out["google_search_intel"] = {
            k: (v[:6] if isinstance(v, list) else v)
            for k, v in gsi.items()
        }
    return out


def _fit_case_llm_context(case_payload: dict[str, Any], *, max_chars: int) -> str:
    """Shrink case-wide payloads without dropping to an empty object."""

    def _encode(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    working = dict(case_payload)
    invs = [dict(i) for i in (working.get("investigations") or []) if isinstance(i, dict)]
    total = len(invs)

    for inv in invs:
        research = inv.get("research_intel")
        if isinstance(research, dict):
            inv["research_intel"] = _compact_inv_research(research)
        data = inv.get("data")
        if isinstance(data, dict):
            inv["data"] = _shrink_investigation_data(data)
    working["investigations"] = invs
    body = _encode(working)
    if len(body) <= max_chars:
        return body

    # Tighter compact pass — keep every investigation, trim research further.
    for inv in invs:
        research = inv.get("research_intel")
        if isinstance(research, dict):
            ri = _compact_inv_research(research)
            ri["google_dork_hits"] = (ri.get("google_dork_hits") or [])[:6]
            sam = ri.get("samurai_content") or {}
            if isinstance(sam, dict):
                ri["samurai_content"] = {**sam, "reels": (sam.get("reels") or [])[:2]}
            inv["research_intel"] = ri
    working["investigations"] = invs
    body = _encode(working)
    if len(body) <= max_chars:
        return body

    current = [i for i in invs if i.get("is_current")]
    others = [i for i in invs if not i.get("is_current")]
    ordered = current + others

    while len(ordered) > 1:
        ordered = ordered[:-1]
        working["investigations"] = ordered
        working["investigation_count"] = len(ordered)
        working["_truncated_investigations"] = total - len(ordered)
        body = _encode(working)
        if len(body) <= max_chars:
            return body

    if ordered:
        inv = ordered[0]
        working["investigations"] = [{
            "investigation_id": inv.get("investigation_id"),
            "query": inv.get("query"),
            "query_type": inv.get("query_type"),
            "is_current": bool(inv.get("is_current")),
            "data": _shrink_investigation_data(inv.get("data") if isinstance(inv.get("data"), dict) else {}),
        }]
        working["investigation_count"] = 1
        working["_truncated_investigations"] = max(0, total - 1)
        body = _encode(working)
        return body[:max_chars] if len(body) > max_chars else body

    header = {
        "scope": "case",
        "case_id": working.get("case_id"),
        "case_number": working.get("case_number"),
        "title": working.get("title"),
        "status": working.get("status"),
        "investigation_count": case_payload.get("investigation_count") or total,
        "note": "Case metadata only — rerun or open a specific investigation for full detail.",
    }
    body = _encode(header)
    return body[:max_chars] if len(body) > max_chars else body


def _fit_llm_context(slim: dict[str, Any], *, max_chars: int) -> str:
    """Shrink payload progressively while keeping linguistic signals when present."""

    def _encode(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    body = _encode(slim)
    if len(body) <= max_chars:
        return body

    if slim.get("scope") == "case" and isinstance(slim.get("investigations"), list):
        return _fit_case_llm_context(slim, max_chars=max_chars)

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
        "warnings": (working.get("warnings") or [])[:4],
        "confirmed_findings": (working.get("confirmed_findings") or [])[:4],
        "investigation_leads": (working.get("investigation_leads") or [])[:4],
        "entities": (working.get("entities") or [])[:6],
        "verification_summary": _compact_verification_summary(working.get("verification_summary")),
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
