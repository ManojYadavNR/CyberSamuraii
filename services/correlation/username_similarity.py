"""Username similarity: RapidFuzz Levenshtein + Jaro-Winkler."""

from __future__ import annotations

from rapidfuzz.distance import JaroWinkler, Levenshtein
from rapidfuzz import fuzz


def username_similarity(a: str, b: str) -> tuple[float, str]:
    if not a or not b:
        return 0.0, "missing handle"

    a_norm = a.lower().strip()
    b_norm = b.lower().strip()

    if a_norm == b_norm:
        return 1.0, "exact match"

    lev = Levenshtein.normalized_similarity(a_norm, b_norm)
    jw = JaroWinkler.normalized_similarity(a_norm, b_norm)
    partial = fuzz.partial_ratio(a_norm, b_norm) / 100.0
    token = fuzz.token_sort_ratio(a_norm, b_norm) / 100.0

    score = max(lev, jw, partial * 0.95, token * 0.9)

    detail = (
        f"levenshtein={lev:.3f}, jaro_winkler={jw:.3f}, "
        f"partial={partial:.3f}, token_sort={token:.3f}"
    )
    return round(min(score, 1.0), 4), detail
