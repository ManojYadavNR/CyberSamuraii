"""Dashboard API — unified investigation, review, copilot, export."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.deps import client_ip, get_current_user, require_permission
from schemas.dashboard import CopilotRequest, ExportRequest, InvestigateRequest, ReviewRequest
from schemas.discovery import DiscoveryConfig
from services.copilot import answer_copilot_async, stream_copilot_events
from services.enterprise.audit import log_audit
from services.enterprise.cases import link_investigation
from services.enterprise.db import enterprise_enabled
from services.enterprise.security import check_rate_limit
from services.export_report import generate_report
from services.investigation_runner import _dump_result, get_investigation, investigation_runner
from services.query_detector import detect_query_type
from services.resource_guard import InvestigationBusyError
from services.review_store import get_reviews, submit_review

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.post("/investigate")
async def start_investigation(
    request: InvestigateRequest,
    http_request: Request,
    user=Depends(require_permission("start_investigation")),
):
    """Start investigation synchronously (use WebSocket for live progress)."""
    ip = client_ip(http_request)
    if not check_rate_limit(ip, "/api/dashboard/investigate"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if enterprise_enabled() and not request.case_id:
        raise HTTPException(status_code=400, detail="case_id required — every investigation must belong to a case")
    try:
        investigation_id, result = await investigation_runner.run(
            query=request.query,
            query_type=request.query_type,
            timeout_per_tool=request.timeout_per_tool,
            discovery_config=request.discovery or DiscoveryConfig(),
            investigation_mode=request.investigation_mode,
        )
    except InvestigationBusyError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if enterprise_enabled() and request.case_id:
        link_investigation(
            case_id=request.case_id,
            investigation_id=investigation_id,
            started_by=user.user_id,
            query=request.query,
        )
    log_audit(
        user_id=user.user_id,
        username=user.username,
        action="start_investigation",
        entity=investigation_id,
        ip=client_ip(http_request),
        details={"query": request.query, "case_id": request.case_id},
    )
    return {
        "investigation_id": investigation_id,
        "query_type": request.query_type or detect_query_type(request.query),
        "result": _dump_result(result),
    }


@router.get("/investigations/{investigation_id}")
async def get_investigation_result(investigation_id: str, user=Depends(require_permission("view_investigations"))):
    inv = get_investigation(investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv


@router.post("/review")
async def review_cluster(request: ReviewRequest, user=Depends(require_permission("approve_evidence"))):
    record = submit_review(
        investigation_id=request.investigation_id,
        cluster_id=request.cluster_id,
        decision=request.decision,
        reviewer=user.username or request.reviewer,
        notes=request.notes,
    )
    log_audit(user_id=user.user_id, username=user.username, action="review_cluster", entity=request.cluster_id)
    return record


@router.get("/review/{investigation_id}")
async def list_reviews(investigation_id: str, user=Depends(require_permission("view_investigations"))):
    return {"investigation_id": investigation_id, "reviews": get_reviews(investigation_id)}


@router.post("/investigate/cancel")
async def cancel_running_investigation(user=Depends(require_permission("start_investigation"))):
    from services.investigation_cancel import active_investigation_id, cancel_investigation

    inv_id = active_investigation_id()
    if not inv_id or not cancel_investigation(inv_id):
        return {"cancelled": False, "message": "No running investigation to stop"}
    return {"cancelled": True, "investigation_id": inv_id}


@router.post("/copilot/prewarm")
async def copilot_prewarm(user=Depends(require_permission("view_investigations"))):
    from services.copilot_llm import copilot_model, ollama_available, prewarm_copilot_model

    online = await ollama_available()
    warmed = await prewarm_copilot_model(force=True) if online else False
    return {
        "ollama_online": online,
        "model": copilot_model(),
        "warmed": warmed,
    }


@router.get("/copilot/status")
async def copilot_status(user=Depends(require_permission("view_investigations"))):
    from services.copilot_llm import copilot_model, ollama_available

    online = await ollama_available()
    return {
        "ollama_online": online,
        "model": copilot_model(),
        "auto_start": False,
        "hint": (
            "Ollama does not auto-start. Run once in a terminal: ollama serve"
            if not online
            else f"{copilot_model()} is ready"
        ),
    }


def _copilot_context_from_request(request: CopilotRequest) -> dict:
    """Build copilot context — prefers case-wide scope when case_id is present."""
    context = dict(request.context or {})
    if request.case_id:
        context["case_id"] = request.case_id
    if request.investigation_id:
        context["investigation_id"] = request.investigation_id
        inv = get_investigation(request.investigation_id)
        if inv and inv.get("result"):
            context.setdefault("result", inv["result"])
            context.setdefault("query", inv.get("query", ""))
        # Recover case_id from the investigation record when the client omitted it.
        if not context.get("case_id") and inv:
            linked_case = inv.get("case_id") or (inv.get("result") or {}).get("case_id")
            if linked_case:
                context["case_id"] = linked_case
    return context


@router.post("/copilot")
async def copilot_chat(request: CopilotRequest, user=Depends(require_permission("view_investigations"))):
    context = _copilot_context_from_request(request)
    response = await answer_copilot_async(request.message, context)
    return {"message": request.message, **response}


@router.post("/copilot/stream")
async def copilot_chat_stream(request: CopilotRequest, user=Depends(require_permission("view_investigations"))):
    context = _copilot_context_from_request(request)

    async def event_stream():
        async for event in stream_copilot_events(request.message, context):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/export")
async def export_report(request: ExportRequest, http_request: Request, user=Depends(require_permission("export_evidence"))):
    result = request.result
    if not result and request.investigation_id:
        inv = get_investigation(request.investigation_id)
        if inv:
            result = inv.get("result", {})
    if not result:
        raise HTTPException(status_code=400, detail="No investigation result to export")
    report = generate_report(
        investigation_id=request.investigation_id,
        query=request.query,
        result=result,
        reviewer=user.username or request.reviewer,
        include_graph=request.include_graph,
    )
    log_audit(
        user_id=user.user_id,
        username=user.username,
        action="export_evidence",
        entity=request.investigation_id,
        ip=client_ip(http_request),
    )
    if enterprise_enabled() and getattr(request, "case_id", None):
        from services.enterprise.evidence_governance import record_evidence

        record_evidence(
            case_id=request.case_id,
            investigation_id=request.investigation_id or "",
            source="export",
            collector_id=user.user_id,
            payload=report,
            label=f"Export: {request.query or request.investigation_id}",
            username=user.username,
        )
    return report
