"""Lightweight topic overlap for behavioral correlation (TF-IDF with bag-of-words fallback)."""

from __future__ import annotations

import math
import re
from collections import Counter

STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "will", "would", "could", "should", "may", "might", "must",
        "i", "me", "my", "we", "our", "you", "your", "he", "she", "it", "they", "them", "their",
        "this", "that", "these", "those", "as", "if", "then", "so", "than", "too", "very", "just",
        "about", "into", "over", "after", "before", "not", "no", "yes", "all", "can", "get",
    }
)

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]{1,}", re.I)


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    tokens: list[str] = []
    for match in TOKEN_RE.findall(text.lower()):
        if match in STOPWORDS or len(match) < 3:
            continue
        tokens.append(match)
    return tokens


def _counter_cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _tfidf_vectors(text_a: str, text_b: str) -> tuple[Counter[str], Counter[str]]:
    docs = [_tokenize(text_a), _tokenize(text_b)]
    if not docs[0] or not docs[1]:
        return Counter(), Counter()

    df: Counter[str] = Counter()
    for tokens in docs:
        for term in set(tokens):
            df[term] += 1

    vectors: list[Counter[str]] = []
    for tokens in docs:
        tf = Counter(tokens)
        total = max(sum(tf.values()), 1)
        vec: Counter[str] = Counter()
        for term, count in tf.items():
            idf = math.log(2 / (1 + df[term])) + 1.0
            vec[term] = (count / total) * idf
        vectors.append(vec)
    return vectors[0], vectors[1]


def topic_similarity(text_a: str, text_b: str) -> tuple[float, str]:
    """Topic overlap on post/activity text (MERN, hackathons, employers, etc.)."""
    if not text_a or not text_b:
        return 0.0, "missing topic text"

    a_norm = text_a.strip().lower()
    b_norm = text_b.strip().lower()
    if a_norm == b_norm:
        return 1.0, "exact topic corpus match"

    vec_a, vec_b = _tfidf_vectors(text_a, text_b)
    if vec_a and vec_b:
        score = _counter_cosine(vec_a, vec_b)
        if score > 0:
            shared = sorted(set(vec_a) & set(vec_b), key=lambda t: -(vec_a[t] + vec_b[t]))[:5]
            return round(min(score, 1.0), 4), f"tfidf={score:.3f}, shared={','.join(shared) or 'none'}"

    bag_a = Counter(_tokenize(text_a))
    bag_b = Counter(_tokenize(text_b))
    score = _counter_cosine(bag_a, bag_b)
    return round(min(score, 1.0), 4), f"bag_of_words={score:.3f}"
