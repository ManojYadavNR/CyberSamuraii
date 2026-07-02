"""Negative identity signals — penalize or block clearly different people."""

from __future__ import annotations

import re

from services.correlation.account_parser import AccountProfile
from services.correlation.text_similarity import text_similarity

TITLE_RE = re.compile(r"\b(dr\.?|doctor|prof\.?|professor|mr\.?|mrs\.?|ms\.?)\b", re.I)
ROLE_CONFLICTS: list[tuple[re.Pattern[str], re.Pattern[str], str]] = [
    (re.compile(r"\b(dr\.?|doctor|chief minister|cm\b|politician|minister)\b", re.I),
     re.compile(r"\b(developer|engineer|student|intern|mern|full[\s-]?stack)\b", re.I),
     "professional title conflict (medical/political vs technical)"),
    (re.compile(r"\b(teacher|professor|lecturer|sir\b)\b", re.I),
     re.compile(r"\b(developer|engineer|student|intern)\b", re.I),
     "education role vs technical role conflict"),
]

DISTANT_LOCATION_HINTS = (
    ("london", "bangalore"),
    ("delhi", "san francisco"),
    ("mumbai", "new york"),
    ("uk", "india"),
)


def _combined_bio_text(profile: AccountProfile) -> str:
    parts: list[str] = []
    if profile.bio:
        parts.append(profile.bio)
    meta = profile.metadata or {}
    for key in ("display_name", "organization", "organizations"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
        elif isinstance(val, list):
            parts.extend(str(v) for v in val if v)
    return " ".join(parts).lower()


def _title_tokens(text: str) -> set[str]:
    return {m.group(0).lower().rstrip(".") for m in TITLE_RE.finditer(text)}


def negative_signal_check(a: AccountProfile, b: AccountProfile) -> tuple[float, str, bool]:
    """
    Return (penalty 0-1, detail, block_link).
    block_link=True when identities are almost certainly different people.
    """
    text_a = _combined_bio_text(a)
    text_b = _combined_bio_text(b)
    if not text_a or not text_b:
        return 0.0, "", False

    penalties: list[float] = []
    reasons: list[str] = []

    for pat_a, pat_b, label in ROLE_CONFLICTS:
        if (pat_a.search(text_a) and pat_b.search(text_b)) or (pat_a.search(text_b) and pat_b.search(text_a)):
            penalties.append(0.55)
            reasons.append(label)

    titles_a = _title_tokens(text_a)
    titles_b = _title_tokens(text_b)
    if titles_a and titles_b and titles_a.isdisjoint(titles_b):
        if "dr" in titles_a or "doctor" in titles_a or "dr" in titles_b or "doctor" in titles_b:
            penalties.append(0.45)
            reasons.append("conflicting honorifics (Dr vs non-Dr)")

    if a.location and b.location:
        loc_a = a.location.lower()
        loc_b = b.location.lower()
        for left, right in DISTANT_LOCATION_HINTS:
            if (left in loc_a and right in loc_b) or (left in loc_b and right in loc_a):
                sim_score, _ = text_similarity(loc_a, loc_b)
                if sim_score < 0.35:
                    penalties.append(0.35)
                    reasons.append(f"distant locations ({a.location} vs {b.location})")

    t_score, _ = text_similarity(text_a, text_b)
    if t_score < 0.12 and a.handle and b.handle:
        from services.correlation.username_similarity import username_similarity

        u_score, _ = username_similarity(a.handle, b.handle)
        if u_score < 0.72:
            penalties.append(0.5)
            reasons.append("bios diverge strongly with weak username overlap")

    if not penalties:
        return 0.0, "", False

    penalty = min(0.85, max(penalties))
    block = penalty >= 0.55 and t_score < 0.2
    return round(penalty, 4), "; ".join(reasons), block
