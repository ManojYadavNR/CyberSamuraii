"""Location similarity for geo-tagged or profile location strings."""

from __future__ import annotations

from rapidfuzz import fuzz


def location_similarity(a: str | None, b: str | None) -> tuple[float, str]:
    if not a or not b:
        return 0.0, "missing location"

    a_n, b_n = a.strip().lower(), b.strip().lower()
    if a_n == b_n:
        return 1.0, "exact location match"

    token = fuzz.token_sort_ratio(a_n, b_n) / 100.0
    partial = fuzz.partial_ratio(a_n, b_n) / 100.0
    score = max(token, partial)

    if "," in a_n and "," in b_n:
        a_country = a_n.split(",")[-1].strip()
        b_country = b_n.split(",")[-1].strip()
        if a_country and a_country == b_country:
            score = max(score, 0.75)

    return round(min(score, 1.0), 4), f"token={token:.3f}, partial={partial:.3f}"
