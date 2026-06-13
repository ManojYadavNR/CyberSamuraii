from pydantic import BaseModel, Field


class UsernameSearchRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=256)
    timeout_per_tool: float = Field(default=120.0, ge=10.0, le=600.0)
    tools: list[str] | None = Field(
        default=None,
        description="Override default tools. Options: sherlock, maigret, whatsmyname, social_analyzer",
    )


class EmailIntelRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    timeout_per_tool: float = Field(default=120.0, ge=10.0, le=600.0)
    tools: list[str] | None = Field(
        default=None,
        description="Override default tools. Options: holehe, theharvester, spiderfoot",
    )


class DomainIntelRequest(BaseModel):
    domain: str = Field(..., min_length=1, max_length=253)
    timeout_per_tool: float = Field(default=180.0, ge=10.0, le=600.0)
    tools: list[str] | None = Field(
        default=None,
        description="Override default tools. Options: theharvester, spiderfoot, recon_ng",
    )


class InfraIntelRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    timeout_per_tool: float = Field(default=60.0, ge=10.0, le=300.0)
    tools: list[str] | None = Field(
        default=None,
        description="Override default tools. Options: shodan",
    )


class ImageIntelRequest(BaseModel):
    image_url: str | None = Field(default=None, max_length=2048)
    image_path: str | None = Field(default=None, max_length=1024)
    timeout_per_tool: float = Field(default=60.0, ge=10.0, le=300.0)


class CorrelationRequest(BaseModel):
    seed_query: str = Field(default="", max_length=512, description="Anchor username/email for correlation")
    entities: list[dict] = Field(
        default_factory=list,
        description="Normalized fusion entities (type, value, sources, metadata). Can be empty.",
    )

    model_config = {"json_schema_extra": {"examples": [{"seed_query": "manojyadavnr", "entities": []}]}}


class GraphIntelRequest(BaseModel):
    seed_query: str = Field(default="", max_length=512)
    entities: list[dict] = Field(default_factory=list)
    clusters: list[dict] = Field(default_factory=list, description="Correlation clusters from prior step")
