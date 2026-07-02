"""Lead-generation visuals — hackathon, news, college, profile cards."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LeadVisual(BaseModel):
    lead_id: str
    lead_type: str = Field(description="hackathon | event | news | article | video | profile | achievement")
    title: str
    url: str
    snippet: str = ""
    source_domain: str = ""
    image_url: str | None = None
    thumbnail_url: str | None = None
    visual_source: str = Field(default="", description="og_image | youtube_thumb | page_screenshot | serp_image | avatar")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    priority_score: float = 0.0


class LeadVisualOutput(BaseModel):
    leads: list[LeadVisual] = Field(default_factory=list)
    captured_screenshots: int = 0
    strategies: list[str] = Field(default_factory=list)
