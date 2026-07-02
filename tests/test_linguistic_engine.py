"""Tests for linguistic analysis engine."""

from __future__ import annotations

import pytest

from schemas.evidence import EvidenceExtractionOutput, FieldProvenance, UnifiedPersonProfile
from schemas.linguistic import LinguisticAnalysisOutput, LanguageProfile, TopicSignal
from services.linguistic.bridge import apply_linguistic_analysis
from services.linguistic.engine import linguistic_engine


@pytest.fixture(autouse=True)
def _disable_ml_for_unit_tests(monkeypatch):
    monkeypatch.setenv("LINGUISTIC_ML_ENABLED", "false")


def test_detect_hinglish_and_topics():
    tool_results = [
        {
            "tool": "samurai",
            "success": True,
            "data": [
                {
                    "platform": "instagram",
                    "bio": "CS student at Cambridge Institute. GitHub: manojyadavnr. Delhi based.",
                    "recent_posts": [
                        {"caption": "Hackathon winner at college tech fest #coding"},
                    ],
                }
            ],
        },
        {
            "tool": "sherlock",
            "success": True,
            "data": [
                {
                    "site": "GitHub",
                    "url": "https://github.com/manojyadavnr",
                    "bio": "Developer | Open source | यह मेरा प्रोफाइल है",
                }
            ],
        },
    ]
    out = linguistic_engine.analyze(seed_query="manojyadavnr", tool_results=tool_results)
    assert out.artifacts_analyzed >= 2
    assert out.language_profile.primary in ("en", "hinglish", "hi", "unknown")
    topic_names = {t.topic for t in out.topics}
    assert "technology" in topic_names or "education" in topic_names or "social_media" in topic_names
    assert out.total_characters > 20
    assert out.keywords or out.named_entities
    assert out.keywords


def test_apply_linguistic_analysis_attaches_to_evidence():
    evidence = EvidenceExtractionOutput(
        entities_enriched=1,
        fields_extracted=1,
        platforms_analyzed=1,
        unified_profile=UnifiedPersonProfile(
            seed_query="alice",
            bios=[FieldProvenance(field="bio", value="Engineer in Bangalore", source_tool="sherlock")],
        ),
    )
    tool_results = [
        {
            "tool": "sherlock",
            "success": True,
            "data": [{"site": "GitHub", "bio": "alice dev https://github.com/alice"}],
        }
    ]
    updated = apply_linguistic_analysis(evidence, seed_query="alice", tool_results=tool_results)
    assert updated is not None
    assert updated.linguistic_analysis is not None
    assert "linguistic_analysis" in updated.extraction_strategies
    assert updated.linguistic_analysis["artifacts_analyzed"] >= 1


@pytest.mark.asyncio
async def test_collect_from_tool_result_models():
    from schemas.common import ToolResult

    tool_results = [
        ToolResult(
            tool="sherlock",
            success=True,
            data=[
                {
                    "platform": "GitHub",
                    "handle": "manojyadavnr",
                    "bio": "Software engineer. Loves hackathons and open source.",
                }
            ],
        )
    ]
    out = linguistic_engine.analyze(seed_query="manojyadavnr", tool_results=tool_results)
    assert out.artifacts_analyzed >= 1


@pytest.mark.asyncio
async def test_evidence_engine_includes_linguistic(monkeypatch):
    from schemas.fusion import Entity, FusionOutput
    from services.evidence.engine import evidence_engine

    monkeypatch.setattr(
        "services.evidence.engine.build_samurai_social_intel",
        lambda _tr: None,
    )

    fusion = FusionOutput(
        query="alice",
        deduplicated_entities=[
            Entity(
                entity_id="e1",
                type="account",
                value="alice",
                platform="github",
                handle="alice",
                url="https://github.com/alice",
                confidence=0.9,
            )
        ],
        fusion_score=0.8,
    )
    tool_results = [
        {
            "tool": "sherlock",
            "success": True,
            "data": [
                {
                    "platform": "GitHub",
                    "handle": "alice",
                    "url": "https://github.com/alice",
                    "bio": "Software engineer. Loves hackathons and open source.",
                }
            ],
        }
    ]
    _, output = await evidence_engine.extract(
        fusion,
        seed_query="alice",
        enrich_public_profiles=False,
        tool_results=tool_results,
    )
    assert output.linguistic_analysis is not None
    assert output.linguistic_analysis.get("artifacts_analyzed", 0) >= 1


def test_ml_engine_path_when_enabled(monkeypatch):
    from schemas.linguistic import TextArtifact

    monkeypatch.setenv("LINGUISTIC_ML_ENABLED", "true")

    def _fake_ml(artifacts, *, seed_query: str, corpus_quality=None):
        return LinguisticAnalysisOutput(
            seed_query=seed_query,
            artifacts_analyzed=len(artifacts),
            total_characters=sum(a.char_count for a in artifacts),
            engine_mode="ml",
            models_used={"ner": "test-ner"},
            language_profile=LanguageProfile(primary="en"),
            topics=[TopicSignal(topic="technology", score=0.9, evidence_snippets=["dev"])],
        )

    monkeypatch.setattr("services.linguistic.ml_analyzers.ml_analyze", _fake_ml)
    out = linguistic_engine.analyze(
        seed_query="alice",
        tool_results=[{"tool": "sherlock", "success": True, "data": [{"bio": "software engineer"}]}],
    )
    assert out.engine_mode == "ml"
    assert out.models_used.get("ner") == "test-ner"
