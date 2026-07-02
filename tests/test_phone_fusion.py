"""Phone entity extraction and dork filtering."""

from services.fusion_engine import _extract_from_item
from services.google_dorking.filters import phone_dork_hit_displayable


def test_extract_phone_from_tool_row():
    entities = _extract_from_item(
        {"platform": "phone_search", "phone": "+919164873661", "url": "https://example.com"},
        "phoneinfoga",
        "+919164873661",
        "infra_intel",
    )
    assert any(e.type == "phone" and "+919164873661" in e.value for e in entities)


def test_phone_dork_rejects_tutorial_spam():
    assert not phone_dork_hit_displayable(
        url="https://googleguide.com/advanced_operators.html",
        title="Google Search Operators",
        snippet="intext examples with random digits 9008492390 listed",
        seed_query="+919164873661",
    )


def test_phone_dork_accepts_matching_listing():
    assert phone_dork_hit_displayable(
        url="https://smartphonetime.altervista.org/?num=919164873661",
        title="Phone lookup",
        snippet="Owner info for 919164873661",
        seed_query="+919164873661",
    )
