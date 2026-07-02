"""Linguistic analysis engine — ML-first with heuristic fallback."""

from __future__ import annotations

import logging
import os
from typing import Any

from schemas.linguistic import CrossTextLink, LinguisticAnalysisOutput, TextArtifact
from services.linguistic import analyzers
from services.linguistic.corpus import collect_from_evidence, collect_from_tool_results, refine_corpus

logger = logging.getLogger(__name__)


def linguistic_enabled() -> bool:
    return os.getenv("LINGUISTIC_ANALYSIS_ENABLED", "true").lower() in ("1", "true", "yes", "on")


def _heuristic_analyze(artifacts: list[TextArtifact], *, seed_query: str) -> LinguisticAnalysisOutput:
    tagged: list[TextArtifact] = []
    for art in artifacts:
        tagged.append(
            art.model_copy(update={"detected_language": analyzers.detect_language(art.text)})
        )

    styles = analyzers.build_style_fingerprints(tagged)
    cross = analyzers.cross_text_links(tagged)
    for i, a in enumerate(styles):
        for b in styles[i + 1 :]:
            sim = analyzers.cosine_similarity_styles(a, b)
            if sim >= 0.92 and a.source_key != b.source_key:
                cross.append(
                    CrossTextLink(
                        kind="similar_writing_style",
                        sources=[a.source_key, b.source_key],
                        detail=f"Style similarity {sim}",
                        score=sim,
                    )
                )

    total_chars = sum(a.char_count for a in tagged)
    return LinguisticAnalysisOutput(
        seed_query=seed_query,
        artifacts_analyzed=len(tagged),
        total_characters=total_chars,
        engine_mode="heuristic",
        language_profile=analyzers.build_language_profile(tagged),
        named_entities=analyzers.extract_named_entities(tagged),
        topics=analyzers.extract_topics(tagged),
        sentiment_overview=analyzers.sentiment_overview(tagged),
        style_fingerprints=styles,
        cross_links=cross[:25],
        contradictions=analyzers.find_contradictions(tagged),
        threat_flags=analyzers.threat_flags(tagged),
        keywords=analyzers.top_keywords(tagged),
        corpus_sample=tagged[:20],
    )


class LinguisticAnalysisEngine:
    def analyze(
        self,
        *,
        seed_query: str,
        tool_results: list[Any] | None = None,
        evidence: Any = None,
    ) -> LinguisticAnalysisOutput:
        artifacts: list[TextArtifact] = []
        artifacts.extend(collect_from_tool_results(tool_results))
        artifacts.extend(collect_from_evidence(evidence))

        artifacts, corpus_quality = refine_corpus(artifacts, seed_query=seed_query)

        if not artifacts:
            return LinguisticAnalysisOutput(
                seed_query=seed_query,
                artifacts_analyzed=0,
                total_characters=0,
                corpus_quality=corpus_quality,
            )

        from services.linguistic.runtime import linguistic_ml_enabled, run_sync

        if linguistic_ml_enabled():
            try:
                from services.linguistic.ml_analyzers import ml_analyze

                return run_sync(ml_analyze, artifacts, seed_query=seed_query, corpus_quality=corpus_quality)
            except Exception as exc:
                logger.warning("ML linguistic analysis failed, using heuristics: %r", exc)

        out = _heuristic_analyze(artifacts, seed_query=seed_query)
        return out.model_copy(update={"corpus_quality": corpus_quality})


linguistic_engine = LinguisticAnalysisEngine()
