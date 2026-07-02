"""
Resolve phone numbers to social profile URLs and usernames.

Techniques (layered):
  1. ignorant — silent registration check (Instagram, Amazon, Snapchat)
  2. Instagram users/lookup API — username + profile URL (needs clean IP or proxy)
  3. Instagram Bloks mobile search — fallback with device fingerprint
  4. Facebook recovery identify.php — partial profile URL
  5. Web OSINT — DuckDuckGo site: searches for public profile links

Set PROXY_URL in .env for residential/mobile proxy (required for production CID use).
  PROXY_URL=http://user:pass@host:port
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import urllib.parse
import uuid
from typing import Any

try:
    import httpx
    import trio
    from ignorant.modules.shopping.amazon import amazon
    from ignorant.modules.social_media.instagram import instagram as ig_exists_check
    from ignorant.modules.social_media.snapchat import snapchat

    DEPS_OK = True
except ImportError:
    DEPS_OK = False

IG_LOOKUP_URL = "https://i.instagram.com/api/v1/users/lookup/"
IG_BLOKS_URL = "https://i.instagram.com/api/v1/bloks/apps/com.bloks.www.caa.ar.search.async/"
IG_SIG_KEY = "e6358aeede676184b9fe702b30f4fd35e71744605e39d2181a34cede076b3c33"
IG_SIG_VERSION = "4"
IG_APP_ID = "567067343352427"
IG_UA = (
    "Instagram 359.2.0.0.0 Android (31/12; 420dpi; 1080x2400; samsung; SM-G991B; "
    "o1s; exynos2100; en_US; 664018448)"
)
UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


def _proxy() -> str | None:
    return os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY")


def _client(timeout: int = 25) -> httpx.Client:
    proxy = _proxy()
    kwargs: dict = {"timeout": timeout, "follow_redirects": True}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


def _ig_signed_body(phone_query: str) -> str:
    payload = json.dumps({
        "login_attempt_count": "0",
        "directly_sign_in": "true",
        "source": "default",
        "q": phone_query,
        "ig_sig_key_version": IG_SIG_VERSION,
    }, separators=(",", ":"))
    sig = hmac.new(IG_SIG_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"ig_sig_key_version={IG_SIG_VERSION}&signed_body={sig}.{urllib.parse.quote_plus(payload)}"


def _ig_mobile_headers(csrf: str = "") -> dict[str, str]:
    device_id = f"android-{hashlib.md5(b'cid-device').hexdigest()[:16]}"
    h = {
        "User-Agent": IG_UA,
        "X-IG-App-ID": IG_APP_ID,
        "X-IG-Android-ID": device_id,
        "X-IG-Device-ID": str(uuid.uuid4()),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept-Language": "en-US",
        "X-FB-HTTP-Engine": "Liger",
        "Connection": "close",
    }
    if csrf:
        h["X-CSRFToken"] = csrf
    return h


async def _ignorant_check(platform_fn, local: str, cc: str) -> dict | None:
    if not DEPS_OK:
        return None
    client = httpx.AsyncClient(timeout=20, proxy=_proxy())
    out: list[dict] = []
    try:
        await platform_fn(local, cc, client, out)
    finally:
        await client.aclose()
    return out[0] if out else None


def ignorant_platform_status(cc: str, local: str) -> dict[str, dict]:
    """Run ignorant checks for instagram, amazon, snapchat."""

    async def _run() -> dict[str, dict]:
        results = {}
        for name, fn in [("instagram", ig_exists_check), ("amazon", amazon), ("snapchat", snapchat)]:
            client = httpx.AsyncClient(timeout=20, proxy=_proxy())
            out: list[dict] = []
            try:
                await fn(local, cc, client, out)
            finally:
                await client.aclose()
            if out:
                r = out[0]
                results[name] = {
                    "exists": bool(r.get("exists")),
                    "rate_limited": bool(r.get("rateLimit")),
                }
        return results

    if not DEPS_OK:
        return {}
    try:
        return trio.run(_run)
    except Exception:  # noqa: BLE001
        return {}


def _parse_ig_user(data: dict, query: str) -> dict[str, Any]:
    if data.get("message") == "No users found":
        return {"platform": "instagram", "linked": False, "status": "not_linked", "username": None, "profile_url": None}
    if data.get("status") == "ok" and "user" in data:
        user = data["user"]
        username = user.get("username") or user.get("user_name")
        user_id = str(user.get("pk") or user.get("pk_id") or "")
        return {
            "platform": "instagram",
            "linked": True,
            "status": "resolved",
            "username": username,
            "user_id": user_id,
            "full_name": user.get("full_name"),
            "profile_url": f"https://www.instagram.com/{username}/" if username else None,
            "profile_pic_url": user.get("profile_pic_url"),
            "is_private": user.get("is_private"),
            "obfuscated_email": user.get("obfuscated_email"),
            "obfuscated_phone": user.get("obfuscated_phone"),
            "query_used": query,
        }
    return {}


def lookup_instagram_profile(country_code: str, local_phone: str, e164: str, ignorant: dict) -> dict[str, Any]:
    """Instagram — one careful lookup attempt; fall back to ignorant linked status."""
    query = f"+{country_code}{local_phone}"
    base_fail: dict[str, Any] = {
        "platform": "instagram",
        "username": None,
        "profile_url": None,
    }

    try:
        with _client() as client:
            r = client.get("https://www.instagram.com/", headers={"User-Agent": IG_UA})
            csrf = r.cookies.get("csrftoken", "")
            headers = _ig_mobile_headers(csrf)
            r2 = client.post(IG_LOOKUP_URL, headers=headers, data=_ig_signed_body(query))

        if r2.status_code == 200:
            parsed = _parse_ig_user(r2.json(), query)
            if parsed:
                return parsed

        data = r2.json() if r2.status_code != 429 else {}
        msg = data.get("message", "")

        if r2.status_code == 429 or "wait" in msg.lower():
            linked = ignorant.get("instagram", {}).get("exists", False)
            return {
                **base_fail,
                "linked": linked if linked else None,
                "status": "rate_limited",
                "account_exists_confirmed": linked,
                "note": (
                    "Instagram API rate-limited this IP. Account IS linked (confirmed). "
                    "Set PROXY_URL in .env (residential proxy) and retry for username. "
                    "Or use Meta Law Enforcement portal for profile ID."
                ),
                "retry": "Add PROXY_URL=http://user:pass@host:port to .env and restart server",
            }

        if ignorant.get("instagram", {}).get("exists"):
            return {**base_fail, "linked": True, "status": "linked_no_username", "account_exists_confirmed": True,
                    "note": "Account exists but username not returned. Try with PROXY_URL."}

        return {**base_fail, "linked": False, "status": "not_linked"}

    except Exception as exc:  # noqa: BLE001
        linked = ignorant.get("instagram", {}).get("exists", False)
        return {
            **base_fail,
            "linked": linked if linked else None,
            "status": "error",
            "error": str(exc),
            "account_exists_confirmed": linked,
        }


def web_search_profile_links(local: str, intl: str, platforms: list[str]) -> list[dict]:
    """DuckDuckGo HTML search for public profile URLs mentioning the phone (fast, 8s timeout)."""
    results: list[dict] = []
    patterns = {
        "instagram": "site:instagram.com",
        "facebook": "site:facebook.com",
        "twitter": "site:twitter.com OR site:x.com",
        "linkedin": "site:linkedin.com/in",
        "telegram": "site:t.me",
    }

    def _one_search(plat: str, q: str) -> list[dict]:
        site = patterns.get(plat, f"site:{plat}.com")
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
        try:
            with _client(timeout=8) as client:
                r = client.get(url, headers={"User-Agent": UA_DESKTOP})
                html = r.text
        except Exception:  # noqa: BLE001
            return []
        found = []
        for link, title in re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html):
            if plat in link.lower() and (local in html or intl in html):
                found.append({
                    "platform": plat,
                    "title": title.strip(),
                    "url": link,
                    "source": "web_search",
                    "confidence": "medium",
                })
        return found

    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout

    jobs = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for plat in platforms:
            site = patterns.get(plat, f"site:{plat}.com")
            for q in [f'"{local}" {site}', f'"{intl}" {site}']:
                jobs.append(pool.submit(_one_search, plat, q))
        try:
            for fut in as_completed(jobs, timeout=20):
                try:
                    results.extend(fut.result())
                except Exception:  # noqa: BLE001
                    pass
        except FuturesTimeout:
            pass
    # dedupe by url
    seen: set[str] = set()
    unique = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    return unique


def lookup_facebook_profile(phone_digits: str, e164: str) -> dict[str, Any]:
    candidates = [phone_digits, e164.lstrip("+"), local if (local := phone_digits[-10:]) else phone_digits]
    try:
        with _client() as client:
            for base in ("https://www.facebook.com", "https://m.facebook.com"):
                r = client.get(f"{base}/login/identify/?ctx=recover", headers={"User-Agent": UA_DESKTOP})
                lsd = None
                for pat in (r'\["LSD",\[\],\{"token":"([^"]+)"', r'"lsd":"([^"]+)"', r'name="lsd"\s+value="([^"]+)"'):
                    m = re.search(pat, r.text)
                    if m:
                        lsd = m.group(1)
                        break
                if not lsd:
                    continue
                for phone in dict.fromkeys(candidates):
                    data = {"lsd": lsd, "email": phone, "did_submit": "Search", "__a": "1", "__user": "0"}
                    headers = {"User-Agent": UA_DESKTOP, "X-FB-LSD": lsd, "Content-Type": "application/x-www-form-urlencoded"}
                    if r.cookies.get("datr"):
                        headers["Cookie"] = f"datr={r.cookies.get('datr')}"
                    r2 = client.post(f"{base}/ajax/login/help/identify.php?ctx=recover", data=data, headers=headers)
                    text = r2.text[9:] if r2.text.startswith("for (;;);") else r2.text
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    for script in payload.get("onload") or []:
                        if not isinstance(script, str):
                            continue
                        for m in re.finditer(r"(/recover/[^\\\"\']+)", script):
                            path = m.group(1).replace("\\", "")
                            return {
                                "platform": "facebook",
                                "linked": True,
                                "status": "partial",
                                "username": None,
                                "profile_url": f"https://www.facebook.com{path}",
                                "note": "Facebook recovery URL confirms linkage. Username requires Meta LE portal.",
                            }
    except Exception as exc:  # noqa: BLE001
        return {"platform": "facebook", "linked": None, "status": "error", "error": str(exc), "username": None, "profile_url": None}

    return {
        "platform": "facebook",
        "linked": None,
        "status": "blocked_or_no_token",
        "username": None,
        "profile_url": None,
        "note": "Facebook blocks automated recovery from datacenter IPs. Use PROXY_URL or Meta LE portal.",
    }


def lookup_snapchat_profile(country_code: str, local_phone: str, ignorant: dict) -> dict[str, Any]:
    ig = ignorant.get("snapchat", {})
    if ig.get("rate_limited"):
        return {"platform": "snapchat", "linked": None, "status": "rate_limited", "username": None, "profile_url": None,
                "note": "Snapchat rate-limited. Username not available via public API."}
    linked = ig.get("exists", False)
    return {
        "platform": "snapchat",
        "linked": linked,
        "status": "registered" if linked else "not_linked",
        "username": None,
        "profile_url": None,
        "note": "Snapchat does not expose username from phone via any public API.",
    }


def lookup_amazon_profile(ignorant: dict) -> dict[str, Any]:
    linked = ignorant.get("amazon", {}).get("exists", False)
    return {
        "platform": "amazon",
        "linked": linked,
        "status": "registered" if linked else "not_linked",
        "username": None,
        "profile_url": "https://www.amazon.in/" if linked else None,
        "note": (
            "Amazon account confirmed on this number."
            if linked
            else "No Amazon account linked to this number (ignorant check)."
        ),
    }


def lookup_twitter_profile(local: str, intl: str) -> dict[str, Any]:
    """Twitter/X — web search for public links; no public phone-to-username API."""
    links = web_search_profile_links(local, intl, ["twitter"])
    if links:
        best = links[0]
        return {
            "platform": "twitter",
            "linked": True,
            "status": "web_match",
            "username": None,
            "profile_url": best["url"],
            "note": "Found via public web search only.",
            "matches": links,
        }
    return {
        "platform": "twitter",
        "linked": None,
        "status": "no_public_api",
        "username": None,
        "profile_url": None,
        "note": "Twitter/X has no public phone-to-username API. Use LE portal for account ID.",
    }


def resolve_all_profiles(number_info: dict) -> dict[str, Any]:
    cc = str(number_info.get("countryCode", number_info.get("country_code", "")))
    raw = number_info.get("rawLocal", number_info.get("raw_local", ""))
    local = re.sub(r"\D", "", raw or "")
    if local.startswith("0"):
        local = local[1:]
    intl = re.sub(r"\D", "", number_info.get("international", ""))
    if intl.startswith(cc) and len(intl) > len(cc):
        local = local or intl[len(cc):]
    e164 = number_info.get("e164", f"+{cc}{local}")
    phone_digits = intl or f"{cc}{local}"

    ignorant = ignorant_platform_status(cc, local)

    instagram = lookup_instagram_profile(cc, local, e164, ignorant)
    facebook = lookup_facebook_profile(phone_digits, e164)
    snapchat = lookup_snapchat_profile(cc, local, ignorant)
    amazon = lookup_amazon_profile(ignorant)
    twitter = lookup_twitter_profile(local, phone_digits)

    web_links: list[dict] = []
    if os.environ.get("SKIP_WEB_SEARCH", "").lower() not in ("1", "true", "yes"):
        web_links = web_search_profile_links(local, phone_digits, ["instagram", "facebook", "linkedin"])

    profiles = [instagram, facebook, snapchat, amazon, twitter]
    for wl in web_links:
        profiles.append({
            "platform": wl["platform"],
            "linked": True,
            "status": "web_match",
            "username": _username_from_url(wl["url"]),
            "profile_url": wl["url"],
            "title": wl.get("title"),
            "source": "web_search",
            "confidence": wl.get("confidence", "medium"),
        })

    usernames = [p["username"] for p in profiles if p.get("username")]
    urls = [p["profile_url"] for p in profiles if p.get("profile_url")]

    return {
        "profile_links": profiles,
        "ignorant_status": ignorant,
        "web_discovered_links": web_links,
        "summary": {
            "total_checked": len(profiles),
            "accounts_linked": sum(1 for p in profiles if p.get("linked") is True),
            "profiles_with_url": len(urls),
            "usernames_found": len(usernames),
            "instagram_confirmed": ignorant.get("instagram", {}).get("exists", False),
            "proxy_configured": bool(_proxy()),
        },
        "usernames": usernames,
        "urls": urls,
    }


def _username_from_url(url: str) -> str | None:
    for pat in [
        r"instagram\.com/([^/?#]+)",
        r"facebook\.com/([^/?#]+)",
        r"twitter\.com/([^/?#]+)",
        r"x\.com/([^/?#]+)",
        r"linkedin\.com/in/([^/?#]+)",
    ]:
        m = re.search(pat, url, re.I)
        if m and m.group(1) not in ("p", "profile.php", "login", "help"):
            return m.group(1)
    return None
