from typing import Any, Literal

from pydantic import BaseModel, Field


class DiscoveryConfig(BaseModel):
    """Auto-pivot limits — image investigations expand until leads are exhausted."""

    enabled: bool = True
    max_depth: int = Field(default=3, ge=1, le=6)
    max_hops: int = Field(default=12, ge=0, le=50)
    max_leads_per_hop: int = Field(default=8, ge=1, le=100)
    max_total_leads: int = Field(default=24, ge=1, le=200)


def is_deep_discovery(config: DiscoveryConfig | None) -> bool:
    """UI Deep mode sends max_hops=20; standard person scans use max_hops<=2."""
    return bool(config and config.enabled and config.max_hops >= 10)


def discovery_config_for_query_type(query_type: str, *, deep: bool = False) -> "DiscoveryConfig":
    """Person-centric expansion defaults per investigation type."""
    if query_type == "image":
        if deep:
            return DiscoveryConfig(
                enabled=True,
                max_depth=4,
                max_hops=20,
                max_leads_per_hop=12,
                max_total_leads=50,
            )
        return DiscoveryConfig(
            enabled=True,
            max_depth=2,
            max_hops=6,
            max_leads_per_hop=4,
            max_total_leads=10,
        )
    if query_type in ("phone", "infra"):
        return DiscoveryConfig(enabled=False)
    if deep:
        return DiscoveryConfig(enabled=True, max_depth=3, max_hops=10, max_leads_per_hop=15, max_total_leads=40)
    return DiscoveryConfig(
        enabled=True,
        max_depth=2,
        max_hops=2,
        max_leads_per_hop=5,
        max_total_leads=12,
    )


LeadType = Literal[
    "username",
    "email",
    "domain",
    "phone",
    "image",
    "infra",
    "url",
    "account",
    "organization",
    "name",
]


class DiscoveryLead(BaseModel):
    lead_id: str
    query: str
    lead_type: LeadType
    feature: str
    depth: int = Field(ge=0)
    priority: float = Field(default=0.5, ge=0.0, le=1.0)
    source_entity_id: str | None = None
    source_entity_type: str | None = None
    source_query: str | None = None
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscoveryHop(BaseModel):
    hop_id: str
    depth: int
    query: str
    feature: str
    lead_type: LeadType
    parent_lead_id: str | None = None
    status: Literal["completed", "failed", "skipped"] = "completed"
    entities_found: int = 0
    leads_spawned: int = 0
    execution_time_ms: float = 0.0
    error: str | None = None
    reason: str = ""


class TimelineEvent(BaseModel):
    event_id: str
    timestamp: str
    phase: Literal[
        "seed",
        "lead_discovered",
        "hop_started",
        "hop_completed",
        "hop_failed",
        "merge",
        "correlation",
        "graph",
        "expansion_stopped",
    ]
    message: str
    detail: str | None = None
    depth: int | None = None
    query: str | None = None


class DiscoveryOutput(BaseModel):
    enabled: bool = True
    seed_query: str
    seed_query_type: str
    config: DiscoveryConfig
    hops: list[DiscoveryHop] = Field(default_factory=list)
    pending_leads: list[DiscoveryLead] = Field(default_factory=list)
    visited: list[str] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    total_hops: int = 0
    total_leads_discovered: int = 0
    total_leads_expanded: int = 0
    max_depth_reached: int = 0
    stop_reason: str = ""
    total_execution_time_ms: float = 0.0
    investigation_tree: Any | None = None
