from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.discovery import DiscoveryConfig


QueryType = Literal["username", "email", "phone", "domain", "image", "infra"]
InvestigationMode = Literal["standard", "fast", "deep"]


class InvestigateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    query_type: QueryType | None = Field(default=None, description="Auto-detected if omitted")
    timeout_per_tool: float = Field(default=120.0, ge=10.0, le=600.0)
    case_id: str | None = Field(default=None, description="Optional case to link this investigation")
    discovery: DiscoveryConfig | None = Field(
        default=None,
        description="Recursive lead expansion settings. Enabled by default when omitted.",
    )
    investigation_mode: InvestigationMode | None = Field(
        default=None,
        description="Standard / fast / deep — overrides discovery-derived mode when set.",
    )


class ReviewRequest(BaseModel):
    investigation_id: str
    cluster_id: str
    decision: Literal["approve", "reject", "suspicious"]
    reviewer: str = Field(default="investigator")
    notes: str = ""


class CopilotRequest(BaseModel):
    investigation_id: str | None = None
    case_id: str | None = Field(
        default=None,
        description="When set, copilot receives ALL investigations linked to this case",
    )
    message: str = Field(..., min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    investigation_id: str
    query: str
    reviewer: str = "investigator"
    include_graph: bool = True
    case_id: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
