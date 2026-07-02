"""Approval workflow — Analyst → Inspector → DSP → SP."""

from __future__ import annotations

from typing import Any

from services.enterprise.audit import log_audit
from services.enterprise.db import get_session, new_id
from services.enterprise.notifications import notify_role

STAGES = ["INSPECTOR", "DSP", "SP"]
ROLE_FOR_STAGE = {"INSPECTOR": "INSPECTOR", "DSP": "DSP", "SP": "SP"}


def submit_for_review(
    *,
    case_id: str,
    investigation_id: str,
    cluster_id: str,
    submitter_id: str,
    submitter_name: str,
    notes: str = "",
) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = _MODELS["ApprovalRecord"](
            approval_id=new_id(),
            case_id=case_id,
            investigation_id=investigation_id,
            cluster_id=cluster_id,
            stage="INSPECTOR",
            decision="pending",
            reviewer_id="",
            reviewer_name=submitter_name,
            notes=notes or "Submitted for review",
        )
        session.add(row)
        session.query(_MODELS["Case"]).filter_by(case_id=case_id).update({"status": "UNDER_REVIEW"})
        session.commit()
        session.refresh(row)
        notify_role("INSPECTOR", title="Review requested", body=f"{submitter_name} submitted findings for review", case_id=case_id)
        log_audit(user_id=submitter_id, username=submitter_name, action="submit_review", entity=cluster_id, details={"case_id": case_id})
        return _approval_out(row)
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def decide_approval(
    *,
    approval_id: str,
    decision: str,
    reviewer_id: str,
    reviewer_name: str,
    reviewer_role: str,
    notes: str = "",
) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        ApprovalRecord = _MODELS["ApprovalRecord"]
        row = session.query(ApprovalRecord).filter_by(approval_id=approval_id).first()
        if not row:
            return None
        expected_role = ROLE_FOR_STAGE.get(row.stage, "")
        if expected_role and reviewer_role not in {expected_role, "SUPER_ADMIN", "CID_DIRECTOR"}:
            raise ValueError(f"Only {expected_role} can decide at this stage")
        row.decision = decision
        row.reviewer_id = reviewer_id
        row.reviewer_name = reviewer_name
        if notes:
            row.notes = notes
        if decision == "approved":
            idx = STAGES.index(row.stage) if row.stage in STAGES else -1
            if idx >= 0 and idx < len(STAGES) - 1:
                next_stage = STAGES[idx + 1]
                nxt = ApprovalRecord(
                    approval_id=new_id(),
                    case_id=row.case_id,
                    investigation_id=row.investigation_id,
                    cluster_id=row.cluster_id,
                    stage=next_stage,
                    decision="pending",
                    reviewer_name="",
                    notes=f"Escalated from {row.stage}",
                )
                session.add(nxt)
                notify_role(ROLE_FOR_STAGE[next_stage], title="Approval escalated", body=f"Review moved to {next_stage}", case_id=row.case_id)
            else:
                session.query(_MODELS["Case"]).filter_by(case_id=row.case_id).update({"status": "ACTIVE"})
        elif decision == "rejected":
            session.query(_MODELS["Case"]).filter_by(case_id=row.case_id).update({"status": "ACTIVE"})
        elif decision == "clarification":
            notify_role("ANALYST", title="Clarification requested", body=notes or "Please clarify findings", case_id=row.case_id)
        session.commit()
        session.refresh(row)
        log_audit(user_id=reviewer_id, username=reviewer_name, action=f"approval_{decision}", entity=approval_id)
        return _approval_out(row)
    except ValueError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def _approval_out(row) -> dict[str, Any]:
    return {
        "approval_id": row.approval_id,
        "case_id": row.case_id,
        "investigation_id": row.investigation_id,
        "cluster_id": row.cluster_id,
        "stage": row.stage,
        "decision": row.decision,
        "reviewer_id": row.reviewer_id,
        "reviewer_name": row.reviewer_name,
        "notes": row.notes or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def list_approvals(*, case_id: str | None = None, investigation_id: str | None = None) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        q = session.query(_MODELS["ApprovalRecord"])
        if case_id:
            q = q.filter_by(case_id=case_id)
        if investigation_id:
            q = q.filter_by(investigation_id=investigation_id)
        rows = q.order_by(_MODELS["ApprovalRecord"].created_at.desc()).all()
        return [_approval_out(r) for r in rows]
    finally:
        session.close()


def list_pending_for_role(role: str) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        stage = role if role in STAGES else None
        if not stage and role not in {"SUPER_ADMIN", "CID_DIRECTOR"}:
            return []
        q = session.query(_MODELS["ApprovalRecord"]).filter_by(decision="pending")
        if stage:
            q = q.filter_by(stage=stage)
        rows = q.order_by(_MODELS["ApprovalRecord"].created_at.desc()).limit(50).all()
        return [_approval_out(r) for r in rows]
    finally:
        session.close()
