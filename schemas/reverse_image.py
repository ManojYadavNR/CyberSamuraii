"""Schemas for reverse image discovery and cross-platform image correlation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.discovery import DiscoveryLead

MatchType = Literal[
    "identical",
    "cropped",
    "mirrored",
    "edited",
    "resized",
    "screenshot",
    "profile_photo",
    "cross_platform_reuse",
    "similar",
]


class ReverseImageMatch(BaseModel):
    match_id: str
    source: str
    match_type: MatchType = "similar"
    match_url: str
    page_url: str | None = None
    title: str | None = None
    snippet: str | None = None
    platform: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence_path: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    profile_urls: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)


class EvidenceChainLink(BaseModel):
    step: str
    value: str
    source: str | None = None
    confidence: float = 0.5


class EvidenceChain(BaseModel):
    chain_id: str
    seed_image: str
    links: list[EvidenceChainLink] = Field(default_factory=list)
    terminal_lead: str | None = None
    confidence: float = 0.5


class ReverseImageDiscoveryOutput(BaseModel):
    seed_image: str
    sources_run: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)
    matches: list[ReverseImageMatch] = Field(default_factory=list)
    generated_leads: list[DiscoveryLead] = Field(default_factory=list)
    evidence_chains: list[EvidenceChain] = Field(default_factory=list)
    total_matches: int = 0


class IdentityCandidate(BaseModel):
    candidate_id: str
    label: str
    confidence: float = 0.5
    reasons: list[str] = Field(default_factory=list)
    linked_accounts: list[str] = Field(default_factory=list)
    face_match_score: float | None = None
    image_similarity_score: float | None = None
    hash_similarity_score: float | None = None
    evidence_paths: list[list[str]] = Field(default_factory=list)


class DetectedFace(BaseModel):
    face_id: str
    person_index: int
    source_tool: str
    confidence: float = 0.0
    quality_score: float | None = None
    bbox: list[float] = Field(default_factory=list)
    crop_path: str | None = None
    crop_preview_url: str | None = None
    embedding_signature: str | None = None


class ImageCorrelationOutput(BaseModel):
    seed_image: str
    seed_preview_url: str | None = None
    detected_faces: list[DetectedFace] = Field(default_factory=list)
    identity_candidates: list[IdentityCandidate] = Field(default_factory=list)
    face_matches: list[dict[str, Any]] = Field(default_factory=list)
    reverse_matches: list[ReverseImageMatch] = Field(default_factory=list)
    hash_signatures: dict[str, str] = Field(default_factory=dict)
    similarity_signature: str | None = None
    confidence_breakdown: dict[str, float] = Field(default_factory=dict)
    evidence_chains: list[EvidenceChain] = Field(default_factory=list)
