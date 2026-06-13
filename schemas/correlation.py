from typing import Any

from pydantic import BaseModel, Field


class CorrelationEvidence(BaseModel):
    type: str = Field(description="username | text | image | behavior | location | email")
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    detail: str | None = None
    conflicting: bool = False


class AccountCluster(BaseModel):
    account_cluster_id: str
    linked_accounts: list[dict[str, Any]] = Field(default_factory=list)
    linked_account_refs: list[str] = Field(
        default_factory=list,
        description="Compact platform:handle references, e.g. github:hacker123",
    )
    confidence_score: float = Field(ge=0.0, le=100.0)
    evidence: list[CorrelationEvidence] = Field(default_factory=list)
    explainability: list[str] = Field(default_factory=list)


class CorrelationOutput(BaseModel):
    clusters: list[AccountCluster] = Field(default_factory=list)
    total_accounts_analyzed: int = 0
    total_clusters: int = 0
    correlation_engine_version: str = "2.0.0"
    signal_availability: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
