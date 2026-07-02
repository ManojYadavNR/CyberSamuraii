"""Generic pivot system — evidence modules return leads for auto-investigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from schemas.discovery import DiscoveryLead


class PivotOpportunity(BaseModel):
    """Describes one possible expansion from an evidence type."""

    field: str
    lead_type: str
    feature: str
    strategy: str
    description: str = ""
    priority_boost: float = 0.0


class PivotEvidence(BaseModel):
    """Single evidence item with provenance for investigation trees."""

    evidence_id: str
    entity_id: str | None = None
    entity_type: str
    field: str
    value: str
    source_tool: str | None = None
    source_platform: str | None = None
    source_ref: str | None = None
    strategy: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PivotResult(BaseModel):
    """Standard module output: evidence discovered + leads to investigate."""

    evidence: list[PivotEvidence] = Field(default_factory=list)
    generated_leads: list[Any] = Field(default_factory=list)
    opportunities: list[PivotOpportunity] = Field(default_factory=list)


class InvestigationTreeNode(BaseModel):
    """One node in the investigation tree — evidence, lead, or hop."""

    node_id: str
    node_type: Literal["seed", "evidence", "lead", "hop", "profile"]
    label: str
    value: str | None = None
    parent_id: str | None = None
    children_ids: list[str] = Field(default_factory=list)
    depth: int = 0
    status: str | None = None
    feature: str | None = None
    lead_type: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvestigationTree(BaseModel):
    """Shows how information was discovered: evidence → lead → evidence chains."""

    root_id: str
    seed_query: str
    nodes: list[InvestigationTreeNode] = Field(default_factory=list)
    total_evidence_nodes: int = 0
    total_lead_nodes: int = 0
    total_hop_nodes: int = 0
    max_depth: int = 0
