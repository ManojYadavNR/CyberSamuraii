from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from schemas.correlation import CorrelationOutput
from schemas.discovery import DiscoveryOutput
from schemas.evidence import EvidenceExtractionOutput
from schemas.intelligence import IdentityProfile
from schemas.fusion import FusionOutput
from schemas.graph import GraphOutput


class ToolStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    NOT_INSTALLED = "not_installed"
    MISSING_API_KEY = "missing_api_key"


class ToolResult(BaseModel):
    tool: str
    success: bool
    data: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    execution_time_ms: float = 0.0
    raw_output: str | None = None


class ConfidenceInput(BaseModel):
    source_tool: str
    field: str
    value: Any
    weight: float = 1.0


class FeatureResult(BaseModel):
    feature: str
    query: str
    query_normalized: str | None = None
    warnings: list[str] = Field(default_factory=list)
    execution_mode: str = "parallel"
    tool_results: list[ToolResult] = Field(default_factory=list)
    merged_results: list[dict[str, Any]] = Field(default_factory=list)
    confirmed_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Verified account registrations and public intel only",
    )
    public_profile_data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Public profile data (e.g. Gravatar) linked to the email",
    )
    investigation_leads: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Inconclusive checks worth manual follow-up (not confirmed)",
    )
    scan_summary: dict[str, Any] | None = None
    fusion: FusionOutput | None = None
    correlation: CorrelationOutput | None = None
    graph: GraphOutput | None = None
    discovery: DiscoveryOutput | None = None
    evidence_extraction: EvidenceExtractionOutput | None = None
    identity_profile: IdentityProfile | None = None
    reverse_image_discovery: Any | None = None
    image_correlation: Any | None = None
    confidence_raw_inputs: list[ConfidenceInput] = Field(default_factory=list)
    total_execution_time_ms: float = 0.0
    tools_succeeded: int = 0
    tools_failed: int = 0


class ToolStatusResponse(BaseModel):
    statuses: dict[str, ToolStatus]
