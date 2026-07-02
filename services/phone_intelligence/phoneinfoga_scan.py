"""PhoneInfoga API scan — structured carrier, validation, and web footprint rows."""

from __future__ import annotations

import os
import re
from typing import Any

from schemas.common import ToolResult
from services.phone_intelligence.number_parser import parse_phone_number
from services.phone_intelligence.results import (
    rows_from_googlecse,
    rows_from_local,
    rows_from_numverify,
    rows_from_social_intel,
    rows_from_web_footprint,
)
from services.phone_intelligence.scan_all import (
    apply_phone_env,
    auto_search_dorks,
    call_numverify,
    fetch_phoneinfoga_number_info,
    run_phoneinfoga_scanner,
)
from services.phone_intelligence.social_lookup import lookup_social_accounts


def _include_web_search() -> bool:
    """Web dork DDGS runs are slow — google_dorking handles phone web search by default."""
    return os.getenv("PHONEINFOGA_WEB_SEARCH", "false").lower() in ("1", "true", "yes")


def scan_phoneinfoga_api(number: str, *, include_web: bool | None = None) -> dict[str, Any]:
    """Run PhoneInfoga REST scanners: number parse, local, numverify; web optional."""
    from services.phone_intelligence.runtime import ensure_phone_stack

    ensure_phone_stack()
    apply_phone_env()
    do_web = include_web if include_web is not None else _include_web_search()

    number_info = fetch_phoneinfoga_number_info(number)
    api_reachable = number_info is not None
    if not number_info:
        number_info = parse_phone_number(number)
    if not number_info:
        return {"success": False, "error": "Invalid or unparsable phone number"}

    international = number_info.get("international", number)
    e164 = str(number_info.get("e164") or international).replace(" ", "")

    local: dict[str, Any] = {}
    if api_reachable:
        local_out = run_phoneinfoga_scanner("local", number, dict(os.environ))
        local = local_out.get("result") if local_out.get("success") else {"error": local_out.get("error")}
    else:
        local = {
            "carrier": number_info.get("carrier"),
            "location": number_info.get("location"),
            "country": number_info.get("countryCode"),
            "valid": number_info.get("valid"),
        }

    numverify = call_numverify(os.environ.get("NUMVERIFY_API_KEY", ""), e164)

    # Fast social registration (ignorant + WhatsApp/Telegram + profile resolver) — matches Postman /scan/social core
    social_accounts = lookup_social_accounts(number_info, fast_only=True)

    web_footprint: dict[str, Any] | None = None
    if do_web:
        dorks_by_category: dict[str, Any] = {}
        if api_reachable:
            gs_out = run_phoneinfoga_scanner("googlesearch", number, dict(os.environ))
            if gs_out.get("success"):
                dorks_by_category = gs_out.get("result") or {}
        if not dorks_by_category:
            from services.google_dorking.queries import build_dork_queries

            pairs = build_dork_queries(number, query_type="phone", max_queries=3)
            dorks_by_category = {
                "general": [{"dork": d.query, "category": d.category} for d in pairs],
                "social_media": [],
            }
        elif os.getenv("PHONE_OSINT_FAST", "true").lower() in ("1", "true", "yes"):
            trimmed: dict[str, Any] = {}
            for cat, dorks in dorks_by_category.items():
                if isinstance(dorks, list):
                    trimmed[cat] = dorks[:2]
            dorks_by_category = trimmed
        web_footprint = auto_search_dorks(dorks_by_category)

    googlecse = None
    gkey = os.environ.get("GOOGLE_API_KEY", "")
    gcx = os.environ.get("GOOGLECSE_CX", "")
    if gkey and gcx and api_reachable:
        cse_out = run_phoneinfoga_scanner("googlecse", number, dict(os.environ))
        if cse_out.get("success"):
            googlecse = cse_out.get("result")

    return {
        "success": True,
        "number": number_info,
        "phoneinfoga_api": api_reachable,
        "local": local,
        "numverify": numverify,
        "social_accounts": social_accounts,
        "web_footprint": web_footprint,
        "googlecse": googlecse,
    }


def rows_from_phoneinfoga_scan(scan: dict[str, Any]) -> list[dict[str, Any]]:
    if not scan.get("success"):
        return []
    number_info = scan.get("number") or {}
    phone = str(number_info.get("e164") or number_info.get("international") or "")
    local = scan.get("local") or {}
    numverify = scan.get("numverify") or {}
    nv_data = (numverify.get("data") or {}) if numverify.get("success") else {}
    web = scan.get("web_footprint")
    social = scan.get("social_accounts") or {}
    social_summary = social.get("summary") or {}

    def _pick(*values: Any) -> Any:
        for value in values:
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
        return None

    summary: dict[str, Any] = {
        "platform": "_scan_summary",
        "phone": phone,
        "country_code": _pick(number_info.get("countryCode"), nv_data.get("country_code")),
        "country_name": nv_data.get("country_name"),
        "carrier": _pick(local.get("carrier"), number_info.get("carrier"), nv_data.get("carrier")),
        "location": _pick(local.get("location"), number_info.get("location"), nv_data.get("location")),
        "phoneinfoga_api": scan.get("phoneinfoga_api"),
        "numverify_ok": bool(numverify.get("success")),
        "web_hits": (web or {}).get("total_hits", 0),
        "registered_accounts_found": social_summary.get("registered_accounts_found", 0),
        "confirmed_links": social_summary.get("confirmed_links", 0),
        "whatsapp_registered": social_summary.get("whatsapp_registered"),
        "valid": nv_data.get("valid") if numverify.get("success") else number_info.get("valid"),
        "line_type": _pick(nv_data.get("line_type"), local.get("line_type")),
        "source_tool": "phoneinfoga",
    }
    rows: list[dict[str, Any]] = [summary]
    rows.extend(rows_from_numverify(numverify))
    rows.extend(rows_from_local(local if isinstance(local, dict) else {}, phone))
    if social:
        social_rows = rows_from_social_intel(number_info, social, source_tool="phoneinfoga")
        rows.extend(r for r in social_rows if r.get("platform") != "_scan_summary")
    rows.extend(rows_from_web_footprint(web, phone))
    rows.extend(rows_from_googlecse(scan.get("googlecse"), phone))
    for row in rows[1:]:
        row.setdefault("source_tool", "phoneinfoga")
    return rows


def run_phoneinfoga_tool(query: str, *, cli_urls: list[dict[str, Any]] | None = None) -> ToolResult:
    scan = scan_phoneinfoga_api(query)
    if not scan.get("success"):
        return ToolResult(
            tool="phoneinfoga",
            success=False,
            error=str(scan.get("error") or "PhoneInfoga scan failed"),
        )

    rows = rows_from_phoneinfoga_scan(scan)
    if cli_urls:
        seen = {str(r.get("url") or "") for r in rows if r.get("url")}
        for item in cli_urls:
            url = str(item.get("url") or "")
            if url and url not in seen:
                rows.append(item)
                seen.add(url)

    web_hits = (scan.get("web_footprint") or {}).get("total_hits", 0)
    nv = scan.get("numverify") or {}
    nv_ok = nv.get("success")
    social_summary = (scan.get("social_accounts") or {}).get("summary") or {}
    regs = int(social_summary.get("registered_accounts_found") or 0)
    links = int(social_summary.get("confirmed_links") or 0)
    carrier = (scan.get("local") or {}).get("carrier") or (scan.get("number") or {}).get("carrier")
    return ToolResult(
        tool="phoneinfoga",
        success=True,
        data=rows,
        raw_output=(
            f"PhoneInfoga API={'up' if scan.get('phoneinfoga_api') else 'offline'} · "
            f"carrier={carrier or 'n/a'} · numverify={'ok' if nv_ok else 'skip'} · "
            f"{regs} platform registration(s) · {links} social link(s) · "
            f"{web_hits} web hit(s) · {len(rows)} row(s)"
        ),
    )


def cli_url_rows(query: str, stdout: str) -> list[dict[str, Any]]:
    """Supplement API results with URLs from `phoneinfoga scan` CLI stdout."""
    url_re = re.compile(r"https?://[^\s\]\)>\"'\x1b]+")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url in url_re.findall(stdout):
        url = url.strip().rstrip(".,)")
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append({
            "platform": "phone_search",
            "phone": query,
            "url": url,
            "status": "search_reference",
            "verified": False,
            "check_type": "cli_web_search",
            "source_tool": "phoneinfoga",
        })
    return rows
