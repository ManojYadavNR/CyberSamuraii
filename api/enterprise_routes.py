"""Case management and enterprise dashboard API."""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from api.deps import client_ip, get_current_user, require_permission
from schemas.enterprise import (
    ApprovalDecision,
    ApprovalSubmit,
    AssignCaseRequest,
    BookmarkCreate,
    CaseCreate,
    CaseOut,
    CaseUpdate,
    CommentCreate,
    EvidenceMarkRequest,
    NoteCreate,
    PasswordChange,
    PinCreate,
    ReportRequest,
    TaskCreate,
    UserCreate,
    UserIdsPreview,
    UserPublic,
    UserUpdate,
    WorkspaceNote,
)
from services.enterprise.approvals import decide_approval, list_approvals, list_pending_for_role, submit_for_review
from services.enterprise.cases import (
    archive_case,
    assign_case,
    create_case,
    dashboard_metrics,
    get_case,
    get_case_detail,
    link_investigation,
    list_cases,
    transfer_case,
    update_case,
)
from services.enterprise.evidence_governance import archive_evidence, list_evidence, mark_evidence_important, record_evidence
from services.enterprise.reports import generate_case_report
from services.enterprise.workspace import (
    activity_feed,
    add_bookmark,
    add_comment,
    add_note as ws_add_note,
    add_pin,
    create_task,
    list_bookmarks,
    list_comments,
    list_notes as ws_list_notes,
    list_pins,
    list_tasks,
    update_task_status,
)
from services.enterprise.users import change_password, create_user, list_users, preview_next_user_ids, resolve_user_avatar_path, save_user_avatar, update_user
from services.enterprise.audit import (
    case_activity_history,
    export_audit_csv,
    get_audit_log,
    list_audit_logs,
    log_audit,
    user_activity_history,
    verify_hash_chain,
)

router = APIRouter(prefix="/api/enterprise", tags=["enterprise"])


@router.get("/users/next-ids", response_model=UserIdsPreview)
async def users_next_ids(user=Depends(require_permission("manage_users"))):
    return UserIdsPreview(**preview_next_user_ids())


@router.get("/users", response_model=list[UserPublic])
async def users_list(user=Depends(require_permission("manage_users"))):
    return [UserPublic(**row) for row in list_users()]


@router.post("/users", response_model=UserPublic)
async def users_create(body: UserCreate, request: Request, user=Depends(require_permission("manage_users"))):
    try:
        row = create_user(
            username=body.username,
            password=body.password,
            name=body.name,
            email=body.email,
            role=body.role,
            department=body.department,
            designation=body.designation,
            employee_id=body.employee_id,
            badge_number=body.badge_number,
            actor_id=user.user_id,
            actor_username=user.username,
            ip=client_ip(request),
        )
        return UserPublic(**row)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/users/{target_user_id}", response_model=UserPublic)
async def users_update(
    target_user_id: str,
    body: UserUpdate,
    request: Request,
    user=Depends(require_permission("manage_users")),
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        row = update_user(
            user_id=target_user_id,
            actor_id=user.user_id,
            actor_username=user.username,
            actor_role=user.role,
            ip=client_ip(request),
            **updates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublic(**row)


@router.post("/users/me/password")
async def users_change_password(body: PasswordChange, request: Request, user=Depends(get_current_user)):
    try:
        ok = change_password(
            user_id=user.user_id,
            current_password=body.current_password,
            new_password=body.new_password,
            ip=client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    return {"ok": True}


@router.post("/users/me/avatar", response_model=UserPublic)
async def users_upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    content = await file.read()
    row = save_user_avatar(
        user_id=user.user_id,
        content=content,
        content_type=file.content_type or "",
        ip=client_ip(request),
    )
    if not row:
        raise HTTPException(status_code=400, detail="Invalid image — use JPEG, PNG, WebP, or GIF under 2.5MB")
    return UserPublic(**row)


@router.get("/users/{target_user_id}/avatar")
async def users_get_avatar(target_user_id: str):
    path = resolve_user_avatar_path(target_user_id)
    if not path:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return FileResponse(path)


@router.get("/dashboard/metrics")
async def metrics(user=Depends(get_current_user)):
    return dashboard_metrics()


@router.get("/cases", response_model=list[CaseOut])
async def cases_list(user=Depends(require_permission("view_cases"))):
    if user.can("*"):
        rows = list_cases(limit=100)
    else:
        rows = list_cases(user_id=user.user_id, limit=100)
    return [CaseOut(**r) for r in rows]


@router.post("/cases", response_model=CaseOut)
async def cases_create(body: CaseCreate, request: Request, user=Depends(require_permission("create_case"))):
    row = create_case(
        title=body.title,
        description=body.description,
        priority=body.priority,
        created_by=user.user_id,
        username=user.username,
        ip=client_ip(request),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create case")
    return CaseOut(**row)


@router.get("/cases/{case_id}", response_model=CaseOut)
async def cases_get(case_id: str, user=Depends(require_permission("view_cases"))):
    row = get_case(case_id)
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut(**row)


@router.patch("/cases/{case_id}", response_model=CaseOut)
async def cases_update(case_id: str, body: CaseUpdate, request: Request, user=Depends(require_permission("edit_case"))):
    updates = body.model_dump(exclude_unset=True)
    row = update_case(case_id, updates=updates, actor_id=user.user_id, username=user.username, ip=client_ip(request))
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut(**row)


@router.post("/cases/{case_id}/close", response_model=CaseOut)
async def cases_close(case_id: str, request: Request, user=Depends(require_permission("close_case"))):
    row = update_case(case_id, updates={"status": "CLOSED"}, actor_id=user.user_id, username=user.username, ip=client_ip(request))
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut(**row)


@router.post("/cases/{case_id}/archive", response_model=CaseOut)
async def cases_archive(case_id: str, request: Request, user=Depends(require_permission("close_case"))):
    from datetime import datetime, timezone

    row = update_case(
        case_id,
        updates={"status": "ARCHIVED", "archived_at": datetime.now(timezone.utc)},
        actor_id=user.user_id,
        username=user.username,
        ip=client_ip(request),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut(**row)


@router.post("/cases/{case_id}/investigations/{investigation_id}")
async def link_inv(case_id: str, investigation_id: str, query: str = "", user=Depends(require_permission("start_investigation"))):
    link_investigation(case_id=case_id, investigation_id=investigation_id, started_by=user.user_id, query=query)
    log_audit(user_id=user.user_id, username=user.username, action="link_investigation", entity=f"{case_id}:{investigation_id}")
    return {"ok": True}


@router.get("/audit")
async def audit_list(
    user=Depends(require_permission("view_audit_logs")),
    limit: int = 100,
    offset: int = 0,
    user_id: str = "",
    username: str = "",
    role: str = "",
    case_id: str = "",
    investigation_id: str = "",
    category: str = "",
    action: str = "",
    risk_level: str = "",
    result: str = "",
    search: str = "",
    date_from: str = "",
    date_to: str = "",
    suspicious_only: bool = False,
):
    data = list_audit_logs(
        limit=min(limit, 500),
        offset=offset,
        user_id=user_id,
        username=username,
        role=role,
        case_id=case_id,
        investigation_id=investigation_id,
        category=category,
        action=action,
        risk_level=risk_level,
        result=result,
        search=search,
        date_from=date_from,
        date_to=date_to,
        suspicious_only=suspicious_only,
    )
    return data


@router.get("/audit/export/csv", response_class=PlainTextResponse)
async def audit_export_csv(
    request: Request,
    user=Depends(require_permission("view_audit_logs")),
    category: str = "",
    case_id: str = "",
    user_id: str = "",
    date_from: str = "",
    date_to: str = "",
    suspicious_only: bool = False,
):
    csv_data = export_audit_csv(
        category=category,
        case_id=case_id,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        suspicious_only=suspicious_only,
    )
    log_audit(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        action="export_audit_report",
        entity="audit",
        entity_type="report",
        result="success",
        risk_level="critical",
        ip=client_ip(request),
        request=request,
    )
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_report.csv"},
    )


@router.get("/audit/verify/chain")
async def audit_verify_chain(user=Depends(require_permission("view_audit_logs")), limit: int = 500):
    from services.enterprise.audit import ensure_audit_chain_integrity, verify_hash_chain
    result = verify_hash_chain(limit=limit)
    if not result.get("valid"):
        repaired = ensure_audit_chain_integrity()
        result = verify_hash_chain(limit=limit)
        result["repaired"] = repaired.get("rebuilt", 0)
    return result


@router.get("/audit/users/{target_user_id}/history")
async def audit_user_history(target_user_id: str, user=Depends(require_permission("view_audit_logs")), limit: int = 100):
    return {"logs": user_activity_history(target_user_id, limit=limit)}


@router.get("/audit/cases/{case_id}/history")
async def audit_case_history(case_id: str, user=Depends(require_permission("view_audit_logs")), limit: int = 100):
    return {"logs": case_activity_history(case_id, limit=limit)}


@router.get("/audit/{log_id}")
async def audit_detail(log_id: str, user=Depends(require_permission("view_audit_logs"))):
    row = get_audit_log(log_id)
    if not row:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    return row


@router.get("/cases/{case_id}/detail")
async def cases_detail(case_id: str, user=Depends(require_permission("view_cases"))):
    row = get_case_detail(case_id)
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return row


@router.post("/cases/{case_id}/assign", response_model=CaseOut)
async def cases_assign(case_id: str, body: AssignCaseRequest, request: Request, user=Depends(require_permission("assign_case"))):
    row = assign_case(case_id, assigned_to=body.assigned_to, actor_id=user.user_id, username=user.username, ip=client_ip(request))
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut(**row)


@router.post("/cases/{case_id}/transfer", response_model=CaseOut)
async def cases_transfer(case_id: str, body: AssignCaseRequest, request: Request, user=Depends(require_permission("assign_case"))):
    row = transfer_case(case_id, assigned_to=body.assigned_to, actor_id=user.user_id, username=user.username, ip=client_ip(request))
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut(**row)


@router.delete("/cases/{case_id}")
async def cases_delete(case_id: str, request: Request, user=Depends(require_permission("delete_case"))):
    row = archive_case(case_id, actor_id=user.user_id, username=user.username, ip=client_ip(request))
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut(**row)


@router.get("/cases/{case_id}/notes", response_model=list[WorkspaceNote])
async def list_notes(case_id: str, user=Depends(require_permission("view_cases"))):
    return [
        WorkspaceNote(note_id=n["note_id"], case_id=n["case_id"], author_id=n["author_id"], author_name="", content=n["content"], created_at=n["created_at"], pinned=n["pinned"])
        for n in ws_list_notes(case_id)
    ]


@router.post("/cases/{case_id}/notes", response_model=WorkspaceNote)
async def add_note(case_id: str, body: NoteCreate, user=Depends(require_permission("edit_case"))):
    row = ws_add_note(case_id=case_id, author_id=user.user_id, content=body.content, pinned=body.pinned)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to add note")
    return WorkspaceNote(note_id=row["note_id"], case_id=row["case_id"], author_id=row["author_id"], author_name=user.name or user.username, content=row["content"], created_at=row["created_at"], pinned=row["pinned"])


@router.get("/cases/{case_id}/comments")
async def case_comments(case_id: str, user=Depends(require_permission("view_cases"))):
    return {"comments": list_comments(case_id)}


@router.post("/cases/{case_id}/comments")
async def case_add_comment(case_id: str, body: CommentCreate, user=Depends(require_permission("edit_case"))):
    row = add_comment(case_id=case_id, author_id=user.user_id, author_name=user.name or user.username, content=body.content)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to add comment")
    return row


@router.get("/cases/{case_id}/tasks")
async def case_tasks(case_id: str, user=Depends(require_permission("view_cases"))):
    return {"tasks": list_tasks(case_id)}


@router.post("/cases/{case_id}/tasks")
async def case_create_task(case_id: str, body: TaskCreate, user=Depends(require_permission("edit_case"))):
    row = create_task(case_id=case_id, title=body.title, description=body.description, assigned_to=body.assigned_to, created_by=user.user_id, actor_name=user.name or user.username)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create task")
    return row


@router.patch("/cases/{case_id}/tasks/{task_id}")
async def case_update_task(case_id: str, task_id: str, status: str, user=Depends(require_permission("edit_case"))):
    row = update_task_status(task_id, status)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return row


@router.get("/cases/{case_id}/bookmarks")
async def case_bookmarks(case_id: str, user=Depends(require_permission("view_cases"))):
    return {"bookmarks": list_bookmarks(case_id)}


@router.post("/cases/{case_id}/bookmarks")
async def case_add_bookmark(case_id: str, body: BookmarkCreate, user=Depends(require_permission("edit_case"))):
    row = add_bookmark(case_id=case_id, user_id=user.user_id, entity_id=body.entity_id, entity_label=body.entity_label, entity_type=body.entity_type)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to bookmark")
    return row


@router.get("/cases/{case_id}/pins")
async def case_pins(case_id: str, user=Depends(require_permission("view_cases"))):
    return {"pins": list_pins(case_id)}


@router.post("/cases/{case_id}/pins")
async def case_add_pin(case_id: str, body: PinCreate, user=Depends(require_permission("edit_case"))):
    row = add_pin(case_id=case_id, user_id=user.user_id, finding_key=body.finding_key, finding_label=body.finding_label, finding_data=body.finding_data)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to pin")
    return row


@router.get("/cases/{case_id}/activity")
async def case_activity(case_id: str, user=Depends(require_permission("view_cases"))):
    return {"activity": activity_feed(case_id)}


@router.get("/cases/{case_id}/evidence")
async def case_evidence(case_id: str, user=Depends(require_permission("view_cases"))):
    return {"evidence": list_evidence(case_id)}


@router.post("/cases/{case_id}/evidence/{evidence_id}/important")
async def case_evidence_important(case_id: str, evidence_id: str, body: EvidenceMarkRequest, user=Depends(require_permission("approve_evidence"))):
    row = mark_evidence_important(evidence_id, body.important)
    if not row:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return row


@router.post("/cases/{case_id}/evidence/{evidence_id}/archive")
async def case_evidence_archive(case_id: str, evidence_id: str, request: Request, user=Depends(require_permission("approve_evidence"))):
    row = archive_evidence(evidence_id, actor_id=user.user_id, username=user.username)
    if not row:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return row


@router.post("/cases/{case_id}/approvals/submit")
async def case_submit_approval(case_id: str, body: ApprovalSubmit, user=Depends(require_permission("start_investigation"))):
    row = submit_for_review(case_id=case_id, investigation_id=body.investigation_id, cluster_id=body.cluster_id, submitter_id=user.user_id, submitter_name=user.name or user.username, notes=body.notes)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to submit")
    return row


@router.get("/cases/{case_id}/approvals")
async def case_approvals(case_id: str, user=Depends(require_permission("view_cases"))):
    return {"approvals": list_approvals(case_id=case_id)}


@router.post("/approvals/{approval_id}/decide")
async def approval_decide(approval_id: str, body: ApprovalDecision, user=Depends(require_permission("approve_evidence"))):
    try:
        row = decide_approval(approval_id=approval_id, decision=body.decision, reviewer_id=user.user_id, reviewer_name=user.name or user.username, reviewer_role=user.role, notes=body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")
    return row


@router.get("/approvals/pending")
async def approvals_pending(user=Depends(get_current_user)):
    return {"approvals": list_pending_for_role(user.role)}


@router.post("/cases/{case_id}/report")
async def case_report(case_id: str, body: ReportRequest, user=Depends(require_permission("export_evidence"))):
    report = generate_case_report(case_id, format=body.format)
    if not report:
        raise HTTPException(status_code=404, detail="Case not found")
    log_audit(user_id=user.user_id, username=user.username, action="export_case_report", entity=case_id)
    return report


@router.get("/agencies")
async def agencies_list(user=Depends(get_current_user)):
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "config" / "agencies.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"agencies": []}
