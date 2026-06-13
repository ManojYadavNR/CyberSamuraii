"""Text similarity via SentenceTransformers with RapidFuzz fallback."""

from __future__ import annotations

from functools import lru_cache

from rapidfuzz import fuzz

_MODEL = None
_MODEL_AVAILABLE: bool | None = None


@lru_cache(maxsize=1)
def _load_model():
    global _MODEL_AVAILABLE
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        model = SentenceTransformer("all-MiniLM-L6-v2")
        _MODEL_AVAILABLE = True
        return model, np
    except Exception:
        _MODEL_AVAILABLE = False
        return None, None


def sentence_transformers_available() -> bool:
    _load_model()
    return bool(_MODEL_AVAILABLE)


def text_similarity(a: str, b: str) -> tuple[float, str]:
    if not a or not b:
        return 0.0, "missing text"

    a_s, b_s = a.strip(), b.strip()
    if a_s.lower() == b_s.lower():
        return 1.0, "exact text match"

    model, np = _load_model()
    if model is not None and np is not None:
        try:
            embeddings = model.encode([a_s, b_s], normalize_embeddings=True)
            cosine = float(np.dot(embeddings[0], embeddings[1]))
            return round(max(cosine, 0.0), 4), f"sentence_transformer_cosine={cosine:.3f}"
        except Exception as exc:
            pass

    token = fuzz.token_sort_ratio(a_s, b_s) / 100.0
    partial = fuzz.partial_ratio(a_s, b_s) / 100.0
    score = max(token, partial * 0.9)
    return round(score, 4), f"fallback_token_sort={token:.3f}, partial={partial:.3f}"
