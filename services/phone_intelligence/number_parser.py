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
