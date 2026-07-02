"""Phone validation — reject dates and CDN URL numeric fragments."""

from services.discovery.attribution import extract_phones_from_text
from services.discovery.validators import is_plausible_phone


def test_rejects_iso_dates():
    assert not is_plausible_phone("2024-02-24")
    assert extract_phones_from_text("created_at 2024-02-24 followers") == []


def test_rejects_cdn_numeric_fragments():
    blob = "17662454_275397716248930_6453253504008978432 51.2885-19"
    assert extract_phones_from_text(blob) == []


def test_accepts_real_phone_formats():
    assert is_plausible_phone("+1 (555) 123-4567")
    assert is_plausible_phone("555-123-4567")
