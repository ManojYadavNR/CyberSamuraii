"""ML-backed linguistic analyzers — transformers + sentence-transformers."""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

import numpy as np

from schemas.linguistic import (
    ArtifactInsight,
    CrossTextLink,
    LanguageProfile,
    LinguisticAnalysisOutput,
    NamedEntity,
    SentimentScore,
    TextArtifact,
    TopicSignal,
    WritingStyleFingerprint,
)
from services.linguistic import analyzers
from services.linguistic.runtime import (
    EMBED_MODEL,
    fast_linguistic_mode,
    get_embedding_model,
    get_lang_pipeline,
    get_ner_pipeline,
    get_sentiment_pipeline,
    get_topic_pipeline,
    get_toxicity_pipeline,
    max_ml_artifacts,
    models_used,
    release_model,
    release_pipeline,
    should_release_after_step,
)

logger = logging.getLogger(__name__)

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]+")
_MAX_CHARS = 1800
_TOPIC_LABELS = (
    "education and academics",
    "technology and software development",
    "social media and content creation",
    "professional career and employment",
    "geographic location and travel",
    "personal identity and biography",
    "politics and activism",
    "finance and business",
    "gaming and entertainment",
    "sports and fitness",
    "cybercrime fraud and scams",
)

_NER_KIND = {
    "PER": "person",
    "ORG": "organization",
    "LOC": "location",
    "MISC": "misc",
    "person": "person",
    "organization": "organization",
    "location": "location",
}

_NER_JUNK = frozenset({
    "github", "instagram", "facebook", "twitter", "linkedin", "youtube", "reddit",
    "tiktok", "medium", "telegram", "discord", "pinterest", "twitch",
})


def _clip(text: str) -> str:
    t = (text or "").strip()
    return t[:_MAX_CHARS] if len(t) > _MAX_CHARS else t


def _refine_hinglish(text: str, lang: str) -> str:
    if lang in ("hi", "en") and _DEVANAGARI_RE.search(text) and re.search(r"[a-zA-Z]{2,}", text):
        return "hinglish"
    if lang == "en" and analyzers.detect_language(text) == "hinglish":
        return "hinglish"
    return lang


def _lang_code(raw: str) -> str:
    label = (raw or "").lower().replace("label_", "")
    if label in ("hi", "hin", "hindi"):
        return "hi"
    if label in ("en", "eng", "english"):
        return "en"
    if label in ("ur", "urd", "urdu"):
        return "ur"
    return label[:12] or "unknown"


def _best_lang_pred(preds: Any) -> str:
    if not isinstance(preds, list) or not preds:
        return "unknown"
    best = "unknown"
    best_score = -1.0
    for item in preds:
        if not isinstance(item, dict):
            continue
        score = float(item.get("score", 0))
        if score > best_score:
            best_score = score
            best = _lang_code(str(item.get("label", "")))
    return best


def _seed_variants(seed_query: str) -> set[str]:
    raw = (seed_query or "").strip()
    if not raw:
        return set()
    variants: set[str] = set()
    compact = re.sub(r"[^a-z0-9]", "", raw.lower())
    if compact:
        variants.add(compact)
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|\d+", raw)
    for part in parts:
        p = part.lower()
        if len(p) >= 2:
            variants.add(p)
    spaced = " ".join(parts).lower().strip()
    if spaced:
        variants.add(spaced)
        variants.add(spaced.replace(" ", ""))
    return variants


def _identity_match_score(text: str, variants: set[str]) -> float:
    if not text or not variants:
        return 0.0
    low = text.lower().strip()
    compact = re.sub(r"[^a-z0-9]", "", low)
    if compact in variants:
        return 1.0
    for v in variants:
        if len(v) >= 4 and v in compact:
            return 0.85
        if len(v) >= 4 and v in low:
            return 0.75
    return 0.0


def _is_ner_junk(word: str) -> bool:
    w = (word or "").strip()
    if len(w) < 2:
        return True
    if w.startswith("##"):
        return True
    if w.lower() in _NER_JUNK:
        return True
    return False


def _weighted_corpus_blob(artifacts: list[TextArtifact]) -> str:
    parts: list[str] = []
    for art in artifacts:
        ref = (art.source_ref or "").lower()
        weight = 3 if any(k in ref for k in ("bio", "caption", "about", "description", "summary")) else 1
        parts.extend([art.text] * weight)
    return " ".join(parts)


def _build_identity_signals(
    *,
    seed_query: str,
    artifacts: list[TextArtifact],
    entities: list[NamedEntity],
    keywords: list[str],
) -> list[dict[str, Any]]:
    variants = _seed_variants(seed_query)
    if not variants:
        return []
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(kind: str, text: str, score: float, source: str) -> None:
        key = f"{kind}:{text.lower()}"
        if key in seen or score < 0.5:
            return
        seen.add(key)
        signals.append({
            "kind": kind,
            "text": text,
            "score": round(score, 3),
            "source": source,
        })

    for ent in entities:
        if ent.kind in ("person", "organization"):
            score = _identity_match_score(ent.text, variants)
            if score >= 0.5:
                add("entity_match", ent.text, score, ent.source_ref or "ner")

    for art in artifacts:
        score = _identity_match_score(art.text, variants)
        if score >= 0.75:
            add("corpus_match", art.text[:120], score, art.source_ref or art.source_tool)

    for kw in keywords[:15]:
        score = _identity_match_score(str(kw), variants)
        if score >= 0.5:
            add("keyword_match", str(kw), score, "keybert")

    signals.sort(key=lambda x: -float(x.get("score", 0)))
    return signals[:12]


def detect_languages_ml(texts: list[str]) -> list[str]:
    if not texts:
        return []
    pipe = get_lang_pipeline()
    out: list[str] = []
    try:
        for text in texts:
            clipped = _clip(text)
            if len(clipped) < 8:
                out.append(analyzers.detect_language(clipped))
                continue
            try:
                preds = pipe(clipped)
                lang = _best_lang_pred(preds)
            except Exception:
                lang = analyzers.detect_language(clipped)
            out.append(_refine_hinglish(clipped, lang))
    finally:
        if should_release_after_step():
            release_pipeline("lang")
    return out


def sentiment_ml(texts: list[str]) -> list[SentimentScore | None]:
    if not texts:
        return []
    pipe = get_sentiment_pipeline()
    scores: list[SentimentScore | None] = []
    try:
        for text in texts:
            clipped = _clip(text)
            if len(clipped) < 6:
                scores.append(None)
                continue
            try:
                pred = pipe(clipped)[0]
                label = str(pred.get("label", "neutral")).lower()
                if "pos" in label:
                    label = "positive"
                elif "neg" in label:
                    label = "negative"
                else:
                    label = "neutral"
                scores.append(
                    SentimentScore(
                        label=label,
                        confidence=round(float(pred.get("score", 0.5)), 3),
                        model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
                    )
                )
            except Exception:
                scores.append(None)
    finally:
        if should_release_after_step():
            release_pipeline("sentiment")
    return scores


def ner_ml(texts: list[str], refs: list[str]) -> list[list[NamedEntity]]:
    pipe = get_ner_pipeline()
    all_entities: list[list[NamedEntity]] = []
    seen_global: set[tuple[str, str]] = set()

    try:
        for text, ref in zip(texts, refs):
            clipped = _clip(text)
            found: list[NamedEntity] = []
            if len(clipped) < 4:
                all_entities.append(found)
                continue
            try:
                spans = pipe(clipped)
                for span in spans or []:
                    if not isinstance(span, dict):
                        continue
                word = str(span.get("word", "")).strip()
                if _is_ner_junk(word):
                    continue
                    ent_group = str(span.get("entity_group") or span.get("entity") or "MISC")
                    kind = _NER_KIND.get(ent_group.upper(), ent_group.lower())
                    key = (kind, word.lower())
                    if key in seen_global:
                        continue
                    seen_global.add(key)
                    conf = float(span.get("score", 0.75))
                    found.append(
                        NamedEntity(
                            text=word,
                            kind=kind,
                            source_ref=ref,
                            confidence=round(conf, 3),
                        )
                    )
            except Exception as exc:
                logger.debug("NER failed for %s: %r", ref, exc)
            all_entities.append(found)
    finally:
        if should_release_after_step():
            release_pipeline("ner")
    return all_entities


def topics_ml(blob: str) -> list[TopicSignal]:
    clipped = _clip(blob)
    if len(clipped) < 20:
        return analyzers.extract_topics([TextArtifact(text=clipped)])
    try:
        pipe = get_topic_pipeline()
        try:
            pred = pipe(clipped, _TOPIC_LABELS, multi_label=True)
            labels = pred.get("labels") or []
            scores = pred.get("scores") or []
            signals: list[TopicSignal] = []
            for label, score in zip(labels, scores):
                if float(score) < 0.12:
                    continue
                topic_key = label.split(" and ")[0].replace(" ", "_")
                signals.append(
                    TopicSignal(
                        topic=topic_key,
                        score=round(float(score), 3),
                        evidence_snippets=[clipped[:200]],
                        model="MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
                    )
                )
            signals.sort(key=lambda x: -x.score)
            return signals[:12]
        finally:
            if should_release_after_step():
                release_pipeline("topics")
    except Exception as exc:
        logger.warning("ML topic classification failed: %r", exc)
        return analyzers.extract_topics([TextArtifact(text=clipped)])


def keywords_ml(blob: str, *, limit: int = 25, embed_model: Any | None = None) -> list[str]:
    clipped = _clip(blob)
    if len(clipped) < 30:
        return analyzers.top_keywords([TextArtifact(text=clipped)], limit=limit)
    own_model = embed_model is None
    try:
        from keybert import KeyBERT

        model = embed_model or get_embedding_model()
        kw = KeyBERT(model=model)
        pairs = kw.extract_keywords(
            clipped,
            keyphrase_ngram_range=(1, 2),
            stop_words="english",
            top_n=limit,
            use_mmr=True,
            diversity=0.4,
        )
        return [p[0] for p in pairs if p and p[0]]
    except Exception:
        return analyzers.top_keywords([TextArtifact(text=clipped)], limit=limit)
    finally:
        if own_model and should_release_after_step():
            release_model("embed")


def embedding_cross_links(
    artifacts: list[TextArtifact],
    *,
    embed_model: Any | None = None,
) -> list[CrossTextLink]:
    buckets: dict[str, str] = {}
    for art in artifacts:
        key = f"{art.source_tool}:{art.source_platform or 'general'}"
        buckets[key] = f"{buckets.get(key, '')} {art.text}".strip()

    keys = list(buckets.keys())
    if len(keys) < 2:
        return []

    own_model = embed_model is None
    try:
        model = embed_model or get_embedding_model()
        texts = [_clip(buckets[k]) for k in keys]
        vectors = model.encode(texts, normalize_embeddings=True)
        links: list[CrossTextLink] = []
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                sim = float(np.dot(vectors[i], vectors[j]))
                if sim < 0.62:
                    continue
                links.append(
                    CrossTextLink(
                        kind="semantic_similarity",
                        sources=[keys[i], keys[j]],
                        detail=f"Embedding similarity {sim:.2f} ({EMBED_MODEL})",
                        score=round(sim, 3),
                    )
                )
        links.sort(key=lambda x: -x.score)
        return links[:15]
    except Exception as exc:
        logger.warning("Embedding cross-links failed: %r", exc)
        return []
    finally:
        if own_model and should_release_after_step():
            release_model("embed")


def toxicity_flags_ml(artifacts: list[TextArtifact]) -> list[dict[str, Any]]:
    pipe = get_toxicity_pipeline()
    flags: list[dict[str, Any]] = []
    try:
        for art in artifacts:
            clipped = _clip(art.text)
            if len(clipped) < 12:
                continue
            try:
                preds = pipe(clipped)
                toxic_score = 0.0
                toxic_label = ""
                for pred in preds or []:
                    label = str(pred.get("label", "")).lower()
                    score = float(pred.get("score", 0))
                    if label == "toxic" and score > toxic_score:
                        toxic_score = score
                        toxic_label = label
                if toxic_score >= 0.72:
                    flags.append({
                        "phrase": clipped[:120],
                        "source_ref": art.source_ref or art.source_tool,
                        "confidence": round(toxic_score, 3),
                        "model": "unitary/toxic-bert",
                        "note": "ML toxicity signal — requires human review",
                    })
            except Exception:
                continue
    finally:
        if should_release_after_step():
            release_pipeline("toxicity")
    return flags[:10]


def contradictions_from_ner(entities: list[NamedEntity]) -> list[dict[str, str]]:
    locs = {e.text.lower().strip() for e in entities if e.kind == "location" and len(e.text) > 2}
    persons = {e.text.lower().strip() for e in entities if e.kind == "person" and len(e.text) > 2}
    orgs = {e.text.lower().strip() for e in entities if e.kind == "organization" and len(e.text) > 2}
    out: list[dict[str, str]] = []
    if len(locs) >= 2:
        out.append({
            "type": "location_mismatch",
            "detail": f"NER locations: {', '.join(sorted(locs)[:6])}",
        })
    if len(persons) >= 2:
        out.append({
            "type": "name_variant",
            "detail": f"NER person names: {', '.join(sorted(persons)[:6])}",
        })
    if len(orgs) >= 2:
        out.append({
            "type": "organization_conflict",
            "detail": f"Multiple organizations: {', '.join(sorted(orgs)[:6])}",
        })
    return out


def build_language_profile_ml(artifacts: list[TextArtifact]) -> LanguageProfile:
    counts: Counter[str] = Counter()
    scripts = {"devanagari": 0, "latin": 0}
    for art in artifacts:
        lang = art.detected_language or "unknown"
        counts[lang] += max(1, art.char_count // 40)
        scripts["devanagari"] += len(_DEVANAGARI_RE.findall(art.text))
        scripts["latin"] += len(re.findall(r"[a-zA-Z]", art.text))
    total = sum(counts.values()) or 1
    dist = {k: round(v / total, 3) for k, v in counts.items()}
    primary = counts.most_common(1)[0][0] if counts else "unknown"
    return LanguageProfile(primary=primary, distribution=dist, scripts=scripts)


def sentiment_overview_ml(insights: list[ArtifactInsight]) -> dict[str, Any]:
    pos = neg = neu = 0
    for ins in insights:
        if not ins.sentiment:
            neu += 1
            continue
        if ins.sentiment.label == "positive":
            pos += 1
        elif ins.sentiment.label == "negative":
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
        "engine": "ml",
    }


def ml_analyze(
    artifacts: list[TextArtifact],
    *,
    seed_query: str,
    corpus_quality: dict[str, Any] | None = None,
) -> LinguisticAnalysisOutput:
    fast = fast_linguistic_mode()
    cap = max_ml_artifacts()
    artifacts = artifacts[:cap]
    quality = dict(corpus_quality or {})
    quality.update({"analyzed_artifacts": len(artifacts), "fast_mode": fast})

    texts = [a.text for a in artifacts]
    refs = [a.source_ref or a.source_tool for a in artifacts]

    langs = detect_languages_ml(texts)
    tagged = [
        art.model_copy(update={"detected_language": lang})
        for art, lang in zip(artifacts, langs)
    ]

    sentiments = sentiment_ml(texts)
    ner_batches = ner_ml(texts, refs)
    regex_entities = analyzers.extract_named_entities(tagged)

    ml_entities: list[NamedEntity] = []
    for batch in ner_batches:
        ml_entities.extend(batch)

    merged_entities = _merge_entities(ml_entities + regex_entities)
    # Boost person entities that match the investigation seed username.
    variants = _seed_variants(seed_query)
    if variants:
        boosted: list[NamedEntity] = []
        for ent in merged_entities:
            match = _identity_match_score(ent.text, variants)
            if match >= 0.5 and ent.kind == "person":
                ent = ent.model_copy(update={"confidence": round(min(1.0, ent.confidence + 0.15), 3)})
            boosted.append(ent)
        merged_entities = sorted(boosted, key=lambda e: -e.confidence)

    blob = _weighted_corpus_blob(tagged)
    if fast:
        topics = analyzers.extract_topics(tagged)
        keywords = analyzers.top_keywords(tagged)
        embed_links: list[CrossTextLink] = []
        used_models = {
            "language": models_used()["language"],
            "sentiment": models_used()["sentiment"],
            "ner": models_used()["ner"],
        }
    else:
        topics = topics_ml(blob)
        embed_model = get_embedding_model()
        keywords = keywords_ml(blob, embed_model=embed_model)
        embed_links = embedding_cross_links(tagged, embed_model=embed_model)
        used_models = models_used()

    styles = analyzers.build_style_fingerprints(tagged)
    heuristic_links = analyzers.cross_text_links(tagged)

    cross: list[CrossTextLink] = embed_links + heuristic_links
    for i, a in enumerate(styles):
        for b in styles[i + 1 :]:
            sim = analyzers.cosine_similarity_styles(a, b)
            if sim >= 0.88 and a.source_key != b.source_key:
                cross.append(
                    CrossTextLink(
                        kind="stylometry_similarity",
                        sources=[a.source_key, b.source_key],
                        detail=f"Stylometry cosine {sim}",
                        score=sim,
                    )
                )
    cross.sort(key=lambda x: -x.score)

    contradictions = contradictions_from_ner(merged_entities)
    contradictions.extend(analyzers.find_contradictions(tagged))
    contradictions = _dedupe_contradictions(contradictions)

    threat_flags = analyzers.threat_flags(tagged)
    if not fast:
        threat_flags += toxicity_flags_ml(tagged)
    identity_signals = _build_identity_signals(
        seed_query=seed_query,
        artifacts=tagged,
        entities=merged_entities,
        keywords=keywords,
    )

    insights: list[ArtifactInsight] = []
    for art, sent, ner_list in zip(tagged, sentiments, ner_batches):
        insights.append(
            ArtifactInsight(
                source_ref=art.source_ref or art.source_tool,
                source_tool=art.source_tool,
                source_platform=art.source_platform,
                language=art.detected_language,
                sentiment=sent,
                entity_count=len(ner_list),
                char_count=art.char_count,
            )
        )

    total_chars = sum(a.char_count for a in tagged)
    return LinguisticAnalysisOutput(
        seed_query=seed_query,
        artifacts_analyzed=len(tagged),
        total_characters=total_chars,
        engine_mode="ml",
        models_used=used_models,
        language_profile=build_language_profile_ml(tagged),
        named_entities=merged_entities[:100],
        topics=topics,
        sentiment_overview=sentiment_overview_ml(insights),
        style_fingerprints=styles,
        cross_links=cross[:25],
        contradictions=contradictions,
        threat_flags=threat_flags[:15],
        keywords=keywords,
        corpus_sample=tagged[:20],
        artifact_insights=insights,
        identity_signals=identity_signals,
        corpus_quality=quality,
    )


def _merge_entities(entities: list[NamedEntity]) -> list[NamedEntity]:
    seen: set[tuple[str, str]] = set()
    out: list[NamedEntity] = []
    for ent in entities:
        key = (ent.kind, ent.text.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(ent)
    out.sort(key=lambda e: -e.confidence)
    return out


def _dedupe_contradictions(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in items:
        key = f"{item.get('type')}:{item.get('detail')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
