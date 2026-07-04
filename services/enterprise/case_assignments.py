"""Case team assignments — role × relationship per case."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.enterprise.audit import log_audit
from services.enterprise.db import get_session, new_id
from services.enterprise.rbac import (
    case_relationships,
    default_relationship_for_rank,
    resolve_rank,
    workflow_config,
)


def _assignment_out(row) -> dict[str, Any]:
    return {
        "assignment_id": row.assignment_id,
        "case_id": row.case_id,
        "user_id": row.user_id,
        "relationship": row.relationship,
        "org_role": row.org_role or "",
        "rank_code": row.rank_code or "",
        "assigned_by": row.assigned_by or "",
        "active": bool(row.active),
        "notes": row.notes or "",
        "assigned_at": row.assigned_at.isoformat() if row.assigned_at else "",
    }


def _user_snapshot(session, user_id: str) -> tuple[str, str]:
    from services.enterprise.db import _MODELS

    user = session.query(_MODELS["User"]).filter_by(user_id=user_id).first()
    if not user:
        return "", ""
    role = user.role or ""
    rank = user.rank_code or resolve_rank(role)
    return role, rank


VALID_RELATIONSHIPS = {r["code"] for r in case_relationships()}


def list_case_assignments(case_id: str, *, active_only: bool = True) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        q = session.query(_MODELS["CaseAssignment"]).filter_by(case_id=case_id)
        if active_only:
            q = q.filter_by(active=True)
        rows = q.order_by(_MODELS["CaseAssignment"].assigned_at.asc()).all()
        return [_assignment_out(r) for r in rows]
    finally:
        session.close()


def get_user_case_relationships(user_id: str, case_id: str) -> list[str]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        rows = (
            session.query(_MODELS["CaseAssignment"])
            .filter_by(case_id=case_id, user_id=user_id, active=True)
            .all()
        )
        return [r.relationship for r in rows if r.relationship]
    finally:
        session.close()


def user_has_case_access(user_id: str, case_id: str) -> bool:
    """Whether user is linked to the case via assignment, creation, or legacy assignee."""
    session = get_session()
    if not session:
        return False
    try:
        from services.enterprise.db import _MODELS

        Case = _MODELS["Case"]
        case = session.query(Case).filter_by(case_id=case_id).first()
        if not case:
            return False
        if case.created_by == user_id or case.assigned_to == user_id:
            return True
        count = (
            session.query(_MODELS["CaseAssignment"])
            .filter_by(case_id=case_id, user_id=user_id, active=True)
            .count()
        )
        return count > 0
    finally:
        session.close()


def list_user_case_ids(user_id: str) -> set[str]:
    session = get_session()
    if not session:
        return set()
    try:
        from services.enterprise.db import _MODELS

        Case = _MODELS["Case"]
        case_ids: set[str] = set()
        for row in session.query(Case).filter(
            (Case.created_by == user_id) | (Case.assigned_to == user_id)
        ).all():
            case_ids.add(row.case_id)
        for row in (
            session.query(_MODELS["CaseAssignment"])
            .filter_by(user_id=user_id, active=True)
            .all()
        ):
            case_ids.add(row.case_id)
        return case_ids
    finally:
        session.close()


def add_case_assignment(
    case_id: str,
    *,
    user_id: str,
    relationship: str,
    assigned_by: str = "",
    notes: str = "",
    org_role: str = "",
    rank_code: str = "",
) -> dict | None:
    if relationship not in VALID_RELATIONSHIPS:
        raise ValueError(f"Invalid case relationship: {relationship}")

    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        CA = _MODELS["CaseAssignment"]
        existing = (
            session.query(CA)
            .filter_by(case_id=case_id, user_id=user_id, relationship=relationship, active=True)
            .first()
        )
        if existing:
            return _assignment_out(existing)

        if not org_role or not rank_code:
            snap_role, snap_rank = _user_snapshot(session, user_id)
            org_role = org_role or snap_role
            rank_code = rank_code or snap_rank

        row = CA(
            assignment_id=new_id(),
            case_id=case_id,
            user_id=user_id,
            relationship=relationship,
            org_role=org_role,
            rank_code=rank_code,
            assigned_by=assigned_by,
            active=True,
            notes=notes.strip(),
        )
        session.add(row)

        if relationship == "investigating_officer":
            session.query(_MODELS["Case"]).filter_by(case_id=case_id).update(
                {"assigned_to": user_id, "updated_at": datetime.now(timezone.utc)}
            )

        session.commit()
        session.refresh(row)
        return _assignment_out(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def remove_case_assignment(assignment_id: str, *, actor_id: str = "") -> bool:
    session = get_session()
    if not session:
        return False
    try:
        from services.enterprise.db import _MODELS

        row = session.query(_MODELS["CaseAssignment"]).filter_by(assignment_id=assignment_id).first()
        if not row:
            return False
        row.active = False
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def assign_case_team(
    case_id: str,
    *,
    assignments: list[dict],
    actor_id: str,
    username: str = "",
    ip: str = "",
) -> list[dict]:
    """Bulk assign team members with relationships."""
    results: list[dict] = []
    for item in assignments:
        user_id = item.get("user_id")
        relationship = item.get("relationship")
        if not user_id or not relationship:
            continue
        row = add_case_assignment(
            case_id,
            user_id=user_id,
            relationship=relationship,
            assigned_by=actor_id,
            notes=str(item.get("notes") or ""),
            org_role=str(item.get("org_role") or ""),
            rank_code=str(item.get("rank_code") or ""),
        )
        if row:
            results.append(row)
    if results:
        from services.enterprise.cases import get_case

        case = get_case(case_id)
        if case:
            log_audit(
                user_id=actor_id,
                username=username,
                action="assign_case_team",
                entity=case.get("case_number", case_id),
                ip=ip,
                case_id=case_id,
                details={"assignments": results},
            )
    return results


def apply_assignment_template(
    case_id: str,
    template_code: str,
    *,
    members: list[dict],
    actor_id: str,
    username: str = "",
    ip: str = "",
) -> list[dict]:
    """Apply template with explicit user picks per slot."""
    return assign_case_team(
        case_id,
        assignments=members,
        actor_id=actor_id,
        username=username,
        ip=ip,
    )


def ensure_creator_assignment(case_id: str, creator_id: str) -> None:
    workflow = workflow_config()
    rel = workflow.get("creator_default_relationship", "supervisor")
    try:
        add_case_assignment(case_id, user_id=creator_id, relationship=rel, assigned_by=creator_id)
    except Exception:
        pass


def migrate_legacy_assignments() -> int:
    """One-time: copy Case.assigned_to → investigating_officer assignment."""
    session = get_session()
    if not session:
        return 0
    count = 0
    try:
        from services.enterprise.db import _MODELS

        Case = _MODELS["Case"]
        CA = _MODELS["CaseAssignment"]
        legacy_io = workflow_config().get("legacy_io_relationship", "investigating_officer")
        for case in session.query(Case).filter(Case.assigned_to.isnot(None)).all():
            if not case.assigned_to:
                continue
            exists = (
                session.query(CA)
                .filter_by(case_id=case.case_id, user_id=case.assigned_to, active=True)
                .first()
            )
            if exists:
                continue
            org_role, rank_code = _user_snapshot(session, case.assigned_to)
            session.add(
                CA(
                    assignment_id=new_id(),
                    case_id=case.case_id,
                    user_id=case.assigned_to,
                    relationship=legacy_io,
                    org_role=org_role,
                    rank_code=rank_code,
                    assigned_by=case.created_by or "",
                    active=True,
                )
            )
            count += 1
        for case in session.query(Case).all():
            creator_exists = (
                session.query(CA)
                .filter_by(case_id=case.case_id, user_id=case.created_by, active=True)
                .count()
            )
            if not creator_exists and case.created_by:
                rel = workflow_config().get("creator_default_relationship", "supervisor")
                org_role, rank_code = _user_snapshot(session, case.created_by)
                session.add(
                    CA(
                        assignment_id=new_id(),
                        case_id=case.case_id,
                        user_id=case.created_by,
                        relationship=rel,
                        org_role=org_role,
                        rank_code=rank_code,
                        assigned_by=case.created_by,
                        active=True,
                    )
                )
                count += 1
        session.commit()
        return count
    except Exception:
        session.rollback()
        return 0
    finally:
        session.close()


def suggest_relationship_for_user(role: str, rank_code: str = "", *, sensitive: bool = False) -> str:
    rank = rank_code or resolve_rank(role)
    return default_relationship_for_rank(rank, sensitive=sensitive)
