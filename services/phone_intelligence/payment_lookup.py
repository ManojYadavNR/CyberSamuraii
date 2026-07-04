"""
Payment / UPI OSINT for Indian phone numbers.

Techniques:
  1. Generate likely UPI VPAs (phone@paytm, phone@ybl, phone@okaxis, …)
  2. Validate VPAs via Razorpay validateVPA (RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET)
  3. Resolve full NPCI-registered name via PayU validateVPA (PAYU_KEY + PAYU_SALT)
  4. Web search for public PayPal / payment-app mentions
  5. Deep-link URLs for manual PhonePe / GPay / Paytm verification
"""

from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None  # type: ignore

# PSP handle → (display label, app key for deep links)
UPI_PSP_HANDLES: list[tuple[str, str, str]] = [
    ("paytm", "Paytm", "paytm"),
    ("ybl", "PhonePe", "phonepe"),
    ("ibl", "PhonePe", "phonepe"),
    ("axl", "PhonePe / Axis", "phonepe"),
    ("okaxis", "Google Pay", "google_pay"),
    ("okhdfcbank", "Google Pay", "google_pay"),
    ("okicici", "Google Pay", "google_pay"),
    ("oksbi", "Google Pay", "google_pay"),
    ("okbizaxis", "Google Pay Business", "google_pay"),
    ("upi", "BHIM UPI", "bhim"),
    ("apl", "Amazon Pay", "amazon_pay"),
    ("yapl", "Amazon Pay", "amazon_pay"),
    ("axisb", "Axis Bank", "axis"),
    ("icici", "ICICI Bank", "icici"),
    ("sbi", "SBI", "sbi"),
    ("pthdfc", "Paytm Payments Bank", "paytm"),
    ("postbank", "India Post Payments", "postbank"),
    ("abfspay", "Bajaj Finserv", "bajaj"),
    ("fbl", "Federal Bank", "federal"),
    ("yescred", "YES Bank", "yesbank"),
]

PAYMENT_WEB_QUERIES = (
    '{num} phonepe UPI',
    '{num} paytm UPI',
    'site:paypal.com "{num}"',
    '"{num}" google pay UPI',
    '"{num}" "@paytm" OR "@ybl" OR "@okaxis"',
)

UA = "Mozilla/5.0 (CID-OSINT/1.0; Phone Payment Intel)"


def _looks_like_indian_mobile(digits: str) -> bool:
    """10-digit Indian mobile (starts 6–9)."""
    d = re.sub(r"\D", "", digits or "")
    return len(d) == 10 and d[0] in "6789"


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _local_ten(number_info: dict[str, Any]) -> str | None:
    cc = str(number_info.get("countryCode") or number_info.get("country_code") or "")
    raw = _digits(number_info.get("rawLocal") or number_info.get("raw_local") or "")
    intl = _digits(number_info.get("international") or number_info.get("e164") or "")
    raw_input = _digits(number_info.get("raw") or "")

    if cc == "91" and len(raw) == 10:
        return raw
    if _looks_like_indian_mobile(raw_input):
        return raw_input[-10:]
    if cc and intl.startswith(cc) and len(intl) > len(cc):
        raw = raw or intl[len(cc):]
    if raw.startswith("0") and len(raw) > 10:
        raw = raw[1:]
    if len(raw) >= 10:
        return raw[-10:]
    if len(raw) == 10:
        return raw
    return None


def is_indian_mobile(number_info: dict[str, Any]) -> bool:
    cc = str(number_info.get("countryCode") or number_info.get("country_code") or "")
    if cc == "91":
        return True
    raw_input = _digits(number_info.get("raw") or "")
    if _looks_like_indian_mobile(raw_input):
        return True
    loc = str(number_info.get("location") or "").lower()
    return "india" in loc


def generate_vpa_candidates(local10: str) -> list[dict[str, Any]]:
    """Build likely UPI IDs from a 10-digit mobile number."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    prefixes = [local10]
    if not local10.startswith("91"):
        prefixes.append(f"91{local10}")

    for prefix in prefixes:
        for handle, label, app in UPI_PSP_HANDLES:
            vpa = f"{prefix}@{handle}"
            if vpa in seen:
                continue
            seen.add(vpa)
            out.append({
                "vpa": vpa,
                "psp_label": label,
                "app": app,
                "handle": handle,
                "status": "candidate",
                "deep_link": _upi_deep_link(vpa, app),
            })
    return out


def _upi_deep_link(vpa: str, app: str) -> str | None:
    encoded = urllib.parse.quote(vpa, safe="")
    if app == "phonepe":
        return f"phonepe://pay?pa={encoded}"
    if app == "google_pay":
        return f"tez://upi/pay?pa={encoded}"
    if app == "paytm":
        return f"paytmmp://pay?pa={encoded}"
    if app == "bhim":
        return f"upi://pay?pa={encoded}"
    return f"upi://pay?pa={encoded}"


def _razorpay_keys() -> tuple[str, str]:
    return (
        os.environ.get("RAZORPAY_KEY_ID", "").strip(),
        os.environ.get("RAZORPAY_KEY_SECRET", "").strip(),
    )


def _payu_keys() -> tuple[str, str]:
    return (
        os.environ.get("PAYU_KEY", os.environ.get("PAYU_MERCHANT_KEY", "")).strip(),
        os.environ.get("PAYU_SALT", os.environ.get("PAYU_MERCHANT_SALT", "")).strip(),
    )


def validate_vpa_razorpay(vpa: str) -> dict[str, Any]:
    """Razorpay validateVPA — returns masked customer_name when VPA exists."""
    key_id, key_secret = _razorpay_keys()
    if not key_id or not key_secret:
        return {"success": False, "skipped": True, "error": "RAZORPAY_KEY_ID/SECRET not configured"}
    if httpx is None:
        return {"success": False, "error": "httpx not installed"}

    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.post(
                "https://api.razorpay.com/v1/payments/validate/vpa",
                auth=(key_id, key_secret),
                json={"vpa": vpa},
            )
        if resp.status_code == 429:
            return {"success": False, "rate_limited": True, "error": "Razorpay rate limit"}
        data = resp.json() if resp.content else {}
        if resp.status_code == 200 and data.get("success"):
            return {
                "success": True,
                "exists": True,
                "vpa": data.get("vpa") or vpa,
                "customer_name": data.get("customer_name"),
                "provider": "razorpay",
            }
        return {
            "success": True,
            "exists": False,
            "vpa": vpa,
            "provider": "razorpay",
            "note": data.get("error", {}).get("description") if isinstance(data.get("error"), dict) else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


def validate_vpa_payu(vpa: str) -> dict[str, Any]:
    """PayU validateVPA — often returns full NPCI-registered account holder name."""
    key, salt = _payu_keys()
    if not key or not salt:
        return {"success": False, "skipped": True, "error": "PAYU_KEY/SALT not configured"}
    if httpx is None:
        return {"success": False, "error": "httpx not installed"}

    hash_str = hashlib.sha512(f"{key}|validateVPA|{vpa}|{salt}".encode()).hexdigest()
    payload = {
        "key": key,
        "command": "validateVPA",
        "var1": vpa,
        "hash": hash_str,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://info.payu.in/merchant/postservice?form=2",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        data = resp.json() if resp.content else {}
        if isinstance(data, dict) and str(data.get("status")).lower() in ("success", "1", "true"):
            name = data.get("name") or data.get("vpaName") or data.get("payerAccountName")
            return {
                "success": True,
                "exists": True,
                "vpa": vpa,
                "customer_name": name,
                "bank": data.get("bank") or data.get("ifsc"),
                "provider": "payu",
            }
        return {"success": True, "exists": False, "vpa": vpa, "provider": "payu"}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


def _validate_one_vpa(candidate: dict[str, Any]) -> dict[str, Any]:
    vpa = str(candidate["vpa"])
    row = dict(candidate)
    rz = validate_vpa_razorpay(vpa)
    pu = validate_vpa_payu(vpa)

    exists = bool(rz.get("exists") or pu.get("exists"))
    if exists:
        row["status"] = "verified"
        row["verified"] = True
        row["customer_name"] = pu.get("customer_name") or rz.get("customer_name")
        row["name_source"] = "payu" if pu.get("customer_name") else ("razorpay" if rz.get("customer_name") else None)
        row["bank"] = pu.get("bank")
    elif rz.get("skipped") and pu.get("skipped"):
        row["status"] = "candidate"
        row["verified"] = False
    else:
        row["status"] = "not_found"
        row["verified"] = False

    row["razorpay"] = {k: v for k, v in rz.items() if k not in ("success",)}
    row["payu"] = {k: v for k, v in pu.items() if k not in ("success",)}
    return row


def verify_vpa_candidates(candidates: list[dict[str, Any]], *, max_checks: int | None = None) -> list[dict[str, Any]]:
    """Parallel VPA validation when Razorpay/PayU keys are configured."""
    key_id, key_secret = _razorpay_keys()
    payu_key, payu_salt = _payu_keys()
    if not ((key_id and key_secret) or (payu_key and payu_salt)):
        return candidates

    limit = max_checks or int(os.environ.get("UPI_VPA_MAX_CHECKS", "18"))
    to_check = candidates[:limit]
    verified: list[dict[str, Any]] = []

    workers = min(6, max(2, len(to_check) // 3 or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_validate_one_vpa, c): c for c in to_check}
        for future in as_completed(futures):
            try:
                verified.append(future.result())
            except Exception as exc:  # noqa: BLE001
                base = dict(futures[future])
                base["status"] = "error"
                base["error"] = str(exc)
                verified.append(base)

    seen = {v["vpa"] for v in verified}
    for c in candidates:
        if c["vpa"] not in seen:
            verified.append(c)
    return verified


def _ddg_html_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    try:
        if httpx is None:
            return []
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            html = client.get(url, headers={"User-Agent": UA}).text
    except Exception:
        return []

    hits: list[dict[str, str]] = []
    for link, title in re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
        html,
    ):
        hits.append({"title": title.strip(), "url": link})
        if len(hits) >= max_results:
            break
    return hits


def _web_search_payment_mentions(local10: str, variants: list[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    queries = [q.format(num=v) for q in PAYMENT_WEB_QUERIES for v in variants[:4]]

    def _run_query(q: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if DDGS is not None:
            try:
                for h in DDGS().text(q, max_results=4):
                    url = h.get("href", h.get("link", ""))
                    title = h.get("title", "")
                    snippet = h.get("body", h.get("snippet", ""))
                    blob = f"{title} {snippet} {url}"
                    if not any(v in _digits(blob) or v in blob for v in variants if len(v) >= 8):
                        continue
                    found.append({
                        "platform": _platform_from_url(url),
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "query": q,
                        "source": "ddgs",
                    })
                if found:
                    return found
            except Exception:
                pass
        for h in _ddg_html_search(q, max_results=4):
            blob = f"{h['title']} {h['url']}"
            if any(v in _digits(blob) or v in blob for v in variants if len(v) >= 8):
                found.append({
                    "platform": _platform_from_url(h["url"]),
                    "title": h["title"],
                    "url": h["url"],
                    "query": q,
                    "source": "ddg_html",
                })
        return found

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(_run_query, q) for q in queries[:8]]
        for fut in as_completed(futs):
            try:
                for hit in fut.result():
                    if hit["url"] in seen_urls:
                        continue
                    seen_urls.add(hit["url"])
                    hits.append(hit)
            except Exception:
                pass
    return hits


def _platform_from_url(url: str) -> str:
    low = url.lower()
    if "paypal.com" in low:
        return "paypal"
    if "phonepe.com" in low:
        return "phonepe"
    if "paytm.com" in low:
        return "paytm"
    if "google.com" in low or "gpay" in low:
        return "google_pay"
    return "payment_web"


def lookup_payment_intel(number_info: dict[str, Any]) -> dict[str, Any]:
    """
    Payment / UPI intelligence for a parsed phone number.
    Returns verified VPAs (when keys configured), candidates, and web mentions.
    """
    local10 = _local_ten(number_info)
    if not local10:
        return {
            "success": False,
            "error": "Could not derive a 10-digit mobile number for UPI lookup",
            "applicable": False,
        }

    if not is_indian_mobile(number_info):
        return {
            "success": True,
            "applicable": False,
            "note": "UPI / PhonePe / Paytm lookup is optimized for Indian (+91) numbers",
            "paypal_web": _web_search_payment_mentions(local10, [local10, f"91{local10}", f"+91{local10}"]),
        }

    variants = list(dict.fromkeys([
        local10,
        f"91{local10}",
        f"+91{local10}",
        _digits(number_info.get("e164") or ""),
        _digits(number_info.get("international") or ""),
    ]))
    variants = [v for v in variants if v]

    candidates = generate_vpa_candidates(local10)
    checked = verify_vpa_candidates(candidates)
    verified = [c for c in checked if c.get("verified")]
    likely = [c for c in checked if c.get("status") == "candidate"][:12]

    web_hits = _web_search_payment_mentions(local10, variants)
    paypal_hits = [h for h in web_hits if h.get("platform") == "paypal"]

    names = list(dict.fromkeys(
        str(v["customer_name"]).strip()
        for v in verified
        if v.get("customer_name") and str(v["customer_name"]).strip()
    ))

    key_id, key_secret = _razorpay_keys()
    payu_key, payu_salt = _payu_keys()
    keys_configured = bool((key_id and key_secret) or (payu_key and payu_salt))

    return {
        "success": True,
        "applicable": True,
        "local_number": local10,
        "e164": number_info.get("e164") or f"+91{local10}",
        "verified_vpas": verified,
        "candidate_vpas": likely if not verified else [c for c in likely if not c.get("verified")][:6],
        "all_candidates_count": len(candidates),
        "registered_names": names,
        "primary_name": names[0] if names else None,
        "web_mentions": web_hits[:15],
        "paypal_mentions": paypal_hits[:5],
        "summary": {
            "verified_upi_count": len(verified),
            "candidate_upi_count": len(likely),
            "names_found": len(names),
            "paypal_hits": len(paypal_hits),
            "web_hits": len(web_hits),
            "keys_configured": keys_configured,
        },
        "configuration": {
            "razorpay_configured": bool(key_id and key_secret),
            "payu_configured": bool(payu_key and payu_salt),
            "setup_note": (
                "Add RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET and/or PAYU_KEY + PAYU_SALT to .env "
                "or phoneNumber/phoneinfoga/.env to resolve UPI IDs and bank-registered names from a phone number."
            ),
        },
        "limitations": (
            "Without Razorpay/PayU merchant keys, the system lists likely UPI handles (phone@paytm, phone@ybl, …) "
            "but cannot confirm them or fetch the NPCI account holder name. PayPal has no public phone→username API; "
            "only public web mentions are searched."
        ),
    }
