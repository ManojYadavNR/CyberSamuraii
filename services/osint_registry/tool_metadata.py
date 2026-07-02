"""OSINT Framework-style tool metadata schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

InputType = Literal["username", "email", "image", "domain", "phone", "infra"]
EntityType = Literal[
    "account", "email", "phone", "domain", "image", "document",
    "organization", "person", "event", "relationship",
]
CostTier = Literal["free", "low", "medium", "high"]
SpeedTier = Literal["fast", "medium", "slow"]


class ToolMetadata(BaseModel):
    tool_name: str
    entity_types: list[str] = Field(default_factory=list)
    supported_inputs: list[str] = Field(default_factory=list)
    cost: CostTier = "low"
    speed: SpeedTier = "medium"
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    parallel_safe: bool = True
    enabled: bool = True
    priority: int = 100
    parallel_group: str = "default"
    adapter_key: str | None = None
    feature: str | None = None
    hop_eligible: bool = False
    catalog_only: bool = False
    osint_category: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)

    def is_runnable(self) -> bool:
        return self.enabled and not self.catalog_only and bool(self.adapter_key)


class ToolSelectionPlan(BaseModel):
    input_type: str
    feature: str
    tools: list[str]
    parallel_groups: dict[str, list[str]]
    wall_budget_sec: float = 300.0
    metadata: list[ToolMetadata] = Field(default_factory=list)
