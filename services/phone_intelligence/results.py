"""Normalize phone OSINT payloads into orchestrator tool result rows."""

from __future__ import annotations

from typing import Any


def _summary_row(number_info: dict[str, Any], social: dict[str, Any]) -> dict[str, Any]:
    summary = social.get("summary") or {}
    return {
        "platform": "_scan_summary",
        "phone": number_info.get("e164") or number_info.get("international"),
        "country_code": number_info.get("countryCode"),
        "carrier": number_info.get("carrier"),
        "location": number_info.get("location"),
        "valid": number_info.get("valid"),
        "registered_accounts_found": summary.get("registered_accounts_found", 0),
        "confirmed_links": summary.get("confirmed_links", 0),
        "possible_links": summary.get("possible_links", 0),
        "profiles_with_url": summary.get("profiles_with_url", 0),
        "whatsapp_registered": summary.get("whatsapp_registered"),
    }


def rows_from_social_intel(
    number_info: dict[str, Any],
    social: dict[str, Any],
    *,
    source_tool: str = "phone_social_intel",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [_summary_row(number_info, social)]

    phone = number_info.get("e164") or number_info.get("international") or number_info.get("raw")
    for field in ("carrier", "location"):
        val = number_info.get(field)
        if val:
            rows.append({
                "platform": "phone_metadata",
                "phone": phone,
                "check_type": field,
                "status": "identified",
                "verified": True,
                field: val,
                "source_tool": source_tool,
            })

    for match in social.get("confirmed_matches") or []:
        platform = str(match.get("platform") or "unknown")
        rows.append({
            "platform": platform,
            "phone": phone,
            "url": match.get("url") or match.get("profile_url"),
            "username": match.get("username"),
            "title": match.get("title"),
            "snippet": match.get("snippet"),
            "status": "linked",
            "verified": True,
            "registered": True,
            "check_type": "phone_social_match",
            "confidence": match.get("confidence", "high"),
            "evidence": match.get("evidence"),
            "source_tool": source_tool,
        })

    for match in social.get("possible_matches") or []:
        platform = str(match.get("platform") or "unknown")
        rows.append({
            "platform": platform,
            "phone": phone,
            "url": match.get("url") or match.get("profile_url"),
            "username": match.get("username"),
            "title": match.get("title"),
            "snippet": match.get("snippet"),
            "status": "possible_match",
            "verified": False,
            "check_type": "phone_social_match",
            "confidence": match.get("confidence", "medium"),
            "evidence": match.get("evidence"),
            "source_tool": source_tool,
        })

    for pl in social.get("profile_links") or []:
        if not isinstance(pl, dict):
            continue
        platform = str(pl.get("platform") or "unknown")
        url = pl.get("profile_url")
        if not url and not pl.get("linked"):
            continue
        rows.append({
            "platform": platform,
            "phone": phone,
            "url": url,
            "username": pl.get("username"),
            "status": pl.get("status") or ("linked" if pl.get("linked") else "checked"),
            "verified": bool(pl.get("linked")),
            "registered": bool(pl.get("linked")),
            "check_type": "profile_resolution",
            "note": pl.get("note"),
            "source_tool": source_tool,
        })

    registered = social.get("registered_accounts") or {}
    for entry in registered.get("platforms") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("account_linked") is not True:
            continue
        rows.append({
            "platform": entry.get("platform") or entry.get("domain") or "platform",
            "phone": phone,
            "url": entry.get("profile_hint"),
            "status": "registered",
            "verified": True,
            "registered": True,
            "check_type": "platform_registration",
            "method": entry.get("method"),
            "source_tool": "ignorant",
        })

    for entry in registered.get("linked_accounts") or []:
        if not isinstance(entry, dict):
            continue
        plat = str(entry.get("platform") or entry.get("domain") or "platform")
        if any(r.get("platform") == plat and r.get("check_type") == "platform_registration" for r in rows):
            continue
        rows.append({
            "platform": plat,
            "phone": phone,
            "url": entry.get("profile_hint") or entry.get("url"),
            "status": "registered",
            "verified": True,
            "registered": True,
            "check_type": "platform_registration",
            "confidence": entry.get("confidence"),
            "evidence": entry.get("evidence"),
            "source_tool": "ignorant",
        })

    for key in ("whatsapp", "telegram"):
        pdata = (social.get("platforms") or {}).get(key) or {}
        url = pdata.get("profile_url") or pdata.get("web_url")
        if pdata.get("status") == "likely_registered":
            rows.append({
                "platform": key,
                "phone": phone,
                "url": url,
                "status": "registered",
                "verified": True,
                "registered": True,
                "check_type": "platform_registration",
                "confidence": "medium",
                "note": pdata.get("note"),
                "source_tool": source_tool,
            })
        elif pdata.get("status") == "link_generated" and url:
            rows.append({
                "platform": key,
                "phone": phone,
                "url": url,
                "status": "linked",
                "verified": False,
                "registered": False,
                "check_type": "platform_registration",
                "note": pdata.get("note"),
                "source_tool": source_tool,
            })

    return rows


def rows_from_numverify(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload.get("success"):
        return [{
            "platform": "numverify",
            "status": "failed",
            "check_type": "carrier_lookup",
            "error": payload.get("error"),
            "note": payload.get("fix"),
            "source_tool": "numverify",
        }]
    data = payload.get("data") or {}
    return [{
        "platform": "numverify",
        "phone": data.get("international_format") or data.get("number"),
        "status": "valid" if data.get("valid") else "invalid",
        "verified": bool(data.get("valid")),
        "check_type": "carrier_lookup",
        "carrier": data.get("carrier"),
        "location": data.get("location"),
        "line_type": data.get("line_type"),
        "country_name": data.get("country_name"),
        "source_tool": "numverify",
    }]


def rows_from_local(local: dict[str, Any], phone: str) -> list[dict[str, Any]]:
    if not local or local.get("error"):
        return []
    rows: list[dict[str, Any]] = []
    for key in ("carrier", "location", "country", "line_type", "local", "international"):
        val = local.get(key)
        if val:
            rows.append({
                "platform": "phone_local",
                "phone": phone,
                "check_type": key,
                "status": "identified",
                "verified": True,
                key: val,
                "source_tool": "phoneinfoga_local",
            })
    return rows


def rows_from_web_footprint(web: dict[str, Any] | None, phone: str) -> list[dict[str, Any]]:
    if not web:
        return []
    rows: list[dict[str, Any]] = []
    for category, block in (web.get("categories") or {}).items():
        if not isinstance(block, dict):
            continue
        for search in block.get("searches") or []:
            for hit in search.get("results") or []:
                url = hit.get("url")
                if not url:
                    continue
                rows.append({
                    "platform": search.get("site") or category,
                    "phone": phone,
                    "url": url,
                    "title": hit.get("title"),
                    "snippet": hit.get("snippet"),
                    "status": "search_reference",
                    "check_type": "google_dork",
                    "dork_category": category,
                    "dork_query": search.get("query"),
                    "verified": False,
                    "source_tool": "phone_web_search",
                })
    return rows[:40]


def rows_from_googlecse(payload: dict[str, Any] | None, phone: str) -> list[dict[str, Any]]:
    if not payload:
        return []
    rows: list[dict[str, Any]] = []
    items = payload if isinstance(payload, list) else payload.get("items") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("link") or item.get("url")
        if not url:
            continue
        rows.append({
            "platform": "google_cse",
            "phone": phone,
            "url": url,
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "status": "search_reference",
            "check_type": "google_cse",
            "verified": False,
            "source_tool": "googlecse",
        })
    return rows[:20]


def rows_from_social_only_scan(scan: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows from social-only scan (phone_social_intel tool)."""
    if not scan.get("success"):
        return []
    number_info = scan.get("number") or {}
    social = scan.get("social_accounts") or {}
    return rows_from_social_intel(number_info, social, source_tool="phone_social_intel")


def rows_from_full_scan(scan: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten scan_phone_all() into orchestrator tool result rows."""
    if not scan.get("success"):
        return []
    number_info = scan.get("number") or {}
    phone = number_info.get("e164") or number_info.get("international") or ""
    social = scan.get("social_accounts") or {}
    rows = rows_from_social_intel(number_info, social)
    rows.extend(rows_from_numverify(scan.get("numverify") or {}))
    rows.extend(rows_from_local(scan.get("local") or {}, str(phone)))
    rows.extend(rows_from_web_footprint(scan.get("web_footprint"), str(phone)))
    rows.extend(rows_from_googlecse(scan.get("googlecse"), str(phone)))

    summary = next((r for r in rows if r.get("platform") == "_scan_summary"), None)
    if summary:
        summary["phoneinfoga_api"] = scan.get("phoneinfoga_api")
        summary["web_hits"] = (scan.get("web_footprint") or {}).get("total_hits", 0)
        summary["numverify_ok"] = bool((scan.get("numverify") or {}).get("success"))
        summary["googlecse_ran"] = scan.get("googlecse") is not None
    return rows
