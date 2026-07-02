"""Heuristic linguistic analyzers — offline, no extra ML dependencies."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from schemas.linguistic import (
    CrossTextLink,
    LanguageProfile,
    NamedEntity,
    TextArtifact,
    TopicSignal,
    WritingStyleFingerprint,
)

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]+")
_LATIN_WORD_RE = re.compile(r"[a-zA-Z]{2,}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
_HANDLE_RE = re.compile(r"@[a-zA-Z0-9_]{2,32}")
_HASHTAG_RE = re.compile(r"#[\w\u0900-\u097f]+")

_HINGLISH_MARKERS = frozenset({
    "hai", "hain", "kya", "nahi", "mera", "tum", "aap", "ka", "ki", "ke",
    "mein", "aur", "bhi", "yeh", "woh", "karo", "batao",
})

_TOPIC_LEXICON: dict[str, tuple[str, ...]] = {
    "education": ("college", "university", "school", "campus", "student", "degree", "कॉलेज", "विश्वविद्यालय"),
    "technology": ("developer", "github", "software", "engineer", "coding", "python", "java", "tech", "hackathon"),
    "social_media": ("instagram", "facebook", "follower", "post", "reel", "story", "like", "share"),
    "professional": ("linkedin", "resume", "job", "work", "company", "founder", "ceo", "manager"),
    "location": ("city", "india", "delhi", "mumbai", "bangalore", "location", "based in", "lives in"),
    "identity": ("bio", "profile", "username", "handle", "alias", "name"),
}

_POSITIVE = frozenset({"love", "great", "happy", "thanks", "awesome", "good", "best", "win", "success", "proud"})
_NEGATIVE = frozenset({"hate", "angry", "bad", "worst", "kill", "fraud", "scam", "threat", "violence", "abuse"})

_THREAT_PHRASES = (
    "kill you", "bomb", "terror", "extremist", "weapon", "attack plan",
    "scam", "fraud ring", "money laundering",
)


def detect_language(text: str) -> str:
    if not text:
        return "unknown"
    deva = len(_DEVANAGARI_RE.findall(text))
    latin_words = _LATIN_WORD_RE.findall(text.lower())
    hinglish_hits = sum(1 for w in latin_words if w in _HINGLISH_MARKERS)
    if deva >= 3 and latin_words:
        return "hinglish"
    if deva >= 3:
        return "hi"
    if hinglish_hits >= 2:
        return "hinglish"
    if latin_words:
        return "en"
    return "unknown"


def build_language_profile(artifacts: list[TextArtifact]) -> LanguageProfile:
    counts: Counter[str] = Counter()
    scripts = {"devanagari": 0, "latin": 0}
    for art in artifacts:
        lang = detect_language(art.text)
        counts[lang] += max(1, art.char_count // 50)
        scripts["devanagari"] += len(_DEVANAGARI_RE.findall(art.text))
        scripts["latin"] += len(_LATIN_WORD_RE.findall(art.text))
    total = sum(counts.values()) or 1
    dist = {k: round(v / total, 3) for k, v in counts.items()}
    primary = counts.most_common(1)[0][0] if counts else "unknown"
    return LanguageProfile(primary=primary, distribution=dist, scripts=scripts)


def extract_named_entities(artifacts: list[TextArtifact]) -> list[NamedEntity]:
    entities: list[NamedEntity] = []
    seen: set[tuple[str, str]] = set()

    def add(text: str, kind: str, ref: str, conf: float = 0.85) -> None:
        key = (kind, text.lower())
        if key in seen:
            return
        seen.add(key)
        entities.append(NamedEntity(text=text, kind=kind, source_ref=ref, confidence=conf))

    for art in artifacts:
        ref = art.source_ref or art.source_tool
        for m in _EMAIL_RE.findall(art.text):
            add(m, "email", ref)
        for m in _URL_RE.findall(art.text):
            if "{" not in m:
                add(m, "url", ref)
        for m in _PHONE_RE.findall(art.text):
            add(m.strip(), "phone", ref, 0.7)
        for m in _HANDLE_RE.findall(art.text):
            add(m, "handle", ref)
        for m in _HASHTAG_RE.findall(art.text):
            add(m, "hashtag", ref, 0.75)
    return entities[:80]


def extract_topics(artifacts: list[TextArtifact]) -> list[TopicSignal]:
    blob = " ".join(a.text.lower() for a in artifacts)
    signals: list[TopicSignal] = []
    for topic, keywords in _TOPIC_LEXICON.items():
        hits = [kw for kw in keywords if kw in blob]
        if not hits:
            continue
        score = min(1.0, len(hits) / max(3, len(keywords) * 0.35))
        snippets: list[str] = []
        for art in artifacts:
            lower = art.text.lower()
            if any(kw in lower for kw in hits):
                snippets.append(art.text[:160])
            if len(snippets) >= 3:
                break
        signals.append(TopicSignal(topic=topic, score=round(score, 3), evidence_snippets=snippets))
    signals.sort(key=lambda x: -x.score)
    return signals[:12]


def sentiment_overview(artifacts: list[TextArtifact]) -> dict[str, Any]:
    pos = neg = neu = 0
    for art in artifacts:
        words = set(_LATIN_WORD_RE.findall(art.text.lower()))
        if words & _POSITIVE:
            pos += 1
        elif words & _NEGATIVE:
            neg += 1
        else:
            neu += 1
    total = max(1, pos + neg + neu)
    return {
        "positive_artifacts": pos,
        "negative_artifacts": neg,
        "neutral_artifacts": neu,
        "positive_ratio": round(pos / total, 3),
        "negative_ratio": round(neg / total, 3),
    }


def style_fingerprint(source_key: str, texts: list[str]) -> WritingStyleFingerprint:
    combined = " ".join(texts)
    words = _LATIN_WORD_RE.findall(combined)
    if not words:
        return WritingStyleFingerprint(source_key=source_key)
    unique = set(w.lower() for w in words)
    hashtags = len(_HASHTAG_RE.findall(combined))
    emoji = len(re.findall(r"[\U0001F300-\U0001FAFF]", combined))
    excl = combined.count("!")
    return WritingStyleFingerprint(
        source_key=source_key,
        avg_word_length=round(sum(len(w) for w in words) / len(words), 2),
        vocabulary_richness=round(len(unique) / len(words), 3),
        hashtag_rate=round(hashtags / max(1, len(words)), 4),
        emoji_rate=round(emoji / max(1, len(words)), 4),
        exclamation_rate=round(excl / max(1, len(words)), 4),
    )


def build_style_fingerprints(artifacts: list[TextArtifact]) -> list[WritingStyleFingerprint]:
    buckets: dict[str, list[str]] = {}
    for art in artifacts:
        key = f"{art.source_tool}:{art.source_platform or 'general'}"
        buckets.setdefault(key, []).append(art.text)
    return [style_fingerprint(k, v) for k, v in list(buckets.items())[:15]]


def _token_set(text: str) -> set[str]:
    return set(w.lower() for w in _LATIN_WORD_RE.findall(text) if len(w) > 3)


def cross_text_links(artifacts: list[TextArtifact]) -> list[CrossTextLink]:
    links: list[CrossTextLink] = []
    for i, a in enumerate(artifacts):
        ta = _token_set(a.text)
        if len(ta) < 4:
            continue
        for b in artifacts[i + 1 : i + 12]:
            tb = _token_set(b.text)
            shared = ta & tb
            if len(shared) < 3:
                continue
            sample = ", ".join(sorted(shared)[:5])
            links.append(
                CrossTextLink(
                    kind="shared_phrase",
                    sources=[a.source_ref or a.source_tool, b.source_ref or b.source_tool],
                    detail=f"Shared terms: {sample}",
                    score=round(min(1.0, len(shared) / 8), 3),
                )
            )
    links.sort(key=lambda x: -x.score)
    return links[:20]


def find_contradictions(artifacts: list[TextArtifact]) -> list[dict[str, str]]:
    locations: list[tuple[str, str]] = []
    names: list[tuple[str, str]] = []
    loc_re = re.compile(r"\b(?:based in|lives in|from|located in|city[:\s]+)\s*([A-Za-z\u0900-\u097f\s]{3,40})", re.I)
    for art in artifacts:
        ref = art.source_ref or art.source_tool
        for m in loc_re.findall(art.text):
            locations.append((m.strip().lower(), ref))
        if art.source_ref and "name" in art.source_ref.lower():
            names.append((art.text[:80], ref))

    contradictions: list[dict[str, str]] = []
    loc_set = {loc for loc, _ in locations}
    if len(loc_set) >= 2:
        contradictions.append({
            "type": "location_mismatch",
            "detail": f"Multiple locations mentioned: {', '.join(sorted(loc_set)[:5])}",
        })
    name_set = {n.lower() for n, _ in names}
    if len(name_set) >= 2:
        contradictions.append({
            "type": "name_variant",
            "detail": f"Multiple display names: {', '.join(sorted(name_set)[:5])}",
        })
    return contradictions


def threat_flags(artifacts: list[TextArtifact]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for art in artifacts:
        lower = art.text.lower()
        for phrase in _THREAT_PHRASES:
            if phrase in lower:
                flags.append({
                    "phrase": phrase,
                    "source_ref": art.source_ref or art.source_tool,
                    "confidence": 0.55,
                    "note": "Lexicon match only — requires human review",
                })
    return flags[:10]


def top_keywords(artifacts: list[TextArtifact], *, limit: int = 25) -> list[str]:
    stop = _HINGLISH_MARKERS | {
        "the", "and", "for", "with", "this", "that", "from", "your", "have", "http", "https", "www",
    }
    counts: Counter[str] = Counter()
    for art in artifacts:
        for w in _LATIN_WORD_RE.findall(art.text.lower()):
            if len(w) > 3 and w not in stop:
                counts[w] += 1
        for w in _DEVANAGARI_RE.findall(art.text):
            if len(w) > 2:
                counts[w] += 1
    return [w for w, _ in counts.most_common(limit)]


def cosine_similarity_styles(a: WritingStyleFingerprint, b: WritingStyleFingerprint) -> float:
    va = [a.avg_word_length, a.vocabulary_richness, a.hashtag_rate, a.emoji_rate, a.exclamation_rate]
    vb = [b.avg_word_length, b.vocabulary_richness, b.hashtag_rate, b.emoji_rate, b.exclamation_rate]
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va)) or 1.0
    nb = math.sqrt(sum(x * x for x in vb)) or 1.0
    return round(dot / (na * nb), 3)
