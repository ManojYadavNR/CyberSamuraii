"""Cross-check investigation tool output — verified intel only for copilot summaries."""

from __future__ import annotations

import os
import re
from typing import Any

from services.account_confirmation import USERNAME_TOOLS, account_confirmed
from services.copilot_context import load_case_investigation_payloads
from services.investigation_brief import is_template_text, resolve_investigation_url

_SCANNER_ONLY = frozenset({"sherlock", "maigret", "social_analyzer", "whatsmyname", "blackbird"})
_RICH_TOOLS = frozenset({"samurai", "holehe", "google_dorking", "platform_probe"})

_HANDLE_RE = re.compile(r"^[a-z0-9._-]{2,64}$", re.I)


def _norm_handle(value: str) -> str:
    return (value or "").strip().lstrip("@").lower()


def _norm_url(url: str) -> str:
    u = (url or "").strip().rstrip("/").lower()
    if u.startswith("http://"):
        u = "https://" + u[7:]
    return u


def _handle_matches_query(handle: str, query: str) -> bool:
    h = _norm_handle(handle)
    q = _norm_handle(query)
    if not h or not q:
        return False
    if h == q:
        return True
    return q in h or h in q


def _samurai_verified_accounts(result: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """Samurai live scrape with profile fields matching the seed query."""
    out: list[dict[str, Any]] = []
    seed = str(result.get("query") or query or "").strip()

    for tr in result.get("tool_results") or []:
        if not isinstance(tr, dict) or tr.get("tool") != "samurai" or not tr.get("success"):
            continue
        for item in tr.get("data") or []:
            if not isinstance(item, dict):
                continue
            if item.get("platform") not in ("samurai_intel",) and item.get("check_type") != "samurai_intel":
                continue

            ig = item.get("instagram") if isinstance(item.get("instagram"), dict) else {}
            prof = ig.get("profile") if isinstance(ig.get("profile"), dict) else {}
            handle = str(prof.get("username") or item.get("username") or "").strip()
            stats = ig.get("stats") if isinstance(ig.get("stats"), dict) else {}
            reels = ig.get("reels") or []
            posts = ig.get("recent_posts") or []

            if handle and _handle_matches_query(handle, seed):
                has_content = any([
                    prof.get("follower_count"),
                    prof.get("biography"),
                    prof.get("full_name"),
                    stats.get("reels_collected"),
                    stats.get("recent_posts_collected"),
                    len(reels),
                    len(posts),
                ])
                if has_content:
                    url = resolve_investigation_url(
                        str(prof.get("profile_url") or f"https://www.instagram.com/{handle}/"),
                        seed,
                    )
                    if url:
                        out.append({
                            "tier": "verified",
                            "type": "social_account",
                            "platform": "instagram",
                            "handle": handle,
                            "display_name": prof.get("full_name"),
                            "url": url,
                            "follower_count": prof.get("follower_count"),
                            "biography": (prof.get("biography") or "")[:200] or None,
                            "reels_collected": stats.get("reels_collected") or len(reels),
                            "verification": "Samurai live profile scrape; handle matches investigation query",
                            "sources": ["samurai"],
                            "investigation_query": seed,
                        })

            fb = item.get("facebook") if isinstance(item.get("facebook"), dict) else {}
            fb_prof = fb.get("target_profile") if isinstance(fb.get("target_profile"), dict) else {}
            fb_slug = str(item.get("facebook_slug") or fb_prof.get("username") or fb_prof.get("id") or "").strip()
            fb_name = fb_prof.get("full_name") or fb_prof.get("name")
            if fb_slug or fb_name:
                fb_url = resolve_investigation_url(
                    str(fb_prof.get("profile_url") or f"https://www.facebook.com/{fb_slug}" if fb_slug else ""),
                    seed,
                )
                if fb_url and (fb_name or fb_prof.get("follower_count") or fb.get("photos")):
                    out.append({
                        "tier": "verified",
                        "type": "social_account",
                        "platform": "facebook",
                        "handle": fb_slug or None,
                        "display_name": fb_name,
                        "url": fb_url,
                        "verification": "Samurai Facebook scrape with profile content",
                        "sources": ["samurai"],
                        "investigation_query": seed,
                    })
    return out


def _fusion_verified_entities(result: dict[str, Any], query: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    fusion = result.get("fusion") or {}
    entities = fusion.get("deduplicated_entities") or fusion.get("entities") or []
    seed = str(result.get("query") or query or "")

    for ent in entities:
        if not isinstance(ent, dict):
            continue
        meta = ent.get("metadata") if isinstance(ent.get("metadata"), dict) else {}
        sources = set(ent.get("sources") or [])
        value = str(ent.get("value") or ent.get("canonical_value") or "")
        platform = str(meta.get("platform") or ent.get("type") or "")
        handle = str(meta.get("username") or meta.get("handle") or "")

        if meta.get("check_type") == "samurai_similar" or meta.get("status") == "similar_profile":
            continue

        if meta.get("verified") is True or meta.get("corroboration_status") == "confirmed":
            url = resolve_investigation_url(str(meta.get("url") or value), seed)
            out.append({
                "tier": "verified",
                "type": ent.get("type") or "entity",
                "platform": platform,
                "handle": handle or None,
                "value": value,
                "url": url,
                "fusion_score": ent.get("fusion_score"),
                "reliability_score": ent.get("reliability_score"),
                "verification": "Fusion marked confirmed",
                "sources": sorted(sources),
                "investigation_query": seed,
            })
            continue

        if account_confirmed(meta, sources, seed_email=seed if "@" in seed else None):
            url = resolve_investigation_url(str(meta.get("url") or value), seed)
            out.append({
                "tier": "verified",
                "type": ent.get("type") or "account",
                "platform": platform,
                "handle": handle or None,
                "value": value,
                "url": url,
                "fusion_score": ent.get("fusion_score"),
                "verification": "Live tool confirmation (Maigret/Holehe/Social Analyzer)",
                "sources": sorted(sources),
                "investigation_query": seed,
            })
            continue

        fusion_score = float(ent.get("fusion_score") or 0)
        rich_sources = sources & _RICH_TOOLS
        if len(sources) >= 2 and fusion_score >= 0.55 and not (sources <= _SCANNER_ONLY):
            url = resolve_investigation_url(str(meta.get("url") or value), seed)
            out.append({
                "tier": "verified",
                "type": ent.get("type") or "entity",
                "platform": platform,
                "handle": handle or None,
                "value": value,
                "url": url,
                "fusion_score": fusion_score,
                "verification": f"Corroborated by {len(sources)} independent tools",
                "sources": sorted(sources),
                "investigation_query": seed,
            })
            continue

        if rich_sources and fusion_score >= 0.65 and meta.get("check_type") != "username_probe":
            url = resolve_investigation_url(str(meta.get("url") or value), seed)
            out.append({
                "tier": "verified",
                "type": ent.get("type") or "entity",
                "platform": platform,
                "handle": handle or None,
                "value": url or value,
                "url": url,
                "fusion_score": fusion_score,
                "verification": f"Rich intel source ({', '.join(sorted(rich_sources))})",
                "sources": sorted(sources),
                "investigation_query": seed,
            })

    return out


def _confirmed_findings_verified(result: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seed = str(result.get("query") or "")
    for item in result.get("confirmed_findings") or []:
        if not isinstance(item, dict):
            continue
        platform = str(item.get("platform") or item.get("type") or "")
        handle = str(item.get("username") or item.get("handle") or "")
        url = resolve_investigation_url(str(item.get("url") or item.get("profile_url") or ""), seed)
        out.append({
            "tier": "verified",
            "type": str(item.get("type") or "confirmed_finding"),
            "platform": platform,
            "handle": handle or None,
            "url": url,
            "value": handle or url or platform,
            "verification": "Pipeline confirmed finding",
            "sources": [str(item.get("source_tool") or item.get("tool") or "confirmed")],
            "investigation_query": seed,
            "raw": item,
        })
    return out


def _public_profiles_verified(result: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seed = str(result.get("query") or "")
    for item in result.get("public_profile_data") or []:
        if not isinstance(item, dict):
            continue
        out.append({
            "tier": "verified",
            "type": "public_profile",
            "platform": str(item.get("platform") or "gravatar"),
            "handle": item.get("username") or item.get("display_name"),
            "display_name": item.get("display_name") or item.get("name"),
            "url": resolve_investigation_url(str(item.get("profile_url") or item.get("url") or ""), seed),
            "verification": "Public profile enrichment",
            "sources": ["public_profile"],
            "investigation_query": seed,
        })
    return out


def _count_excluded_leads(result: dict[str, Any]) -> int:
    """Rough count of unverified scanner / lead rows excluded from summary."""
    excluded = len(result.get("investigation_leads") or [])
    for tr in result.get("tool_results") or []:
        if not isinstance(tr, dict) or not tr.get("success"):
            continue
        tool = str(tr.get("tool") or "")
        if tool in _SCANNER_ONLY:
            excluded += len(tr.get("data") or [])
    fusion = result.get("fusion") or {}
    for ent in fusion.get("deduplicated_entities") or fusion.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        sources = set(ent.get("sources") or [])
        if sources and sources <= _SCANNER_ONLY and len(sources) == 1:
            excluded += 1
    return excluded


def _dedupe_key(finding: dict[str, Any]) -> str:
    url = _norm_url(str(finding.get("url") or ""))
    if url:
        return f"url:{url}"
    platform = str(finding.get("platform") or "").lower()
    handle = _norm_handle(str(finding.get("handle") or finding.get("value") or ""))
    if platform and handle:
        return f"{platform}:{handle}"
    return str(finding.get("value") or finding.get("investigation_query") or id(finding))


def verify_investigation_result(result: dict[str, Any], *, query: str = "") -> dict[str, Any]:
    """Return verified findings and stats for one investigation."""
    if not isinstance(result, dict):
        return {"verified": [], "excluded_leads": 0, "investigation_query": query}

    q = str(result.get("query") or query or "")
    candidates: list[dict[str, Any]] = []
    candidates.extend(_confirmed_findings_verified(result))
    candidates.extend(_public_profiles_verified(result))
    candidates.extend(_samurai_verified_accounts(result, q))
    candidates.extend(_fusion_verified_entities(result, q))

    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        if not item.get("url") and not item.get("value") and not item.get("handle"):
            continue
        if item.get("url") and is_template_text(str(item["url"])):
            continue
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        verified.append(item)

    return {
        "investigation_query": q,
        "feature": result.get("feature"),
        "verified": verified,
        "verified_count": len(verified),
        "excluded_leads": _count_excluded_leads(result),
    }


def verify_case_intel(
    case_id: str,
    *,
    current_investigation_id: str = "",
    current_result: dict[str, Any] | None = None,
    current_query: str = "",
) -> dict[str, Any]:
    """Cross-check all investigations in a case; dedupe verified findings."""
    from services.enterprise.cases import get_case

    case = get_case(case_id) or {}
    payloads = load_case_investigation_payloads(
        case_id,
        current_investigation_id=current_investigation_id,
        current_result=current_result,
        current_query=current_query,
    )

    all_verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_excluded = 0
    queries: list[str] = []

    for item in payloads:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if not result:
            continue
        q = str(item.get("query") or result.get("query") or "")
        if q and q not in queries:
            queries.append(q)
        block = verify_investigation_result(result, query=q)
        total_excluded += int(block.get("excluded_leads") or 0)
        for finding in block.get("verified") or []:
            key = _dedupe_key(finding)
            if key in seen:
                continue
            seen.add(key)
            finding = dict(finding)
            finding["case_investigation_id"] = item.get("investigation_id")
            all_verified.append(finding)

    return {
        "scope": "case",
        "case_id": case_id,
        "case_number": case.get("case_number") or "",
        "title": case.get("title") or "",
        "investigation_count": len(payloads),
        "unique_queries": queries,
        "verified_findings": all_verified,
        "verified_count": len(all_verified),
        "excluded_unverified_leads": total_excluded,
    }


def _slim_dork_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in {
            "title": hit.get("title"),
            "url": hit.get("url"),
            "snippet": (str(hit.get("snippet") or ""))[:280],
            "platform": hit.get("platform"),
            "dork_query": hit.get("dork_query") or hit.get("query"),
            "topic": hit.get("topic") or hit.get("trigger_keyword"),
        }.items()
        if v
    }


def _extract_google_dork_hits(result: dict[str, Any], *, max_hits: int = 30) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tr in result.get("tool_results") or []:
        if not isinstance(tr, dict) or tr.get("tool") != "google_dorking" or not tr.get("success"):
            continue
        for item in tr.get("data") or []:
            if not isinstance(item, dict):
                continue
            if item.get("check_type") not in (None, "google_dork", "google_search_discovery"):
                continue
            url = str(item.get("url") or "").strip()
            if not url or is_template_text(url):
                continue
            key = _norm_url(url)
            if key in seen:
                continue
            seen.add(key)
            hits.append(_slim_dork_hit(item))
            if len(hits) >= max_hits:
                return hits
    return hits


def _extract_google_search_intel(result: dict[str, Any], *, max_each: int = 12) -> dict[str, Any]:
    evidence = result.get("evidence_extraction") or {}
    gsi = evidence.get("google_search_intel") if isinstance(evidence, dict) else {}
    if not isinstance(gsi, dict):
        return {}

    def _slice_list(key: str) -> list[Any]:
        raw = gsi.get(key)
        if not isinstance(raw, list):
            return []
        out: list[Any] = []
        for item in raw[:max_each]:
            if isinstance(item, dict):
                out.append({
                    k: v
                    for k, v in {
                        "title": item.get("title") or item.get("name") or item.get("label"),
                        "url": item.get("url"),
                        "snippet": (str(item.get("snippet") or item.get("summary") or ""))[:240],
                        "platform": item.get("platform"),
                        "topic": item.get("topic") or item.get("trigger_keyword"),
                        "name": item.get("name") or item.get("college") or item.get("organization"),
                        "role": item.get("role") or item.get("title"),
                    }.items()
                    if v
                })
            elif item:
                out.append(str(item)[:200])
        return out

    return {
        k: _slice_list(k)
        for k in (
            "colleges",
            "hackathon_wins",
            "employment",
            "highlights",
            "google_highlights",
            "social_posts",
            "instagram_posts",
            "facebook_posts",
            "discovered_keywords",
        )
        if gsi.get(k)
    }


def _extract_samurai_content(result: dict[str, Any], query: str, *, max_reels: int = 8) -> dict[str, Any]:
    seed = str(result.get("query") or query or "").strip()
    out: dict[str, Any] = {"investigation_query": seed, "profiles": [], "reels": [], "posts": [], "links": []}
    seen_links: set[str] = set()

    for tr in result.get("tool_results") or []:
        if not isinstance(tr, dict) or tr.get("tool") != "samurai" or not tr.get("success"):
            continue
        for item in tr.get("data") or []:
            if not isinstance(item, dict) or item.get("platform") not in ("samurai_intel",):
                continue
            ig = item.get("instagram") if isinstance(item.get("instagram"), dict) else {}
            prof = ig.get("profile") if isinstance(ig.get("profile"), dict) else {}
            handle = str(prof.get("username") or item.get("username") or "").strip()
            if handle:
                out["profiles"].append({
                    k: v
                    for k, v in {
                        "platform": "instagram",
                        "handle": handle,
                        "full_name": prof.get("full_name"),
                        "biography": (prof.get("biography") or "")[:400] or None,
                        "follower_count": prof.get("follower_count"),
                        "following_count": prof.get("following_count"),
                        "media_count": prof.get("media_count"),
                        "external_url": prof.get("external_url"),
                        "profile_url": prof.get("profile_url"),
                        "category": prof.get("category"),
                    }.items()
                    if v not in (None, "", 0)
                })
            for reel in (ig.get("reels") or [])[:max_reels]:
                if not isinstance(reel, dict):
                    continue
                out["reels"].append({
                    k: v
                    for k, v in {
                        "caption": (str(reel.get("caption") or ""))[:400],
                        "url": reel.get("url") or reel.get("permalink"),
                        "like_count": reel.get("like_count"),
                        "comment_count": reel.get("comment_count"),
                        "timestamp": reel.get("timestamp") or reel.get("taken_at"),
                    }.items()
                    if v not in (None, "", 0)
                })
            for post in (ig.get("recent_posts") or [])[:max_reels]:
                if not isinstance(post, dict):
                    continue
                out["posts"].append({
                    "caption": (str(post.get("caption") or post.get("text") or ""))[:300],
                    "url": post.get("url") or post.get("permalink"),
                })
            fb = item.get("facebook") if isinstance(item.get("facebook"), dict) else {}
            fb_prof = fb.get("target_profile") if isinstance(fb.get("target_profile"), dict) else {}
            if fb_prof.get("full_name") or fb_prof.get("name"):
                out["profiles"].append({
                    "platform": "facebook",
                    "name": fb_prof.get("full_name") or fb_prof.get("name"),
                    "url": fb_prof.get("profile_url"),
                })
            for block in (ig, fb, item.get("cross_platform") or {}):
                if not isinstance(block, dict):
                    continue
                for link in block.get("links") or []:
                    u = str(link if isinstance(link, str) else (link.get("url") if isinstance(link, dict) else ""))
                    if u.startswith("http") and _norm_url(u) not in seen_links:
                        seen_links.add(_norm_url(u))
                        out["links"].append(u)
    return out


def _extract_linguistic_summary(result: dict[str, Any]) -> dict[str, Any]:
    evidence = result.get("evidence_extraction") or {}
    ling = evidence.get("linguistic_analysis") if isinstance(evidence, dict) else {}
    if not isinstance(ling, dict):
        return {}
    return {
        k: v
        for k, v in {
            "language": (ling.get("language_profile") or {}).get("primary"),
            "topics": [
                t.get("topic")
                for t in (ling.get("topics") or [])[:10]
                if isinstance(t, dict) and t.get("topic")
            ],
            "keywords": (ling.get("keywords") or [])[:20],
            "cross_links": (ling.get("cross_links") or [])[:8],
        }.items()
        if v
    }


def build_research_intel(result: dict[str, Any], *, query: str = "") -> dict[str, Any]:
    """Dorking, Google search intel, Samurai content — supplementary to verified accounts."""
    q = str(result.get("query") or query or "")
    dork_hits = _extract_google_dork_hits(result)
    gsi = _extract_google_search_intel(result)
    samurai = _extract_samurai_content(result, q)
    linguistic = _extract_linguistic_summary(result)
    identity = result.get("identity_profile")
    return {
        "investigation_query": q,
        "google_dork_hits": dork_hits,
        "google_dork_hit_count": len(dork_hits),
        "google_search_intel": gsi,
        "samurai_content": samurai,
        "linguistic_analysis": linguistic,
        "identity_profile": identity if isinstance(identity, dict) else None,
    }


def _research_has_content(research: dict[str, Any]) -> bool:
    if not research:
        return False
    if research.get("google_dork_hit_count"):
        return True
    if research.get("google_search_intel"):
        return True
    sam = research.get("samurai_content") or {}
    if sam.get("profiles") or sam.get("reels") or sam.get("posts") or sam.get("links"):
        return True
    if research.get("linguistic_analysis") or research.get("identity_profile"):
        return True
    return False


def build_case_research_intel(
    case_id: str,
    *,
    current_investigation_id: str = "",
    current_result: dict[str, Any] | None = None,
    current_query: str = "",
    include_all_runs: bool = True,
) -> list[dict[str, Any]]:
    """One research block per linked investigation (no query dedupe — full case access)."""
    payloads = load_case_investigation_payloads(
        case_id,
        current_investigation_id=current_investigation_id,
        current_result=current_result,
        current_query=current_query,
    )
    blocks: list[dict[str, Any]] = []
    for item in payloads:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if not result:
            continue
        q = str(item.get("query") or result.get("query") or "")
        research = build_research_intel(result, query=q)
        research["investigation_id"] = item.get("investigation_id")
        research["created_at"] = item.get("created_at")
        research["tools_run"] = [
            str(tr.get("tool"))
            for tr in (result.get("tool_results") or [])
            if isinstance(tr, dict) and tr.get("tool")
        ]
        if include_all_runs or _research_has_content(research):
            blocks.append(research)
    return blocks


def build_full_case_llm_context(
    case_id: str,
    *,
    current_investigation_id: str = "",
    current_result: dict[str, Any] | None = None,
    current_query: str = "",
    max_chars: int | None = None,
) -> str:
    """Every investigation in the case — verified + dorking + Samurai + tools."""
    import json

    from services.copilot_context import _fit_llm_context
    from services.enterprise.cases import get_case

    limit = max_chars if max_chars is not None else int(os.getenv("COPILOT_CASE_CONTEXT_MAX_CHARS", "96000"))
    case = get_case(case_id) or {}
    payloads = load_case_investigation_payloads(
        case_id,
        current_investigation_id=current_investigation_id,
        current_result=current_result,
        current_query=current_query,
    )

    case_verified = verify_case_intel(
        case_id,
        current_investigation_id=current_investigation_id,
        current_result=current_result,
        current_query=current_query,
    )

    investigations: list[dict[str, Any]] = []
    for item in payloads:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        q = str(item.get("query") or result.get("query") or "")
        inv_block: dict[str, Any] = {
            "investigation_id": item.get("investigation_id"),
            "query": q,
            "query_type": item.get("query_type"),
            "created_at": item.get("created_at"),
            "status": item.get("status"),
            "is_current": bool(item.get("is_current")),
        }
        if result:
            verified = verify_investigation_result(result, query=q)
            inv_block["verified_findings"] = verified.get("verified") or []
            inv_block["research_intel"] = build_research_intel(result, query=q)
            inv_block["tools_run"] = [
                str(tr.get("tool"))
                for tr in (result.get("tool_results") or [])
                if isinstance(tr, dict) and tr.get("tool")
            ]
        else:
            inv_block["note"] = "No stored result yet"
        investigations.append(inv_block)

    payload = {
        "scope": "case",
        "access": "full",
        "case_id": case_id,
        "case_number": case.get("case_number") or "",
        "title": case.get("title") or "",
        "investigation_count": len(investigations),
        "investigations": investigations,
        "verified_findings": case_verified.get("verified_findings") or [],
        "verified_count": case_verified.get("verified_count") or 0,
        "excluded_unverified_leads": case_verified.get("excluded_unverified_leads") or 0,
        "unique_targets": case_verified.get("unique_queries") or [],
        "instruction": (
            f"FULL CASE ACCESS — all {len(investigations)} investigations are included below. "
            "Each entry has investigation_id, query, verified_findings, and research_intel "
            "(google dork hits, google_search_intel, Samurai reels/posts). "
            "Answer using ANY investigation. Cite investigation query and id when relevant."
        ),
    }
    return _fit_llm_context(payload, max_chars=limit)


def build_hybrid_llm_context(
    *,
    case_id: str = "",
    investigation_id: str = "",
    result: dict[str, Any] | None = None,
    query: str = "",
) -> str:
    """Verified accounts + full dorking / search / Samurai content for rich answers."""
    import json

    if case_id:
        return build_full_case_llm_context(
            case_id,
            current_investigation_id=investigation_id,
            current_result=result,
            current_query=query,
        )

    if result:
        block = verify_investigation_result(result, query=query or str(result.get("query") or ""))
        research = build_research_intel(result, query=query or str(result.get("query") or ""))
        payload = {
            "scope": "investigation",
            "investigation_id": investigation_id,
            "investigation_query": block.get("investigation_query"),
            "verified_findings": block.get("verified"),
            "verified_count": block.get("verified_count"),
            "excluded_unverified_leads": block.get("excluded_leads"),
            "research_intel": research if _research_has_content(research) else {},
            "instruction": (
                "Use verified_findings for confirmed accounts. "
                "Use research_intel for dorking, Google search, Samurai posts/reels, colleges, GitHub, etc."
            ),
        }
    else:
        payload = {"scope": "empty", "verified_findings": [], "verified_count": 0, "research_intel": {}}

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_verified_llm_context(
    *,
    case_id: str = "",
    investigation_id: str = "",
    result: dict[str, Any] | None = None,
    query: str = "",
) -> str:
    """JSON context for LLM — verified facts only."""
    import json

    if case_id:
        intel = verify_case_intel(
            case_id,
            current_investigation_id=investigation_id,
            current_result=result,
            current_query=query,
        )
    elif result:
        block = verify_investigation_result(result, query=query or str(result.get("query") or ""))
        intel = {
            "scope": "investigation",
            "investigation_id": investigation_id,
            "investigation_query": block.get("investigation_query"),
            "verified_findings": block.get("verified"),
            "verified_count": block.get("verified_count"),
            "excluded_unverified_leads": block.get("excluded_leads"),
        }
    else:
        intel = {"scope": "empty", "verified_findings": [], "verified_count": 0}

    payload = {
        **intel,
        "instruction": (
            "VERIFIED INTEL ONLY. Every item in verified_findings passed cross-check rules. "
            "Do NOT cite scanner-only or single-source enumeration hits. "
            "If the analyst asks about unverified data, say it was excluded and recommend manual checks."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _format_finding_line(f: dict[str, Any]) -> str:
    platform = str(f.get("platform") or f.get("type") or "finding").title()
    handle = f.get("handle")
    name = f.get("display_name")
    url = f.get("url")
    parts = [f"**{platform}**"]
    if handle:
        parts.append(f"@{handle}")
    if name and name != handle:
        parts.append(f"({name})")
    if f.get("follower_count"):
        parts.append(f"· {f['follower_count']} followers")
    if f.get("reels_collected"):
        parts.append(f"· {f['reels_collected']} reels scraped")
    if url:
        parts.append(f"· [{url}]({url})")
    line = " ".join(str(p) for p in parts if p)
    reason = f.get("verification") or "Cross-checked"
    sources = ", ".join(f.get("sources") or [])
    return f"- {line}\n  - ✓ {reason}" + (f" · sources: {sources}" if sources else "")


def _format_research_section(research_blocks: list[dict[str, Any]] | dict[str, Any]) -> list[str]:
    lines: list[str] = []
    blocks = research_blocks if isinstance(research_blocks, list) else [research_blocks]

    for block in blocks:
        if not isinstance(block, dict) or not _research_has_content(block):
            continue
        q = block.get("investigation_query") or ""
        header = f"### Research · {q}" if q else "### Research & dorking"
        lines.append(header)

        dork_hits = block.get("google_dork_hits") or []
        if dork_hits:
            lines.append(f"**Google dork hits ({len(dork_hits)}):**")
            for hit in dork_hits[:8]:
                title = hit.get("title") or hit.get("url") or "Result"
                url = hit.get("url")
                snippet = (hit.get("snippet") or "")[:120]
                if url:
                    lines.append(f"- [{title}]({url})" + (f" — {snippet}" if snippet else ""))
                else:
                    lines.append(f"- {title}")
            if len(dork_hits) > 8:
                lines.append(f"- _…and {len(dork_hits) - 8} more dork results_")

        gsi = block.get("google_search_intel") or {}
        for key, label in (
            ("colleges", "Colleges / schools"),
            ("hackathon_wins", "Hackathons"),
            ("employment", "Employment"),
            ("highlights", "Web highlights"),
        ):
            items = gsi.get(key) or []
            if not items:
                continue
            lines.append(f"**{label}:**")
            for item in items[:5]:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("url") or "Item"
                    url = item.get("url")
                    lines.append(f"- [{name}]({url})" if url else f"- {name}")
                else:
                    lines.append(f"- {item}")
            if len(items) > 5:
                lines.append(f"- _…and {len(items) - 5} more_")

        sam = block.get("samurai_content") or {}
        reels = sam.get("reels") or []
        if reels:
            lines.append("**Instagram reels / posts:**")
            for reel in reels[:4]:
                cap = (reel.get("caption") or "")[:140].replace("\n", " ")
                url = reel.get("url")
                if cap and url:
                    lines.append(f"- [{cap}…]({url})")
                elif cap:
                    lines.append(f"- {cap}…")
        links = sam.get("links") or []
        if links:
            lines.append("**Links found in profiles:** " + ", ".join(links[:5]))

        lines.append("")

    return lines


def format_verified_summary_markdown(intel: dict[str, Any]) -> str:
    """Deterministic opening summary — verified data only."""
    findings = intel.get("verified_findings") or intel.get("verified") or []
    verified_count = intel.get("verified_count", len(findings))
    excluded = int(intel.get("excluded_unverified_leads") or intel.get("excluded_leads") or 0)
    scope = intel.get("scope") or "investigation"

    lines = ["## ✓ Verified Intelligence Summary", ""]
    inv_total = intel.get("investigation_count") or len(intel.get("research_intel") or [])
    if inv_total:
        lines.append(f"**Full case access:** {inv_total} investigation(s) loaded for the copilot.")
        lines.append("")

    if scope == "case":
        case_num = intel.get("case_number") or intel.get("case_id") or "case"
        title = intel.get("title") or ""
        inv_n = intel.get("investigation_count") or 0
        lines.append(f"**Case:** {case_num}" + (f" · {title}" if title else ""))
        lines.append(f"**Investigations cross-checked:** {inv_n}")
        queries = intel.get("unique_queries") or []
        if queries:
            lines.append(f"**Targets:** {', '.join(queries[:8])}" + ("…" if len(queries) > 8 else ""))
    else:
        q = intel.get("investigation_query") or ""
        if q:
            lines.append(f"**Target:** {q}")

    lines.append(
        f"**Verified findings:** {verified_count} · **Excluded unverified tool hits:** {excluded}"
    )
    lines.append("")
    lines.append(
        "_Only cross-checked results are shown. Scanner enumeration hits and single-source "
        "probes were removed until manually verified._"
    )
    lines.append("")

    if not findings:
        lines.append("No findings passed verification yet. Run Samurai or live-scan tools, or corroborate across multiple sources.")
        return "\n".join(lines)

    lines.append("### Verified findings")
    for f in findings[:25]:
        lines.append(_format_finding_line(f))
    if len(findings) > 25:
        lines.append(f"- _…and {len(findings) - 25} more verified items_")

    research = intel.get("research_intel")
    research_lines = _format_research_section(research or [])
    if research_lines:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.extend(research_lines)
        lines.append("_Research/dorking items are investigative leads — verify before treating as confirmed identity._")

    lines.append("")
    lines.append("Ask follow-up questions about **verified accounts**, **dorking**, **colleges**, **GitHub**, **reels**, and more.")
    return "\n".join(lines)


def build_opening_summary(
    *,
    case_id: str = "",
    investigation_id: str = "",
    result: dict[str, Any] | None = None,
    query: str = "",
) -> dict[str, Any]:
    """Opening copilot message payload."""
    if case_id:
        intel = verify_case_intel(
            case_id,
            current_investigation_id=investigation_id,
            current_result=result,
            current_query=query,
        )
        intel["research_intel"] = build_case_research_intel(
            case_id,
            current_investigation_id=investigation_id,
            current_result=result,
            current_query=query,
            include_all_runs=True,
        )
    elif result:
        block = verify_investigation_result(result, query=query or str(result.get("query") or ""))
        research = build_research_intel(result, query=query or str(result.get("query") or ""))
        intel = {
            "scope": "investigation",
            "investigation_id": investigation_id,
            "investigation_query": block.get("investigation_query"),
            "verified_findings": block.get("verified"),
            "verified_count": block.get("verified_count"),
            "excluded_unverified_leads": block.get("excluded_leads"),
            "research_intel": research if _research_has_content(research) else {},
        }
    else:
        intel = {
            "scope": "empty",
            "verified_findings": [],
            "verified_count": 0,
            "excluded_unverified_leads": 0,
        }

    markdown = format_verified_summary_markdown(intel)
    return {
        **intel,
        "summary_markdown": markdown,
        "verified_context_json": build_hybrid_llm_context(
            case_id=case_id,
            investigation_id=investigation_id,
            result=result,
            query=query,
        ),
    }
