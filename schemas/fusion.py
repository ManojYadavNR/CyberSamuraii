from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceRecord(BaseModel):
    """Full provenance for a single tool contribution."""

    tool: str
    timestamp: str = Field(default_factory=_utc_now)
    raw_source_ref: str = Field(description="URL, file path, or tool output reference")
    source_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    raw_payload: dict[str, Any] | None = Field(
        default=None,
        description="Preserved raw evidence for audit queries",
    )


class Entity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid4()))
    type: str = Field(description="account | email | phone | domain | image | person | post | hashtag")
    value: str
    canonical_value: str = ""
    aliases: list[str] = Field(default_factory=list)
    normalized_value: str = ""
    sources: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reliability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    fusion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    first_seen: str = Field(default_factory=_utc_now)
    last_seen: str = Field(default_factory=_utc_now)
    evidence: list[EvidenceRecord] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.normalized_value:
            self.normalized_value = self.value.strip().lower()
        if not self.canonical_value:
            self.canonical_value = self.normalized_value


class FusionOutput(BaseModel):
    entities: list[Entity] = Field(
        default_factory=list,
        description="All extracted entities before deduplication",
    )
    deduplicated_entities: list[Entity] = Field(
        default_factory=list,
        description="Merged unique entities with fused scores",
    )
    fusion_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall evidence strength for the investigation query",
    )
    evidence_map: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-entity evidence breakdown keyed by type:value",
    )
    investigation_id: str | None = Field(
        default=None,
        description="UUID of persisted investigation when database is enabled",
    )
    raw_evidence_index: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Maps entity keys to raw evidence record IDs for audit queries",
    )
