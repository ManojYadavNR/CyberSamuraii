"""Schemas for the Image Intelligence Engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.fusion import Entity


class ImageFinding(BaseModel):
    """Single intelligence finding from an image module."""

    category: str = Field(description="face | metadata | ocr | object | fingerprint")
    field: str
    value: str
    source_tool: str
    extraction_strategy: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ImageIntelligenceOutput(BaseModel):
    """Consolidated output from all parallel image modules."""

    image_source: str
    image_path: str | None = None
    image_url: str | None = None
    face_count: int = 0
    findings: list[ImageFinding] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    modules_run: list[str] = Field(default_factory=list)
    modules_failed: list[str] = Field(default_factory=list)
    perceptual_hashes: dict[str, str] = Field(default_factory=dict)
    similarity_signature: str | None = None
    content_type: str | None = None
    ocr_text: str | None = None
