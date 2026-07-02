"""Schemas for post-investigation linguistic analysis."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TextArtifact(BaseModel):
    source_tool: str = ""
    source_platform: str | None = None
    source_ref: str = ""
    text: str = ""
    char_count: int = 0
    detected_language: str = "unknown"


class NamedEntity(BaseModel):
    text: str
    kind: str
    source_ref: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class TopicSignal(BaseModel):
    topic: str
    score: float = Field(ge=0.0, le=1.0)
    evidence_snippets: list[str] = Field(default_factory=list)
    model: str = ""


class LanguageProfile(BaseModel):
    primary: str = "unknown"
    distribution: dict[str, float] = Field(default_factory=dict)
    scripts: dict[str, int] = Field(default_factory=dict)


class SentimentScore(BaseModel):
    label: str = "neutral"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    model: str = ""


class ArtifactInsight(BaseModel):
    source_ref: str = ""
    source_tool: str = ""
    source_platform: str | None = None
    language: str = "unknown"
    sentiment: SentimentScore | None = None
    entity_count: int = 0
    char_count: int = 0


class WritingStyleFingerprint(BaseModel):
    source_key: str
    avg_word_length: float = 0.0
    vocabulary_richness: float = 0.0
    hashtag_rate: float = 0.0
    emoji_rate: float = 0.0
    exclamation_rate: float = 0.0


class CrossTextLink(BaseModel):
    kind: str
    sources: list[str] = Field(default_factory=list)
    detail: str = ""
    score: float = Field(default=0.5, ge=0.0, le=1.0)


class LinguisticAnalysisOutput(BaseModel):
    seed_query: str = ""
    artifacts_analyzed: int = 0
    total_characters: int = 0
    engine_mode: str = "heuristic"
    models_used: dict[str, str] = Field(default_factory=dict)
    language_profile: LanguageProfile = Field(default_factory=LanguageProfile)
    named_entities: list[NamedEntity] = Field(default_factory=list)
    topics: list[TopicSignal] = Field(default_factory=list)
    sentiment_overview: dict[str, Any] = Field(default_factory=dict)
    style_fingerprints: list[WritingStyleFingerprint] = Field(default_factory=list)
    cross_links: list[CrossTextLink] = Field(default_factory=list)
    contradictions: list[dict[str, str]] = Field(default_factory=list)
    threat_flags: list[dict[str, Any]] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    corpus_sample: list[TextArtifact] = Field(default_factory=list)
    artifact_insights: list[ArtifactInsight] = Field(default_factory=list)
    identity_signals: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Seed-query name/handle matches in corpus and NER",
    )
    corpus_quality: dict[str, Any] = Field(
        default_factory=dict,
        description="Noise filtering and corpus composition stats",
    )
