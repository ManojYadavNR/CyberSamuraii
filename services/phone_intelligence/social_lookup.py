"""
Social account OSINT for phone numbers — CID investigation module.

Techniques used:
  1. Platform registration check (ignorant) — detects Instagram, Amazon, Snapchat
  2. Multi-format web OSINT with strict phone-number filtering
  3. DuckDuckGo HTML fallback when ddgs library fails
  4. India-focused people-search sites (Truecaller, Sync.me, Justdial, etc.)
  5. WhatsApp / Telegram direct checks
"""

from __future__ import annotations

import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None  # type: ignore

try:
    import httpx
    import trio
    from ignorant.modules.shopping.amazon import amazon
    from ignorant.modules.social_media.instagram import instagram
    from ignorant.modules.social_media.snapchat import snapchat

    IGNORANT_AVAILABLE = True
except ImportError:
    IGNORANT_AVAILABLE = False

from services.phone_intelligence.profile_resolver import resolve_all_profiles

SOCIAL_PROFILE_PATTERNS = (
    "facebook.com/",
    "instagram.com/",
    "twitter.com/",
    "x.com/",
    "linkedin.com/in/",
    "t.me/",
    "reddit.com/user/",
    "github.com/",
    "snapchat.com/add/",
)

# Platforms relevant for India / international CID OSINT
SOCIAL_PLATFORMS = {
    "whatsapp": {
        "label": "WhatsApp",
        "queries": ['"{num}" whatsapp', 'site:whatsapp.com "{num}"', '"{local}" whatsapp group'],
    },
    "facebook": {
        "label": "Facebook",
        "queries": ['site:facebook.com "{num}"', 'site:facebook.com "{local}"', 'site:m.facebook.com "{num}"'],
    },
    "instagram": {
        "label": "Instagram",
        "queries": ['site:instagram.com "{num}"', 'site:instagram.com "{local}"', '"{num}" instagram profile'],
    },
    "twitter": {
        "label": "Twitter / X",
        "queries": ['site:twitter.com "{num}"', 'site:x.com "{num}"', '"{num}" site:twitter.com'],
    },
    "linkedin": {
        "label": "LinkedIn",
        "queries": ['site:linkedin.com "{num}"', 'site:linkedin.com/in "{local}"', '"{num}" linkedin'],
    },
    "telegram": {
        "label": "Telegram",
        "queries": ['site:t.me "{num}"', '"{num}" telegram', 'site:telegram.me "{num}"'],
    },
    "truecaller": {
        "label": "Truecaller",
        "queries": ['site:truecaller.com "{num}"', 'site:truecaller.com "{local}"', '"{num}" truecaller india'],
    },
    "syncme": {
        "label": "Sync.me",
        "queries": ['site:sync.me "{num}"', 'site:sync.me "{local}"'],
    },
    "callapp": {
        "label": "CallApp",
        "queries": ['site:callapp.com "{num}"', '"{num}" callapp'],
    },
    "justdial": {
        "label": "Justdial (India business)",
        "queries": ['site:justdial.com "{num}"', 'site:justdial.com "{local}"'],
    },
    "olx": {
        "label": "OLX classifieds",
        "queries": ['site:olx.in "{num}"', 'site:olx.com "{num}"'],
    },
    "github": {
        "label": "GitHub",
        "queries": ['site:github.com "{num}"', '"{num}" site:github.com'],
    },
}

GENERIC_SKIP_DOMAINS = {
    "linkedin.com/login", "linkedin.com/help", "facebook.com/login",
    "instagram.com/accounts", "twitter.com/login", "google.com",
}


def parse_country_and_local(number_info: dict) -> tuple[str, str]:
    """Country code and local number for ignorant-style checks."""
    cc = str(number_info.get("countryCode", number_info.get("country_code", "")))
    raw = number_info.get("rawLocal", number_info.get("raw_local", ""))
    local = re.sub(r"\D", "", raw or "")
    if local.startswith("0"):
        local = local[1:]
    intl = re.sub(r"\D", "", number_info.get("international", ""))
    if intl.startswith(cc) and len(intl) > len(cc):
        local = local or intl[len(cc) :]
    return cc, local


def check_registered_accounts(country_code: str, local_phone: str) -> dict[str, Any]:
    """
    Check if phone is registered on Instagram, Amazon, Snapchat.
    Uses ignorant library — queries platform signup/login endpoints silently.
    """
    if not IGNORANT_AVAILABLE:
        return {
            "success": False,
            "error": "ignorant not installed — run: pip install ignorant",
            "platforms": [],
        }

    async def _run() -> list[dict]:
        client = httpx.AsyncClient(timeout=15)
        out: list[dict] = []
        try:
            await amazon(local_phone, country_code, client, out)
            await instagram(local_phone, country_code, client, out)
            await snapchat(local_phone, country_code, client, out)
        finally:
            await client.aclose()
        return out

    try:
        results = trio.run(_run)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc), "platforms": []}

    platforms = []
    linked = []
    for r in results:
        entry = {
            "platform": r.get("name", ""),
            "domain": r.get("domain", ""),
            "account_linked": r.get("exists") if not r.get("rateLimit") else None,
            "rate_limited": bool(r.get("rateLimit")),
            "method": r.get("method", ""),
            "confidence": "high" if r.get("exists") else ("unknown" if r.get("rateLimit") else "not_linked"),
        }
        platforms.append(entry)
        if r.get("exists"):
            linked.append({
                "platform": r.get("name", ""),
                "domain": r.get("domain", ""),
                "account_linked": True,
                "confidence": "high",
                "evidence": "Phone number registered on platform (registration endpoint check)",
                "profile_hint": f"https://www.{r.get('domain', '')}/",
            })

    return {
        "success": True,
        "technique": "platform_registration_check",
        "country_code": country_code,
        "local_phone": local_phone,
        "platforms": platforms,
        "linked_accounts": linked,
        "linked_count": len(linked),
    }


def ddg_html_search(query: str, max_results: int = 8) -> list[dict]:
    """Fallback search via DuckDuckGo HTML when ddgs library fails."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (CID-OSINT/1.0)"})
    try:
        html = urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    except (URLError, OSError):
        return []

    results = []
    for block in re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?class="result__snippet"[^>]*>([^<]*)',
        html,
        re.S,
    ):
        results.append({
            "title": block[1].strip(),
            "url": block[0],
            "snippet": re.sub(r"<[^>]+>", "", block[2]).strip(),
        })
        if len(results) >= max_results:
            break
    return results


def is_social_profile_url(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in SOCIAL_PROFILE_PATTERNS) and "login" not in u and "/help" not in u


def build_number_variants(international: str, local: str, e164: str, raw_local: str) -> list[str]:
    """All searchable formats of the phone number."""
    variants = set()
    for v in (international, local, e164, raw_local):
        if v:
            variants.add(v.strip())
            variants.add(v.replace(" ", "").replace("-", ""))
    if e164.startswith("+"):
        variants.add(e164[1:])
    digits = re.sub(r"\D", "", international or e164 or "")
    if digits:
        variants.add(digits)
        if len(digits) > 10:
            variants.add(digits[-10:])  # local 10-digit (India)
        if not digits.startswith("0") and len(digits) == 10:
            variants.add("0" + digits)
            variants.add("91" + digits)
            variants.add("+91" + digits)
    return [v for v in variants if len(re.sub(r"\D", "", v)) >= 8]


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def number_mentioned(text: str, variants: list[str]) -> bool:
    """True if any number variant appears in text."""
    if not text:
        return False
    text_digits = _digits(text)
    text_lower = text.lower()
    for v in variants:
        vd = _digits(v)
        if len(vd) >= 8 and vd in text_digits:
            return True
        if v.lower() in text_lower:
            return True
    return False


def confidence_score(title: str, snippet: str, url: str, variants: list[str]) -> str:
    combined = f"{title} {snippet} {url}"
    if not number_mentioned(combined, variants):
        return "none"
    vd_main = _digits(variants[0]) if variants else ""
    if vd_main and vd_main in _digits(url):
        return "high"
    if number_mentioned(title, variants) or number_mentioned(snippet, variants):
        return "high"
    if number_mentioned(url, variants):
        return "medium"
    return "low"


def is_generic_page(url: str, title: str) -> bool:
    url_l = url.lower()
    title_l = title.lower()
    for skip in GENERIC_SKIP_DOMAINS:
        if skip in url_l:
            return True
    generic_titles = ("login", "sign in", "sign up", "help center", "search for people")
    return any(g in title_l for g in generic_titles)


def check_whatsapp(international_digits: str) -> dict[str, Any]:
    """WhatsApp presence — generates profile link; checks page for invalid number."""
    phone = _digits(international_digits)
    result: dict[str, Any] = {
        "platform": "whatsapp",
        "profile_url": f"https://wa.me/{phone}",
        "api_url": f"https://api.whatsapp.com/send/?phone={phone}",
        "status": "unknown",
        "note": "Open profile_url to verify. WhatsApp does not expose owner name publicly.",
    }
    try:
        req = Request(
            f"https://api.whatsapp.com/send/?phone={phone}",
            headers={"User-Agent": "Mozilla/5.0 (CID-OSINT/1.0)"},
        )
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore").lower()
        if "invalid" in html and "phone" in html:
            result["status"] = "invalid_or_not_registered"
        elif "share on whatsapp" in html or "whatsapp" in html:
            result["status"] = "likely_registered"
    except (URLError, OSError) as exc:
        result["status"] = "check_failed"
        result["error"] = str(exc)
    return result


def check_telegram(international_digits: str) -> dict[str, Any]:
    phone = _digits(international_digits)
    return {
        "platform": "telegram",
        "status": "link_generated",
        "profile_url": f"tg://resolve?phone={phone}",
        "web_url": f"https://t.me/+{phone}",
        "note": "Telegram account lookup requires the user in your contacts or authorized Telegram API.",
    }


def run_social_query(query: str, variants: list[str], max_results: int = 8) -> list[dict]:
    hits: list[dict] = []

    if DDGS is not None:
        try:
            for h in DDGS().text(query, max_results=max_results):
                title = h.get("title", "")
                url = h.get("href", h.get("link", ""))
                snippet = h.get("body", h.get("snippet", ""))
                if is_generic_page(url, title):
                    continue
                conf = confidence_score(title, snippet, url, variants)
                if conf == "none" and not is_social_profile_url(url):
                    continue
                hits.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "confidence": conf if conf != "none" else "medium",
                    "query": query,
                    "source": "ddgs",
                })
            if hits:
                return hits
        except Exception:  # noqa: BLE001
            pass

    # Fallback: DuckDuckGo HTML scrape
    for h in ddg_html_search(query, max_results):
        title, url, snippet = h["title"], h["url"], h["snippet"]
        if is_generic_page(url, title):
            continue
        conf = confidence_score(title, snippet, url, variants)
        if conf == "none" and not is_social_profile_url(url):
            continue
        hits.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "confidence": conf if conf != "none" else "medium",
            "query": query,
            "source": "ddg_html",
        })
    return hits


def search_platform(platform_key: str, cfg: dict, variants: list[str], num: str, local: str) -> dict:
    queries = [q.format(num=num, local=local) for q in cfg["queries"]]
    all_hits: list[dict] = []
    seen_urls: set[str] = set()

    for q in queries:
        for hit in run_social_query(q, variants):
            if hit["url"] not in seen_urls:
                seen_urls.add(hit["url"])
                all_hits.append(hit)

    all_hits.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["confidence"], 3))

    status = "no_public_link_found"
    if all_hits:
        high = [h for h in all_hits if h["confidence"] == "high"]
        status = "linked" if high else "possible_match"

    return {
        "platform": platform_key,
        "label": cfg["label"],
        "status": status,
        "match_count": len(all_hits),
        "matches": all_hits,
    }


def lookup_social_accounts(number_info: dict, *, fast_only: bool = False) -> dict[str, Any]:
    """
    Run social OSINT for a parsed phone number dict from PhoneInfoga.
    fast_only=True: ignorant + WhatsApp/Telegram + profile resolver (no DDGS platform sweep).
    """
    international = number_info.get("international", "")
    local = number_info.get("rawLocal", number_info.get("raw_local", ""))
    e164 = number_info.get("e164", "")
    raw_local = number_info.get("rawLocal", number_info.get("raw_local", local))

    variants = build_number_variants(international, local, e164, raw_local)
    num = _digits(international) or _digits(e164)
    local10 = variants[-1] if variants else local

    country_code, local_phone = parse_country_and_local(number_info)

    # PRIMARY: platform registration check (Instagram, Amazon, Snapchat)
    registered = check_registered_accounts(country_code, local_phone)

    # Profile URLs + usernames (Instagram lookup API, Facebook recovery, etc.)
    if fast_only:
        import os
        prev = os.environ.get("SKIP_WEB_SEARCH")
        os.environ["SKIP_WEB_SEARCH"] = "1"
        try:
            profile_resolution = resolve_all_profiles(number_info)
        finally:
            if prev is None:
                os.environ.pop("SKIP_WEB_SEARCH", None)
            else:
                os.environ["SKIP_WEB_SEARCH"] = prev
    else:
        profile_resolution = resolve_all_profiles(number_info)

    platforms: dict[str, Any] = {}

    # Direct platform checks (fast)
    platforms["whatsapp"] = check_whatsapp(num)
    platforms["telegram"] = check_telegram(num)

    # OSINT search per platform (parallel) — skip instagram if ignorant already found it
    skip_search = {r["platform"] for r in registered.get("linked_accounts", [])}

    import os

    fast = fast_only or os.getenv("PHONE_OSINT_FAST", "true").lower() in ("1", "true", "yes")
    fast_keys = frozenset({
        "instagram", "facebook", "truecaller", "linkedin", "github", "justdial",
    })
    platform_items: list[tuple[str, dict]] = []
    if not fast_only:
        platform_items = [
            (key, cfg)
            for key, cfg in SOCIAL_PLATFORMS.items()
            if key not in ("whatsapp", "telegram") and key not in skip_search
            and (not fast or key in fast_keys)
        ]

    if platform_items:
        with ThreadPoolExecutor(max_workers=4 if fast else 6) as pool:
            futures = {
                pool.submit(search_platform, key, cfg, variants, num, local10): key
                for key, cfg in platform_items
            }
            for future in as_completed(futures):
                key = futures[future]
                platforms[key] = future.result()

    # Collect all confirmed matches
    confirmed: list[dict] = list(registered.get("linked_accounts", []))
    for pl in profile_resolution.get("profile_links", []):
        if pl.get("username") and pl.get("profile_url"):
            confirmed.append({
                "platform": pl["platform"],
                "username": pl["username"],
                "url": pl["profile_url"],
                "confidence": "high",
                "evidence": "Username resolved via platform lookup API",
            })
        elif pl.get("linked") is True and pl.get("profile_url"):
            confirmed.append({
                "platform": pl["platform"],
                "url": pl["profile_url"],
                "confidence": "medium",
                "evidence": pl.get("note", "Account linked; partial profile URL"),
            })
    for key, pdata in platforms.items():
        if key in ("whatsapp", "telegram"):
            if pdata.get("status") == "likely_registered":
                confirmed.append({
                    "platform": pdata["platform"],
                    "url": pdata.get("profile_url", ""),
                    "confidence": "medium",
                    "evidence": "WhatsApp accepts this number (likely registered)",
                })
            continue
        for m in pdata.get("matches", []):
            if m["confidence"] in ("high", "medium"):
                confirmed.append({
                    "platform": pdata["label"],
                    "url": m["url"],
                    "title": m.get("title", ""),
                    "snippet": m.get("snippet", ""),
                    "confidence": m["confidence"],
                    "evidence": "Phone number found in public web result",
                })

    linked = [c for c in confirmed if c.get("confidence") == "high"]
    possible = [c for c in confirmed if c.get("confidence") not in ("high",)]

    return {
        "summary": {
            "platforms_checked": len(SOCIAL_PLATFORMS) + 2 + len(registered.get("platforms", [])),
            "registered_accounts_found": registered.get("linked_count", 0),
            "profiles_with_url": profile_resolution["summary"]["profiles_with_url"],
            "usernames_found": profile_resolution["summary"]["usernames_found"],
            "confirmed_links": len(linked),
            "possible_links": len(possible),
            "whatsapp_registered": platforms.get("whatsapp", {}).get("status") == "likely_registered",
        },
        "registered_accounts": registered,
        "profile_links": profile_resolution["profile_links"],
        "profile_urls": profile_resolution["urls"],
        "usernames": profile_resolution["usernames"],
        "platforms": platforms,
        "confirmed_matches": linked,
        "possible_matches": possible,
        "number_variants_searched": variants,
        "limitations": (
            "profile_links attempts to resolve username/URL via Instagram lookup API and Facebook recovery. "
            "Instagram/Facebook often rate-limit automated requests — retry later if status is rate_limited. "
            "Snapchat/Amazon confirm registration but do NOT expose username from phone. "
            "For guaranteed username/profile ID use official Law Enforcement portals."
        ),
        "law_enforcement_portals": {
            "meta_facebook_instagram_whatsapp": "https://www.facebook.com/records",
            "google": "https://support.google.com/legal/contact/law?product=websearch",
            "twitter_x": "https://help.twitter.com/forms/lawenforcement",
            "telegram": "https://telegram.org/faq#q-there-is-illegal-content-on-telegram-how-do-i-take-it-down",
        },
    }
