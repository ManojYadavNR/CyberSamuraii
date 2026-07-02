"""Person-centric intelligence layer — identity profile built from all evidence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.evidence import FieldProvenance, PlatformProfile
from schemas.pivot import InvestigationTree


class SupportingEvidence(BaseModel):
    field: str
    value: str
    confidence: float = 0.5
    source_platform: str | None = None
    source_tool: str | None = None
    source_ref: str | None = None
    extraction_strategy: str = ""


class IdentityRelationship(BaseModel):
    relation_type: str
    target: str
    confidence: float = 0.5
    source_ref: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class IdentityTimelineEvent(BaseModel):
    timestamp: str
    event_type: str
    description: str
    source: str | None = None
    confidence: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)


class IdentityProfile(BaseModel):
    """Person behind the accounts — continuously enriched from all discovered evidence."""

    seed_query: str
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    primary_name: str | None = None
    primary_bio: str | None = None
    primary_location: str | None = None
    primary_avatar: str | None = None

    names: list[FieldProvenance] = Field(default_factory=list)
    aliases: list[FieldProvenance] = Field(default_factory=list)
    usernames: list[FieldProvenance] = Field(default_factory=list)
    photos: list[FieldProvenance] = Field(default_factory=list)
    emails: list[FieldProvenance] = Field(default_factory=list)
    phones: list[FieldProvenance] = Field(default_factory=list)
    domains: list[FieldProvenance] = Field(default_factory=list)
    websites: list[FieldProvenance] = Field(default_factory=list)
    organizations: list[FieldProvenance] = Field(default_factory=list)
    companies: list[FieldProvenance] = Field(default_factory=list)
    schools: list[FieldProvenance] = Field(default_factory=list)
    achievements: list[FieldProvenance] = Field(default_factory=list)
    projects: list[FieldProvenance] = Field(default_factory=list)
    appearances: list[FieldProvenance] = Field(default_factory=list)
    publications: list[FieldProvenance] = Field(default_factory=list)
    events: list[FieldProvenance] = Field(default_factory=list)
    social_accounts: list[FieldProvenance] = Field(default_factory=list)
    bios: list[FieldProvenance] = Field(default_factory=list)
    locations: list[FieldProvenance] = Field(default_factory=list)
    public_links: list[FieldProvenance] = Field(default_factory=list)
    search_findings: list[FieldProvenance] = Field(default_factory=list)

    platform_profiles: list[PlatformProfile] = Field(default_factory=list)
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    relationships: list[IdentityRelationship] = Field(default_factory=list)
    timeline: list[IdentityTimelineEvent] = Field(default_factory=list)
    investigation_tree: InvestigationTree | None = None

    verified_platform_count: int = 0
    total_evidence_fields: int = 0
    enrichment_passes: int = 0
