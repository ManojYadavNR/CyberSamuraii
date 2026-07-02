"""In-app notifications."""

from __future__ import annotations

from services.enterprise.db import get_session, new_id


def notify_user(*, user_id: str, title: str, body: str = "", kind: str = "info", case_id: str = "") -> None:
    session = get_session()
    if not session or not user_id:
        return
    try:
        from services.enterprise.db import _MODELS

        session.add(
            _MODELS["Notification"](
                notification_id=new_id(),
                user_id=user_id,
                title=title,
                body=body,
                kind=kind,
                case_id=case_id,
            )
        )
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def notify_role(role: str, *, title: str, body: str = "", case_id: str = "") -> None:
    session = get_session()
    if not session:
        return
    try:
        from services.enterprise.db import _MODELS

        users = session.query(_MODELS["User"]).filter_by(role=role, active=True).all()
        for u in users:
            notify_user(user_id=u.user_id, title=title, body=body, kind="role", case_id=case_id)
    finally:
        session.close()


def list_notifications(user_id: str, *, unread_only: bool = False, limit: int = 50) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        q = session.query(_MODELS["Notification"]).filter_by(user_id=user_id)
        if unread_only:
            q = q.filter_by(read=False)
        rows = q.order_by(_MODELS["Notification"].created_at.desc()).limit(limit).all()
        return [
            {
                "notification_id": r.notification_id,
                "title": r.title,
                "body": r.body,
                "kind": r.kind,
                "case_id": r.case_id or "",
                "read": bool(r.read),
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    finally:
        session.close()


def mark_read(notification_id: str, user_id: str) -> bool:
    session = get_session()
    if not session:
        return False
    try:
        from services.enterprise.db import _MODELS

        row = session.query(_MODELS["Notification"]).filter_by(notification_id=notification_id, user_id=user_id).first()
        if not row:
            return False
        row.read = True
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def mark_all_read(user_id: str) -> int:
    session = get_session()
    if not session:
        return 0
    try:
        from services.enterprise.db import _MODELS

        count = (
            session.query(_MODELS["Notification"])
            .filter_by(user_id=user_id, read=False)
            .update({"read": True})
        )
        session.commit()
        return count
    except Exception:
        session.rollback()
        return 0
    finally:
        session.close()
