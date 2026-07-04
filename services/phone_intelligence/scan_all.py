"""Full phone scan — all PhoneInfoga APIs + social OSINT in one pass (from phoneNumber/scan_all.py)."""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None  # type: ignore

from services.phone_intelligence.number_parser import parse_phone_number
from services.phone_intelligence.social_lookup import lookup_social_accounts

PHONEINFOGA_BASE = os.environ.get("PHONEINFOGA_BASE", "http://127.0.0.1:5000/api")
MAX_RESULTS_PER_QUERY = int(os.environ.get("MAX_WEB_RESULTS", "5"))
SEARCH_WORKERS = int(os.environ.get("SEARCH_WORKERS", "4"))

CATEGORY_LABELS = {
    "social_media": "Social media",
    "disposable_providers": "Disposable SMS providers",
    "reputation": "Reputation / spam reports",
    "individuals": "People lookup / leaks",
    "general": "General web & documents",
}


def _load_env_file(path: str) -> dict[str, str]:
    opts: dict[str, str] = {}
    if not os.path.isfile(path):
        return opts
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            opts[key.strip()] = value.strip().strip('"').strip("'")
    return opts


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def apply_phone_env() -> dict[str, str]:
    """
    Merge phone OSINT keys from project .env and phoneNumber/phoneinfoga/.env.
    Non-empty values in phoneNumber/phoneinfoga/.env win (e.g. NUMVERIFY_API_KEY).
    """
    root = _project_root()
    candidates = [
        os.path.join(root, ".env"),
        os.path.join(root, "phoneNumber", "phoneinfoga", ".env"),
        os.path.join(os.getcwd(), "phoneNumber", "phoneinfoga", ".env"),
    ]
    merged: dict[str, str] = {}
    seen_paths: set[str] = set()
    for path in candidates:
        resolved = os.path.abspath(path)
        if resolved in seen_paths or not os.path.isfile(resolved):
            continue
        seen_paths.add(resolved)
        merged.update(_load_env_file(resolved))

    phone_infoga_env = os.path.join(root, "phoneNumber", "phoneinfoga", ".env")
    if os.path.isfile(phone_infoga_env):
        for key, value in _load_env_file(phone_infoga_env).items():
            if value:
                merged[key] = value

    for key, value in merged.items():
        if value or not os.environ.get(key):
            os.environ[key] = value
    return merged


def post_json(url: str, payload: dict, timeout: int = 120) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {"error": exc.reason}
        except json.JSONDecodeError:
            parsed = {"error": body or exc.reason}
        return exc.code, parsed
    except (URLError, OSError) as exc:
        return 0, {"error": str(exc)}


def get_json(url: str, headers: dict | None = None, timeout: int = 30) -> tuple[int, dict]:
    req = Request(url, headers=headers or {}, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {"message": exc.reason}
        except json.JSONDecodeError:
            parsed = {"message": body or exc.reason}
        return exc.code, parsed
    except (URLError, OSError) as exc:
        return 0, {"error": str(exc)}


def phoneinfoga_api_number(number: str) -> str:
    """PhoneInfoga REST API expects digits only (no +, spaces, or punctuation)."""
    return re.sub(r"\D", "", number or "")


def fetch_phoneinfoga_number_info(number: str) -> dict[str, Any] | None:
    api_number = phoneinfoga_api_number(number)
    if not api_number:
        return None
    status, data = post_json(f"{PHONEINFOGA_BASE}/v2/numbers", {"number": api_number}, timeout=30)
    if status == 200 and isinstance(data, dict):
        return data
    return None


def call_numverify(api_key: str, international_number: str) -> dict[str, Any]:
    if not api_key:
        return {
            "success": False,
            "error": "NUMVERIFY_API_KEY not set",
            "fix": "Add NUMVERIFY_API_KEY to phoneNumber/phoneinfoga/.env or project .env",
        }
    url = f"https://api.apilayer.com/number_verification/validate?number={international_number}"
    status, data = get_json(url, headers={"Apikey": api_key})
    if status == 200 and isinstance(data, dict) and "valid" in data:
        return {"success": True, "data": data}
    message = (data.get("message") or data.get("error") or str(data)) if isinstance(data, dict) else str(data)
    return {
        "success": False,
        "http_status": status,
        "error": message,
        "fix": "Subscribe to APILayer Number Verification API and copy the key.",
    }


def run_phoneinfoga_scanner(scanner: str, number: str, options: dict[str, str]) -> dict[str, Any]:
    api_number = phoneinfoga_api_number(number) or number
    status, data = post_json(
        f"{PHONEINFOGA_BASE}/v2/scanners/{scanner}/run",
        {"number": api_number, "options": options},
        timeout=120,
    )
    if status != 200:
        return {"success": False, "error": data.get("error", data) if isinstance(data, dict) else data}
    if isinstance(data, dict):
        return {"success": True, "result": data.get("result", data)}
    return {"success": False, "error": "invalid scanner response"}


def site_from_dork(dork: str) -> str:
    if dork.startswith("site:"):
        return dork.split()[0].replace("site:", "")
    return "web"


def run_web_query(dork: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "query": dork,
        "site": site_from_dork(dork),
        "result_count": 0,
        "results": [],
    }
    if DDGS is None:
        entry["error"] = "ddgs not installed"
        return entry
    try:
        hits = list(DDGS().text(dork, max_results=MAX_RESULTS_PER_QUERY))
        entry["results"] = [
            {
                "title": h.get("title", ""),
                "url": h.get("href", h.get("link", "")),
                "snippet": h.get("body", h.get("snippet", "")),
            }
            for h in hits
        ]
        entry["result_count"] = len(entry["results"])
    except Exception as exc:
        entry["error"] = str(exc)
    return entry


def auto_search_dorks(dorks_by_category: dict[str, Any]) -> dict[str, Any]:
    web: dict[str, Any] = {}
    total_hits = 0
    for category, dorks in (dorks_by_category or {}).items():
        if not isinstance(dorks, list):
            continue
        category_entries: list[dict] = []
        dork_list = [d.get("dork", "") for d in dorks if isinstance(d, dict) and d.get("dork")]
        if not dork_list:
            continue
        with ThreadPoolExecutor(max_workers=SEARCH_WORKERS) as pool:
            futures = {pool.submit(run_web_query, dork): dork for dork in dork_list}
            for future in as_completed(futures):
                category_entries.append(future.result())
        category_entries.sort(key=lambda x: x.get("result_count", 0), reverse=True)
        cat_hits = sum(e.get("result_count", 0) for e in category_entries)
        total_hits += cat_hits
        web[category] = {
            "label": CATEGORY_LABELS.get(category, category),
            "queries_run": len(category_entries),
            "total_hits": cat_hits,
            "searches": category_entries,
        }
    return {"categories": web, "total_hits": total_hits}


def _fallback_phone_dorks(number: str) -> dict[str, list[dict[str, str]]]:
    from services.google_dorking.queries import build_dork_queries

    pairs = build_dork_queries(number, query_type="phone", max_queries=12)
    return {
        "general": [{"dork": d.query, "category": d.category} for d in pairs],
        "social_media": [],
    }


def scan_phone_all(number: str, *, include_web: bool = True) -> dict[str, Any]:
    """
    Run every phone OSINT source once:
    PhoneInfoga local + googlesearch (+ googlecse if keyed), Numverify, social/ignorant, web DDGS.
    """
    from services.phone_intelligence.runtime import ensure_phone_stack

    ensure_phone_stack()
    env = apply_phone_env()
    options = dict(env)

    number_info = parse_phone_number(number)
    api_reachable = False
    if not number_info:
        number_info = fetch_phoneinfoga_number_info(number)
        if number_info:
            api_reachable = True
    else:
        # If parsed locally, still check if API is reachable by hitting it with the parsed number
        api_info = fetch_phoneinfoga_number_info(number_info.get("international", number))
        api_reachable = api_info is not None
    if not number_info:
        return {"success": False, "error": "Invalid or unparsable phone number"}

    international = number_info.get("international", number)
    e164 = str(number_info.get("e164") or international).replace(" ", "")

    # 1) PhoneInfoga local scanner (country, line type) when API server is up
    local: dict[str, Any] = {}
    if api_reachable:
        local_out = run_phoneinfoga_scanner("local", number, options)
        local = local_out.get("result") if local_out.get("success") else {"error": local_out.get("error")}
    else:
        local = {
            "carrier": number_info.get("carrier"),
            "location": number_info.get("location"),
            "country": number_info.get("countryCode"),
            "note": "PhoneInfoga API offline — using phonenumbers local parse",
        }

    # 2) Numverify / APILayer carrier validation
    numverify = call_numverify(options.get("NUMVERIFY_API_KEY", os.environ.get("NUMVERIFY_API_KEY", "")), e164)

    # 3) Social OSINT (ignorant + profile resolver + platform web search)
    social_accounts = lookup_social_accounts(number_info, fast_only=False)

    # 4) PhoneInfoga googlesearch dorks + DDGS auto-run (or fallback dorks)
    web_footprint: dict[str, Any] | None = None
    if include_web:
        fast_web = os.getenv("PHONE_OSINT_FAST", "true").lower() in ("1", "true", "yes")
        dorks_by_category: dict[str, Any] = {}
        if api_reachable and not fast_web:
            gs_out = run_phoneinfoga_scanner("googlesearch", number, options)
            if gs_out.get("success"):
                dorks_by_category = gs_out.get("result") or {}
        if not dorks_by_category:
            from services.google_dorking.queries import build_dork_queries

            pairs = build_dork_queries(number, query_type="phone", max_queries=4 if fast_web else 12)
            dorks_by_category = {
                "general": [{"dork": d.query, "category": d.category} for d in pairs],
                "social_media": [],
            }
        elif fast_web:
            trimmed: dict[str, Any] = {}
            for cat, dorks in dorks_by_category.items():
                if isinstance(dorks, list):
                    trimmed[cat] = dorks[:2]
            dorks_by_category = trimmed
        web_footprint = auto_search_dorks(dorks_by_category)
        if not web_footprint.get("total_hits"):
            web_footprint["note"] = "No web hits — check network or DDGS availability"

    # 5) Google Custom Search (optional API)
    googlecse = None
    gkey = options.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    gcx = options.get("GOOGLECSE_CX") or os.environ.get("GOOGLECSE_CX", "")
    if gkey and gcx and api_reachable:
        cse_out = run_phoneinfoga_scanner("googlecse", number, options)
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


def scan_phone_social_only(number: str) -> dict[str, Any]:
    """Social registration + profile resolution only (PhoneInfoga runs in phoneinfoga tool)."""
    from services.phone_intelligence.runtime import ensure_phone_stack

    ensure_phone_stack()
    apply_phone_env()

    number_info = parse_phone_number(number)
    if not number_info:
        number_info = fetch_phoneinfoga_number_info(number)
    if not number_info:
        return {"success": False, "error": "Invalid or unparsable phone number"}

    social_accounts = lookup_social_accounts(number_info, fast_only=False)
    return {
        "success": True,
        "number": number_info,
        "social_accounts": social_accounts,
    }
