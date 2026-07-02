"""Behavioral similarity: posts, hashtags, activity windows, topics, emoji/style."""

from __future__ import annotations

import re
from collections import Counter

from services.correlation.topic_similarity import topic_similarity

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
    return Counter(EMOJI_RE.findall(text))


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


def _hashtag_overlap(tags_a: list[str], tags_b: list[str]) -> float:
    if not tags_a or not tags_b:
        return 0.0
    set_a = {t.lower() for t in tags_a}
    set_b = {t.lower() for t in tags_b}
    overlap = len(set_a & set_b)
    return overlap / max(len(set_a | set_b), 1)


def _activity_window_similarity(windows_a: list[str], windows_b: list[str]) -> float:
    if not windows_a or not windows_b:
        return 0.0
    set_a = set(windows_a)
    set_b = set(windows_b)
    overlap = len(set_a & set_b)
    return overlap / max(len(set_a | set_b), 1)


def _hour_slot_similarity(times_a: list[str], times_b: list[str]) -> float:
    """Bucket HH:00 slots into activity windows."""

    def slots_to_windows(times: list[str]) -> set[str]:
        windows: set[str] = set()
        for token in times:
            match = re.search(r"\b(\d{1,2}):\d{2}\b", token)
            if not match:
                continue
            hour = int(match.group(1)) % 24
            if 9 <= hour < 17:
                windows.add("business_hours")
            elif 17 <= hour < 22:
                windows.add("evening")
            else:
                windows.add("night_owl")
        return windows

    win_a = slots_to_windows(times_a)
    win_b = slots_to_windows(times_b)
    if not win_a or not win_b:
        return 0.0
    overlap = len(win_a & win_b)
    return overlap / max(len(win_a | win_b), 1)


def behavior_similarity(
    corpus_a: str,
    corpus_b: str,
    times_a: list[str] | None = None,
    times_b: list[str] | None = None,
    *,
    hashtags_a: list[str] | None = None,
    hashtags_b: list[str] | None = None,
    activity_windows_a: list[str] | None = None,
    activity_windows_b: list[str] | None = None,
) -> tuple[float, str]:
    """Score activity overlap — uses post/comment corpus, not bios."""
    times_a = times_a or []
    times_b = times_b or []
    hashtags_a = hashtags_a or []
    hashtags_b = hashtags_b or []
    activity_windows_a = activity_windows_a or []
    activity_windows_b = activity_windows_b or []

    if not corpus_a and not corpus_b and not times_a and not times_b and not hashtags_a and not hashtags_b:
        return 0.0, "missing behavioral data"

    scores: list[float] = []
    parts: list[str] = []

    if corpus_a and corpus_b:
        topic_score, topic_detail = topic_similarity(corpus_a, corpus_b)
        if topic_score > 0:
            scores.append(topic_score)
            parts.append(f"topic({topic_detail})")

        emoji_sim = _counter_cosine(_emoji_profile(corpus_a), _emoji_profile(corpus_b))
        if emoji_sim > 0:
            scores.append(emoji_sim)
            parts.append(f"emoji={emoji_sim:.3f}")

        feat_a = _style_features(corpus_a)
        feat_b = _style_features(corpus_b)
        if feat_a and feat_b:
            diffs = [abs(feat_a[k] - feat_b[k]) for k in feat_a if k in feat_b]
            style_sim = max(0.0, min(1.0 - (sum(diffs) / max(len(diffs), 1)), 1.0))
            scores.append(style_sim)
            parts.append(f"language_style={style_sim:.3f}")

    tag_sim = _hashtag_overlap(hashtags_a, hashtags_b)
    if tag_sim > 0:
        scores.append(tag_sim)
        parts.append(f"hashtags={tag_sim:.3f}")

    window_sim = _activity_window_similarity(activity_windows_a, activity_windows_b)
    if window_sim == 0:
        window_sim = _hour_slot_similarity(times_a, times_b)
    if window_sim > 0:
        scores.append(window_sim)
        label = "activity_window" if activity_windows_a or activity_windows_b else "posting_time"
        parts.append(f"{label}={window_sim:.3f}")

    if not scores:
        return 0.0, "insufficient behavioral overlap"

    return round(sum(scores) / len(scores), 4), ", ".join(parts)
