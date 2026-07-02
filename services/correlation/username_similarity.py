"""Username similarity: cross-platform normalization + RapidFuzz."""

from __future__ import annotations

import re

from rapidfuzz.distance import JaroWinkler, Levenshtein
from rapidfuzz import fuzz

_SEP_RE = re.compile(r"[\s_.\-]+")


def normalize_handle_cross_platform(handle: str) -> str:
    """Collapse platform-specific separators: manoj-yadav-nr → manojyadavnr."""
    if not handle:
        return ""
    lowered = handle.lower().strip()
    if "@" in lowered:
        lowered = lowered.split("@", 1)[0]
    return re.sub(r"[^a-z0-9]", "", _SEP_RE.sub("", lowered))


def username_similarity(a: str, b: str) -> tuple[float, str]:
    if not a or not b:
        return 0.0, "missing handle"

    a_norm = a.lower().strip()
    b_norm = b.lower().strip()
    a_compact = normalize_handle_cross_platform(a)
    b_compact = normalize_handle_cross_platform(b)

    if a_norm == b_norm or (a_compact and a_compact == b_compact):
        return 1.0, "exact match (cross-platform normalized)" if a_norm != b_norm else "exact match"

    lev = Levenshtein.normalized_similarity(a_compact or a_norm, b_compact or b_norm)
    jw = JaroWinkler.normalized_similarity(a_compact or a_norm, b_compact or b_norm)
    partial = fuzz.partial_ratio(a_compact or a_norm, b_compact or b_norm) / 100.0
    token = fuzz.token_sort_ratio(a_norm, b_norm) / 100.0

    score = max(lev, jw, partial * 0.95, token * 0.9)
    if a_compact and b_compact and partial >= 0.88:
        score = max(score, partial)

    detail = (
        f"compact_a={a_compact}, compact_b={b_compact}, "
        f"levenshtein={lev:.3f}, jaro_winkler={jw:.3f}, "
        f"partial={partial:.3f}, token_sort={token:.3f}"
    )
    return round(min(score, 1.0), 4), detail
