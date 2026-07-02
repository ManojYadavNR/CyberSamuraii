"""Case management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.enterprise.audit import log_audit
from services.enterprise.db import get_session, new_id

_CASE_SEQ = 0


def _next_case_number(session) -> str:
    global _CASE_SEQ
    from services.enterprise.db import _MODELS

    Case = _MODELS["Case"]
    year = datetime.now(timezone.utc).year
    count = session.query(Case).count() + 1
    _CASE_SEQ = max(_CASE_SEQ, count)
    return f"CASE-{year}-{count:05d}"


def _case_out(row) -> dict[str, Any]:
    return {
        "case_id": row.case_id,
        "case_number": row.case_number,
        "title": row.title,
        "description": row.description or "",
        "priority": row.priority,
        "status": row.status,
        "assigned_to": row.assigned_to,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def create_case(*, title: str, description: str, priority: str, created_by: str, username: str = "", ip: str = "") -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        Case = _MODELS["Case"]
        row = Case(
            case_id=new_id(),
            case_number=_next_case_number(session),
            title=title.strip(),
            description=description.strip(),
            priority=priority,
            status="OPEN",
            created_by=created_by,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        log_audit(user_id=created_by, username=username, action="create_case", entity=row.case_number, ip=ip)
        return _case_out(row)
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def list_cases(*, user_id: str | None = None, limit: int = 50) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        Case = _MODELS["Case"]
        q = session.query(Case).filter(Case.archived_at.is_(None))
        if user_id:
            q = q.filter((Case.created_by == user_id) | (Case.assigned_to == user_id))
        rows = q.order_by(Case.created_at.desc()).limit(limit).all()
        return [_case_out(r) for r in rows]
    finally:
        session.close()


def get_case(case_id: str) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = session.query(_MODELS["Case"]).filter_by(case_id=case_id).first()
        return _case_out(row) if row else None
    finally:
        session.close()


def update_case(case_id: str, *, updates: dict, actor_id: str, username: str = "", ip: str = "") -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        Case = _MODELS["Case"]
        row = session.query(Case).filter_by(case_id=case_id).first()
        if not row:
            return None
        for key, val in updates.items():
            if val is not None and hasattr(row, key):
                setattr(row, key, val)
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
        log_audit(user_id=actor_id, username=username, action="edit_case", entity=row.case_number, ip=ip, details=updates)
        return _case_out(row)
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def link_investigation(*, case_id: str, investigation_id: str, started_by: str, query: str = "") -> None:
    session = get_session()
    if not session:
        return
    try:
        from services.enterprise.db import _MODELS

        CI = _MODELS["CaseInvestigation"]
        session.add(
            CI(
                id=new_id(),
                case_id=case_id,
                investigation_id=investigation_id,
                started_by=started_by,
                query=query,
            )
        )
        session.query(_MODELS["Case"]).filter_by(case_id=case_id).update({"status": "ACTIVE"})
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def list_case_investigations(case_id: str) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        rows = (
            session.query(_MODELS["CaseInvestigation"])
            .filter_by(case_id=case_id)
            .order_by(_MODELS["CaseInvestigation"].created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "case_id": r.case_id,
                "investigation_id": r.investigation_id,
                "started_by": r.started_by,
                "query": r.query or "",
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    finally:
        session.close()


def get_case_detail(case_id: str) -> dict | None:
    case = get_case(case_id)
    if not case:
        return None
    investigations = list_case_investigations(case_id)
    return {**case, "investigation_count": len(investigations), "investigations": investigations}


def assign_case(
    case_id: str,
    *,
    assigned_to: str,
    actor_id: str,
    username: str = "",
    ip: str = "",
) -> dict | None:
    from services.enterprise.notifications import notify_user

    row = update_case(case_id, updates={"assigned_to": assigned_to}, actor_id=actor_id, username=username, ip=ip)
    if row:
        notify_user(user_id=assigned_to, title="Case assigned", body=f"Case {row['case_number']} assigned to you", kind="assignment", case_id=case_id)
        log_audit(user_id=actor_id, username=username, action="assign_case", entity=row["case_number"], ip=ip, details={"assigned_to": assigned_to})
    return row


def transfer_case(
    case_id: str,
    *,
    assigned_to: str,
    actor_id: str,
    username: str = "",
    ip: str = "",
) -> dict | None:
    from services.enterprise.notifications import notify_user

    row = update_case(case_id, updates={"assigned_to": assigned_to, "status": "ACTIVE"}, actor_id=actor_id, username=username, ip=ip)
    if row:
        notify_user(user_id=assigned_to, title="Case transferred", body=f"Case {row['case_number']} transferred to you", kind="transfer", case_id=case_id)
        log_audit(user_id=actor_id, username=username, action="transfer_case", entity=row["case_number"], ip=ip, details={"assigned_to": assigned_to})
    return row


def archive_case(case_id: str, *, actor_id: str, username: str = "", ip: str = "") -> dict | None:
    from datetime import datetime, timezone

    return update_case(
        case_id,
        updates={"status": "ARCHIVED", "archived_at": datetime.now(timezone.utc)},
        actor_id=actor_id,
        username=username,
        ip=ip,
    )


def dashboard_metrics() -> dict[str, Any]:
    session = get_session()
    if not session:
        return {}
    try:
        from services.enterprise.db import _MODELS

        Case = _MODELS["Case"]
        AuditLog = _MODELS["AuditLog"]
        active = session.query(Case).filter(Case.status.in_(["OPEN", "ACTIVE", "UNDER_REVIEW", "ESCALATED"])).count()
        open_cases = session.query(Case).filter_by(status="OPEN").count()
        today = datetime.now(timezone.utc).date()
        inv_today = (
            session.query(_MODELS["CaseInvestigation"])
            .filter(_MODELS["CaseInvestigation"].created_at >= datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc))
            .count()
        )
        pending = session.query(_MODELS["ApprovalRecord"]).filter_by(decision="pending").count() if "ApprovalRecord" in _MODELS else session.query(Case).filter_by(status="UNDER_REVIEW").count()
        high = session.query(Case).filter(Case.priority == "CRITICAL", Case.status != "CLOSED").count()
        investigators_online = session.query(_MODELS["User"]).filter(_MODELS["User"].last_login.isnot(None)).count()
        recent = list_audit_short(session)
        work_queue = []
        if "ApprovalRecord" in _MODELS:
            approvals = (
                session.query(_MODELS["ApprovalRecord"])
                .filter_by(decision="pending")
                .order_by(_MODELS["ApprovalRecord"].created_at.desc())
                .limit(10)
                .all()
            )
            work_queue = [{"type": "approval", "id": a.approval_id, "case_id": a.case_id, "stage": a.stage} for a in approvals]
        return {
            "active_cases": active,
            "open_cases": open_cases,
            "investigations_today": inv_today,
            "pending_reviews": pending,
            "high_risk_targets": high,
            "investigators_online": investigators_online,
            "recent_activity": recent,
            "work_queue": work_queue,
        }
    finally:
        session.close()


def list_audit_short(session) -> list[dict]:
    from services.enterprise.db import _MODELS

    rows = session.query(_MODELS["AuditLog"]).order_by(_MODELS["AuditLog"].timestamp.desc()).limit(10).all()
    return [
        {"timestamp": r.timestamp.isoformat(), "user": r.username, "action": r.action, "entity": r.entity}
        for r in rows
    ]
