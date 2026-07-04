from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
import re

from api.deps import CurrentUser, get_optional_user, require_permission
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
from services.enterprise.db import enterprise_enabled
from services.graph_intelligence.engine import graph_engine
from services.image_upload import resolve_upload_path, save_upload
from services.face_crops import resolve_crop_path
from services.screenshot_store import resolve_screenshot_path

router = APIRouter(prefix="/api/intel", tags=["intelligence"])

_intel_run = require_permission("start_investigation")
_intel_view = require_permission("view_investigations")


async def _media_access(user: CurrentUser | None = Depends(get_optional_user)) -> CurrentUser | None:
    if enterprise_enabled() and not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.post("/username-search")
async def username_search(
    request: UsernameSearchRequest,
    user=Depends(_intel_run),
):
    result = await orchestrator.execute_username_search(
        username=request.username,
        timeout=request.timeout_per_tool,
        tools=request.tools,
    )
    return result.model_dump()


@router.post("/email")
async def email_intel(request: EmailIntelRequest, user=Depends(_intel_run)):
    result = await orchestrator.execute_email_intel(
        email=request.email,
        timeout=request.timeout_per_tool,
        tools=request.tools,
    )
    return result.model_dump()


@router.post("/domain")
async def domain_intel(request: DomainIntelRequest, user=Depends(_intel_run)):
    result = await orchestrator.execute_domain_intel(
        domain=request.domain,
        timeout=request.timeout_per_tool,
        tools=request.tools,
    )
    return result.model_dump()


@router.post("/infra")
async def infra_intel(request: InfraIntelRequest, user=Depends(_intel_run)):
    result = await orchestrator.execute_infra_intel(
        query=request.query,
        timeout=request.timeout_per_tool,
        tools=request.tools,
    )
    return result.model_dump()


@router.post("/image/upload")
async def upload_image(file: UploadFile = File(...), user=Depends(_intel_run)):
    """Upload an image file for investigation (multipart form field: file)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if f".{ext}" not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        raise HTTPException(status_code=400, detail="Supported formats: jpg, jpeg, png, gif, webp")
    content = await file.read()
    try:
        saved = save_upload(content, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return saved


@router.get("/image/uploads/{image_id}")
async def get_uploaded_image(image_id: str, user=Depends(_media_access)):
    path = resolve_upload_path(image_id)
    if not path:
        raise HTTPException(status_code=404, detail="upload not found")
    return FileResponse(path)


@router.get("/screenshots/{screenshot_id}")
async def get_page_screenshot(screenshot_id: str, user=Depends(_media_access)):
    path = resolve_screenshot_path(screenshot_id)
    if not path:
        raise HTTPException(status_code=404, detail="screenshot not found")
    return FileResponse(path, media_type="image/png")


@router.get("/image/crops/{upload_id}/{crop_name}")
async def get_face_crop(upload_id: str, crop_name: str, user=Depends(_media_access)):
    path = resolve_crop_path(upload_id, crop_name)
    if not path:
        raise HTTPException(status_code=404, detail="face crop not found")
    return FileResponse(path)


@router.get("/media-proxy")
async def proxy_external_media(url: str = Query(...), user=Depends(_media_access)):
    """Proxy hotlinked images and short video clips for in-app previews."""
    import httpx

    from services.discovery.validators import is_branding_image_url, is_proxiable_media_url
    from services.media_proxy_fetch import proxy_fetch_headers

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="invalid media url")

    if not is_proxiable_media_url(url) or is_branding_image_url(url):
        raise HTTPException(status_code=400, detail="url is not a displayable image or video")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            response = await client.get(url, headers=proxy_fetch_headers(url))
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="media fetch failed") from exc

    content_type = response.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
    if content_type.startswith("image/") or content_type.startswith("video/"):
        return Response(content=response.content, media_type=content_type)
    if url.lower().endswith(".mp4"):
        return Response(content=response.content, media_type="video/mp4")
    raise HTTPException(status_code=400, detail="remote response is not displayable media")


def _lookaside_proxy_candidates(url: str) -> list[str]:
    """Facebook lookaside often serves HTML for full-size URLs — try thumbnail first."""
    low = url.lower()
    if "lookaside.fbsbx.com" not in low:
        return [url]
    candidates = [url]
    if "get_thumbnail=1" not in low:
        sep = "&" if "?" in url else "?"
        candidates.insert(0, f"{url}{sep}get_thumbnail=1")
    else:
        full = re.sub(r"[?&]get_thumbnail=1", "", url).rstrip("?&")
        if full and full not in candidates:
            candidates.append(full)
    return candidates


@router.get("/image-proxy")
async def proxy_external_image(url: str = Query(...), user=Depends(_media_access)):
    """Proxy hotlinked profile/post images — supports ?token= for <img> tags."""
    import httpx

    from services.discovery.validators import is_branding_image_url, is_image_url
    from services.media_proxy_fetch import proxy_fetch_headers

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="invalid image url")
    if not is_image_url(url) or is_branding_image_url(url):
        raise HTTPException(status_code=400, detail="url is not a displayable image")

    last_error: Exception | None = None
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
            for try_url in _lookaside_proxy_candidates(url):
                try:
                    response = await client.get(try_url, headers=proxy_fetch_headers(try_url))
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    last_error = exc
                    continue
                content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                if content_type.startswith("image/"):
                    return Response(content=response.content, media_type=content_type)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="image fetch failed") from exc

    if last_error:
        raise HTTPException(status_code=502, detail="image fetch failed") from last_error
    raise HTTPException(status_code=400, detail="remote response is not an image")


@router.post("/image")
async def image_intel(request: ImageIntelRequest, user=Depends(_intel_run)):
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
    user=Depends(_intel_run),
    request: CorrelationRequest = Body(
        default_factory=CorrelationRequest,
        examples={
            "sample": {
                "summary": "Correlate two accounts",
                "value": {
                    "seed_query": "targetuser",
                    "entities": [
                        {
                            "type": "account",
                            "value": "profiles.example.org/targetuser",
                            "sources": ["sherlock", "maigret"],
                            "metadata": {
                                "platform": "profiles.example.org",
                                "verified": True,
                                "url": "https://profiles.example.org/user/targetuser",
                            },
                            "fusion_score": 0.95,
                        },
                        {
                            "type": "account",
                            "value": "community.example.org/targetuser",
                            "sources": ["sherlock"],
                            "metadata": {
                                "platform": "community.example.org",
                                "verified": True,
                                "url": "https://community.example.org/u/targetuser",
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
async def graph_intelligence(request: GraphIntelRequest, user=Depends(_intel_run)):
    """Build graph intelligence from fusion entities and correlation clusters."""
    entities = [Entity(**e) for e in request.entities]
    fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
    clusters = [AccountCluster(**c) for c in request.clusters]
    correlation = CorrelationOutput(clusters=clusters, total_accounts_analyzed=len(entities), total_clusters=len(clusters))
    output = graph_engine.analyze(fusion, correlation, seed_query=request.seed_query)
    return output.model_dump()
