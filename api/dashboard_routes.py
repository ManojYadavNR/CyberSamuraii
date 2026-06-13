"""Dashboard API — unified investigation, review, copilot, export."""

from fastapi import APIRouter, HTTPException

from schemas.dashboard import CopilotRequest, ExportRequest, InvestigateRequest, ReviewRequest
from services.copilot import answer_copilot
from services.export_report import generate_report
from services.investigation_runner import get_investigation, investigation_runner
from services.query_detector import detect_query_type
from services.review_store import get_reviews, submit_review

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.post("/investigate")
async def start_investigation(request: InvestigateRequest):
    """Start investigation synchronously (use WebSocket for live progress)."""
    investigation_id, result = await investigation_runner.run(
        query=request.query,
        query_type=request.query_type,
        timeout_per_tool=request.timeout_per_tool,
    )
    return {
        "investigation_id": investigation_id,
        "query_type": request.query_type or detect_query_type(request.query),
        "result": result.model_dump(),
    }


@router.get("/investigations/{investigation_id}")
async def get_investigation_result(investigation_id: str):
    inv = get_investigation(investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv


@router.post("/review")
async def review_cluster(request: ReviewRequest):
    record = submit_review(
        investigation_id=request.investigation_id,
        cluster_id=request.cluster_id,
        decision=request.decision,
        reviewer=request.reviewer,
        notes=request.notes,
    )
    return record


@router.get("/review/{investigation_id}")
async def list_reviews(investigation_id: str):
    return {"investigation_id": investigation_id, "reviews": get_reviews(investigation_id)}


@router.post("/copilot")
async def copilot_chat(request: CopilotRequest):
    context = dict(request.context)
    if request.investigation_id:
        inv = get_investigation(request.investigation_id)
        if inv and inv.get("result"):
            context.setdefault("result", inv["result"])
            context.setdefault("query", inv.get("query", ""))
    response = answer_copilot(request.message, context)
    return {"message": request.message, **response}


@router.post("/export")
async def export_report(request: ExportRequest):
    result = request.result
    if not result and request.investigation_id:
        inv = get_investigation(request.investigation_id)
        if inv:
            result = inv.get("result", {})
    if not result:
        raise HTTPException(status_code=400, detail="No investigation result to export")
    reviews = get_reviews(request.investigation_id)
    return generate_report(
        investigation_id=request.investigation_id,
        query=request.query,
        result=result,
        reviewer=request.reviewer,
        reviews=reviews,
    )
