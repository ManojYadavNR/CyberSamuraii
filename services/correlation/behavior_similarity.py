"""Behavioral similarity: emoji usage, language style, posting time patterns."""

from __future__ import annotations

import re
from collections import Counter

EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)


def _emoji_profile(text: str) -> Counter:
    emojis = EMOJI_RE.findall(text)
    return Counter(emojis)


def _style_features(text: str) -> dict[str, float]:
    if not text:
        return {}
    words = text.split()
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    exclam = text.count("!")
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
    return {
        "exclam_density": exclam / max(len(sentences), 1),
        "caps_ratio": caps_ratio,
        "avg_word_len": avg_word_len / 20.0,
    }


def _time_pattern_similarity(times_a: list[str], times_b: list[str]) -> float:
    if not times_a or not times_b:
        return 0.0
    set_a = {t.strip().lower() for t in times_a}
    set_b = {t.strip().lower() for t in times_b}
    if not set_a or not set_b:
        return 0.0
    overlap = len(set_a & set_b)
    return overlap / max(len(set_a | set_b), 1)


def _counter_cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    norm_a = sum(v * v for v in a.values()) ** 0.5
    norm_b = sum(v * v for v in b.values()) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def behavior_similarity(
    text_a: str,
    text_b: str,
    times_a: list[str] | None = None,
    times_b: list[str] | None = None,
) -> tuple[float, str]:
    if not text_a and not text_b and not times_a and not times_b:
        return 0.0, "missing behavioral data"

    scores: list[float] = []
    parts: list[str] = []

    if text_a and text_b:
        emoji_sim = _counter_cosine(_emoji_profile(text_a), _emoji_profile(text_b))
        scores.append(emoji_sim)
        parts.append(f"emoji={emoji_sim:.3f}")

        feat_a = _style_features(text_a)
        feat_b = _style_features(text_b)
        if feat_a and feat_b:
            diffs = [abs(feat_a[k] - feat_b[k]) for k in feat_a if k in feat_b]
            style_sim = 1.0 - (sum(diffs) / max(len(diffs), 1))
            style_sim = max(0.0, min(style_sim, 1.0))
            scores.append(style_sim)
            parts.append(f"language_style={style_sim:.3f}")

    time_sim = _time_pattern_similarity(times_a or [], times_b or [])
    if time_sim > 0:
        scores.append(time_sim)
        parts.append(f"posting_time={time_sim:.3f}")

    if not scores:
        return 0.0, "insufficient behavioral overlap"

    return round(sum(scores) / len(scores), 4), ", ".join(parts)
