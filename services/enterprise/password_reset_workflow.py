"""Enterprise password reset — supervisor and admin approval workflow."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Any

from services.enterprise.audit import log_audit
from services.enterprise.auth_tokens import hash_password
from services.enterprise.db import get_session, new_id
from services.enterprise.notifications import notify_role, notify_user
from services.enterprise.password_policy import assert_strong_password

SUPERVISOR_ROLES = frozenset({"SP", "DSP", "INSPECTOR", "CID_DIRECTOR", "SUPER_ADMIN"})
ADMIN_ROLES = frozenset({"SUPER_ADMIN", "CID_DIRECTOR"})


def _request_public(row, *, user=None) -> dict[str, Any]:
    return {
        "request_id": row.request_id,
        "user_id": row.user_id,
        "employee_id": row.employee_id,
        "employee_name": getattr(user, "name", "") if user else "",
        "status": row.status,
        "reason": row.reason or "",
        "requested_at": row.requested_at.isoformat() if row.requested_at else "",
        "supervisor_id": row.supervisor_id or "",
        "supervisor_notes": row.supervisor_notes or "",
        "supervisor_decision_at": row.supervisor_decision_at.isoformat() if row.supervisor_decision_at else "",
        "admin_id": row.admin_id or "",
        "admin_notes": row.admin_notes or "",
        "admin_decision_at": row.admin_decision_at.isoformat() if row.admin_decision_at else "",
        "temp_password_issued": bool(row.temp_password_issued),
        "completed_at": row.completed_at.isoformat() if row.completed_at else "",
    }


def _generate_temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%&*" for c in pwd)
        ):
            return pwd


def submit_password_reset_request(
    *,
    employee_id: str,
    reason: str = "",
    ip: str = "",
    request=None,
) -> dict[str, Any]:
    session = get_session()
    if not session:
        raise RuntimeError("Database unavailable")
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        PRR = _MODELS["PasswordResetRequest"]
        uname = employee_id.strip().lower()
        user = session.query(User).filter_by(username=uname, active=True).first()
        if not user:
            log_audit(
                username=uname,
                action="password_reset_workflow_request",
                entity="auth",
                entity_type="user",
                result="failed",
                failure_reason="unknown_employee_id",
                ip=ip,
                request=request,
            )
            return {
                "ok": True,
                "message": "If the employee ID is registered, a reset request was created for supervisor review.",
            }

        existing = (
            session.query(PRR)
            .filter_by(user_id=user.user_id)
            .filter(PRR.status.in_(["pending_supervisor", "pending_admin"]))
            .first()
        )
        if existing:
            return {
                "ok": True,
                "request_id": existing.request_id,
                "status": existing.status,
                "message": "A password reset request is already pending approval.",
            }

        row = PRR(
            request_id=new_id(),
            user_id=user.user_id,
            employee_id=user.username,
            status="pending_supervisor",
            reason=reason.strip(),
        )
        session.add(row)
        session.commit()

        notify_role("SP", title="Password reset request", body=f"Employee {user.username} requested a password reset.")
        notify_role("DSP", title="Password reset request", body=f"Employee {user.username} requested a password reset.")
        notify_role("SUPER_ADMIN", title="Password reset queued", body=f"Reset for {user.username} awaits supervisor then admin approval.")

        log_audit(
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            action="password_reset_workflow_request",
            entity=user.username,
            entity_type="user",
            entity_id=user.user_id,
            result="success",
            approval_required=True,
            ip=ip,
            request=request,
            details={"request_id": row.request_id, "reason": reason},
        )
        return {
            "ok": True,
            "request_id": row.request_id,
            "status": row.status,
            "message": "Request submitted. Your supervisor and security administrator will be notified.",
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_password_reset_requests(*, status: str = "", limit: int = 100) -> list[dict[str, Any]]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        PRR = _MODELS["PasswordResetRequest"]
        User = _MODELS["User"]
        q = session.query(PRR)
        if status:
            q = q.filter_by(status=status)
        rows = q.order_by(PRR.requested_at.desc()).limit(limit).all()
        out = []
        for r in rows:
            user = session.query(User).filter_by(user_id=r.user_id).first()
            out.append(_request_public(r, user=user))
        return out
    finally:
        session.close()


def supervisor_decide_password_reset(
    *,
    request_id: str,
    actor_id: str,
    actor_username: str,
    actor_role: str,
    approve: bool,
    notes: str = "",
    ip: str = "",
    request=None,
) -> dict[str, Any]:
    if actor_role not in SUPERVISOR_ROLES:
        raise PermissionError("Supervisor role required")
    session = get_session()
    if not session:
        raise RuntimeError("Database unavailable")
    try:
        from services.enterprise.db import _MODELS

        PRR = _MODELS["PasswordResetRequest"]
        row = session.query(PRR).filter_by(request_id=request_id).first()
        if not row or row.status != "pending_supervisor":
            raise ValueError("Request not found or not awaiting supervisor")

        now = datetime.now(timezone.utc)
        row.supervisor_id = actor_id
        row.supervisor_notes = notes
        row.supervisor_decision_at = now
        if approve:
            row.status = "pending_admin"
            notify_role("SUPER_ADMIN", title="Password reset needs admin approval", body=f"Request for {row.employee_id}")
            notify_role("CID_DIRECTOR", title="Password reset needs admin approval", body=f"Request for {row.employee_id}")
        else:
            row.status = "denied"
            row.completed_at = now
            notify_user(user_id=row.user_id, title="Password reset denied", body=notes or "Contact your supervisor.")

        session.commit()
        log_audit(
            user_id=actor_id,
            username=actor_username,
            role=actor_role,
            action="password_reset_supervisor_approve" if approve else "password_reset_supervisor_deny",
            entity=row.employee_id,
            entity_type="user",
            entity_id=row.user_id,
            supervisor_id=actor_id,
            approval_required=True,
            result="success",
            ip=ip,
            request=request,
            details={"request_id": request_id, "notes": notes},
        )
        return _request_public(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def admin_decide_password_reset(
    *,
    request_id: str,
    actor_id: str,
    actor_username: str,
    actor_role: str,
    approve: bool,
    notes: str = "",
    ip: str = "",
    request=None,
) -> dict[str, Any]:
    if actor_role not in ADMIN_ROLES:
        raise PermissionError("Administrator role required")
    session = get_session()
    if not session:
        raise RuntimeError("Database unavailable")
    try:
        from services.enterprise.db import _MODELS

        PRR = _MODELS["PasswordResetRequest"]
        User = _MODELS["User"]
        row = session.query(PRR).filter_by(request_id=request_id).first()
        if not row or row.status != "pending_admin":
            raise ValueError("Request not found or not awaiting administrator")

        now = datetime.now(timezone.utc)
        row.admin_id = actor_id
        row.admin_notes = notes
        row.admin_decision_at = now
        temp_password = None
        if approve:
            user = session.query(User).filter_by(user_id=row.user_id, active=True).first()
            if not user:
                raise ValueError("User account not found")
            temp_password = _generate_temp_password()
            assert_strong_password(temp_password, username=user.username)
            user.password_hash = hash_password(temp_password)
            user.must_change_password = True
            user.failed_logins = {"count": 0}
            user.locked_until = None
            row.status = "approved"
            row.temp_password_issued = True
            row.completed_at = now
            notify_user(
                user_id=user.user_id,
                title="Password reset approved",
                body="A temporary password was issued. Sign in and change your password immediately.",
            )
        else:
            row.status = "denied"
            row.completed_at = now
            notify_user(user_id=row.user_id, title="Password reset denied", body=notes or "Contact IT security.")

        session.commit()
        log_audit(
            user_id=actor_id,
            username=actor_username,
            role=actor_role,
            action="password_reset_admin_approve" if approve else "password_reset_admin_deny",
            entity=row.employee_id,
            entity_type="user",
            entity_id=row.user_id,
            supervisor_id=row.supervisor_id,
            approval_required=True,
            result="success",
            risk_level="high",
            ip=ip,
            request=request,
            details={"request_id": request_id, "notes": notes},
        )
        out = _request_public(row)
        if temp_password:
            out["temporary_password"] = temp_password
            out["message"] = "Temporary password issued — deliver through secure channel and force immediate change on login."
        return out
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
