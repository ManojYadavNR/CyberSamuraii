"""Parse and normalize phone numbers without a PhoneInfoga API server."""

from __future__ import annotations

import os
import re
from typing import Any

try:
    import phonenumbers
    from phonenumbers import carrier, geocoder, timezone as pn_timezone
except ImportError:
    phonenumbers = None  # type: ignore


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _looks_like_indian_mobile(digits: str) -> bool:
    """10-digit Indian mobile (starts 6–9)."""
    d = _digits(digits)
    return len(d) == 10 and d[0] in "6789"


def coalesce_number_info(raw: str, api_info: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Prefer locally parsed Indian numbers when PhoneInfoga API mis-detects country
    (e.g. 9353227875 parsed as +93 Afghanistan instead of +91 India).
    """
    digits = _digits(raw)
    local_parsed = parse_phone_number(raw)

    if api_info and api_info.get("valid") is not False:
        cc = str(api_info.get("countryCode") or api_info.get("country_code") or "")
        local = _digits(api_info.get("rawLocal") or api_info.get("raw_local") or "")
        if cc == "91" and len(local) == 10:
            return api_info
        if _looks_like_indian_mobile(digits) and cc != "91" and local_parsed and str(local_parsed.get("countryCode")) == "91":
            merged = dict(local_parsed)
            merged["phoneinfoga_api"] = True
            merged["note"] = "Re-parsed as Indian (+91) — PhoneInfoga API country mismatch corrected"
            return merged
        if len(local) >= 8:
            return api_info

    return local_parsed or api_info


def parse_phone_number(raw: str, *, default_region: str | None = None) -> dict[str, Any] | None:
    """Build a PhoneInfoga-compatible number_info dict."""
    text = (raw or "").strip()
    if not text:
        return None

    if phonenumbers is None:
        digits = _digits(text)
        if len(digits) < 8:
            return None
        cc = digits[:-10] if len(digits) > 10 else ""
        local = digits[-10:] if len(digits) >= 10 else digits
        return {
            "raw": text,
            "valid": True,
            "international": f"+{digits}",
            "e164": f"+{digits}",
            "countryCode": cc,
            "country_code": cc,
            "rawLocal": local,
            "raw_local": local,
        }

    region = default_region or os.getenv("PHONE_DEFAULT_REGION", "IN")
    try:
        parsed = phonenumbers.parse(text, None if text.startswith("+") else region)
    except phonenumbers.NumberParseException:
        return None

    if not phonenumbers.is_possible_number(parsed):
        return None

    cc = str(parsed.country_code)
    national = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
    local_digits = _digits(national)
    if local_digits.startswith("0"):
        local_digits = local_digits[1:]

    return {
        "raw": text,
        "valid": phonenumbers.is_valid_number(parsed),
        "international": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
        "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
        "countryCode": cc,
        "country_code": cc,
        "rawLocal": local_digits,
        "raw_local": local_digits,
        "carrier": carrier.name_for_number(parsed, "en") or None,
        "location": geocoder.description_for_number(parsed, "en") or None,
        "timezones": list(pn_timezone.time_zones_for_number(parsed)),
    }
