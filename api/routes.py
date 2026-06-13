from fastapi import APIRouter, Body, HTTPException

from orchestrator.engine import orchestrator
from schemas.correlation import AccountCluster, CorrelationOutput
from schemas.features import (
    CorrelationRequest,
    DomainIntelRequest,
    EmailIntelRequest,
    GraphIntelRequest,
    ImageIntelRequest,
    InfraIntelRequest,
    UsernameSearchRequest,
)
from schemas.fusion import Entity, FusionOutput
from services.correlation.engine import correlation_engine
from services.graph_intelligence.engine import graph_engine

router = APIRouter(prefix="/api/intel", tags=["intelligence"])


@router.post("/username-search")
async def username_search(request: UsernameSearchRequest):
    result = await orchestrator.execute_username_search(
        username=request.username,
        timeout=request.timeout_per_tool,
        tools=request.tools,
    )
    return result.model_dump()


@router.post("/email")
async def email_intel(request: EmailIntelRequest):
    result = await orchestrator.execute_email_intel(
        email=request.email,
        timeout=request.timeout_per_tool,
        tools=request.tools,
    )
    return result.model_dump()


@router.post("/domain")
async def domain_intel(request: DomainIntelRequest):
    result = await orchestrator.execute_domain_intel(
        domain=request.domain,
        timeout=request.timeout_per_tool,
        tools=request.tools,
    )
    return result.model_dump()


@router.post("/infra")
async def infra_intel(request: InfraIntelRequest):
    result = await orchestrator.execute_infra_intel(
        query=request.query,
        timeout=request.timeout_per_tool,
        tools=request.tools,
    )
    return result.model_dump()


@router.post("/image")
async def image_intel(request: ImageIntelRequest):
    source = request.image_url or request.image_path
    if not source:
        raise HTTPException(status_code=400, detail="Provide image_url or image_path")
    result = await orchestrator.execute_image_intel(
        source=source,
        timeout=request.timeout_per_tool,
    )
    return result.model_dump()


@router.post("/correlate")
async def correlate_identities(
    request: CorrelationRequest = Body(
        default_factory=CorrelationRequest,
        examples={
            "sample": {
                "summary": "Correlate two accounts",
                "value": {
                    "seed_query": "manojyadavnr",
                    "entities": [
                        {
                            "type": "account",
                            "value": "github.com/manojyadavnr",
                            "sources": ["sherlock", "maigret"],
                            "metadata": {
                                "platform": "github.com",
                                "verified": True,
                                "url": "https://github.com/manojyadavnr",
                            },
                            "fusion_score": 0.95,
                        },
                        {
                            "type": "account",
                            "value": "twitter.com/manojyadavnr",
                            "sources": ["sherlock"],
                            "metadata": {
                                "platform": "twitter.com",
                                "verified": True,
                                "url": "https://twitter.com/manojyadavnr",
                            },
                            "fusion_score": 0.92,
                        },
                    ],
                },
            }
        },
    ),
):
    """Run identity correlation on fusion entities directly."""
    if not request.entities:
        raise HTTPException(
            status_code=400,
            detail="Provide 'entities' array in JSON body. See POST /api/intel/username-search for fusion output.",
        )
    entities = [Entity(**e) for e in request.entities]
    fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
    output = await correlation_engine.correlate(fusion, seed_query=request.seed_query)
    return output.model_dump()


@router.post("/graph")
async def graph_intelligence(request: GraphIntelRequest):
    """Build graph intelligence from fusion entities and correlation clusters."""
    entities = [Entity(**e) for e in request.entities]
    fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
    clusters = [AccountCluster(**c) for c in request.clusters]
    correlation = CorrelationOutput(clusters=clusters, total_accounts_analyzed=len(entities), total_clusters=len(clusters))
    output = graph_engine.analyze(fusion, correlation, seed_query=request.seed_query)
    return output.model_dump()
