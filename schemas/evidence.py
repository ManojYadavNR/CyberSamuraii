"""Schemas for universal evidence extraction and unified person profiles."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FieldProvenance(BaseModel):
    """Source attribution for a single extracted intelligence field."""

    field: str
    value: str
    source_entity_id: str | None = None
    source_entity_type: str | None = None
    source_platform: str | None = None
    source_tool: str | None = None
    source_ref: str | None = None
    extraction_strategy: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class PlatformProfile(BaseModel):
    """Rich intelligence extracted from one platform account."""

    entity_id: str
    platform: str
    handle: str
    url: str | None = None
    verified: bool = False
    sources: list[str] = Field(default_factory=list)
    fusion_score: float = 0.0
    display_name: str | None = None
    bio: str | None = None
    location: str | None = None
    website: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    organizations: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    usernames: list[str] = Field(default_factory=list)
    public_links: list[str] = Field(default_factory=list)
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_fields: list[FieldProvenance] = Field(default_factory=list)


class UnifiedPersonProfile(BaseModel):
    """One identity built from multi-platform evidence — not platform-centric."""

    seed_query: str
    platform_count: int = 0
    verified_platform_count: int = 0
    names: list[FieldProvenance] = Field(default_factory=list)
    aliases: list[FieldProvenance] = Field(default_factory=list)
    usernames: list[FieldProvenance] = Field(default_factory=list)
    bios: list[FieldProvenance] = Field(default_factory=list)
    locations: list[FieldProvenance] = Field(default_factory=list)
    emails: list[FieldProvenance] = Field(default_factory=list)
    websites: list[FieldProvenance] = Field(default_factory=list)
    organizations: list[FieldProvenance] = Field(default_factory=list)
    images: list[FieldProvenance] = Field(default_factory=list)
    public_links: list[FieldProvenance] = Field(default_factory=list)
    search_findings: list[FieldProvenance] = Field(default_factory=list)
    platform_profiles: list[PlatformProfile] = Field(default_factory=list)
    primary_display_name: str | None = None
    primary_bio: str | None = None
    primary_location: str | None = None
    primary_avatar: str | None = None


class EvidenceExtractionOutput(BaseModel):
    """Result of universal evidence extraction pass."""

    entities_enriched: int = 0
    fields_extracted: int = 0
    platforms_analyzed: int = 0
    extraction_strategies: list[str] = Field(default_factory=list)
    unified_profile: UnifiedPersonProfile | None = None
    lead_visuals: list[dict[str, Any]] = Field(default_factory=list)
    lead_screenshots_captured: int = 0
    google_search_intel: dict[str, Any] | None = Field(
        default=None,
        description="Merged plain Google username search + keyword-driven dork follow-ups",
    )
    samurai_social_intel: dict[str, Any] | None = Field(
        default=None,
        description="Deep Instagram/Facebook profile intel from Samurai tool",
    )
    linguistic_analysis: dict[str, Any] | None = Field(
        default=None,
        description="Post-extraction linguistic profile: language, topics, entities, style links",
    )
