from typing import Any, Literal

from pydantic import BaseModel, Field


QueryType = Literal["username", "email", "phone", "domain", "image", "infra"]


class InvestigateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    query_type: QueryType | None = Field(default=None, description="Auto-detected if omitted")
    timeout_per_tool: float = Field(default=120.0, ge=10.0, le=600.0)


class ReviewRequest(BaseModel):
    investigation_id: str
    cluster_id: str
    decision: Literal["approve", "reject", "suspicious"]
    reviewer: str = Field(default="investigator")
    notes: str = ""


class CopilotRequest(BaseModel):
    investigation_id: str | None = None
    message: str = Field(..., min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    investigation_id: str
    query: str
    reviewer: str = "investigator"
    include_graph: bool = True
    result: dict[str, Any] = Field(default_factory=dict)
