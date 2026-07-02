"""Case workspace — notes, comments, tasks, bookmarks, pins."""

from __future__ import annotations

import re
from typing import Any

from services.enterprise.audit import log_audit
from services.enterprise.db import get_session, new_id
from services.enterprise.notifications import notify_user


def _parse_mentions(text: str) -> list[str]:
    return list({m.lower() for m in re.findall(r"@([a-zA-Z0-9_]+)", text)})


def list_notes(case_id: str) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        rows = (
            session.query(_MODELS["WorkspaceNote"])
            .filter_by(case_id=case_id)
            .order_by(_MODELS["WorkspaceNote"].pinned.desc(), _MODELS["WorkspaceNote"].created_at.desc())
            .all()
        )
        return [
            {
                "note_id": r.note_id,
                "case_id": r.case_id,
                "author_id": r.author_id,
                "content": r.content,
                "pinned": bool(r.pinned),
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    finally:
        session.close()


def add_note(*, case_id: str, author_id: str, content: str, pinned: bool = False) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = _MODELS["WorkspaceNote"](
            note_id=new_id(),
            case_id=case_id,
            author_id=author_id,
            content=content.strip(),
            pinned=pinned,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {
            "note_id": row.note_id,
            "case_id": row.case_id,
            "author_id": row.author_id,
            "content": row.content,
            "pinned": bool(row.pinned),
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def list_comments(case_id: str) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        rows = (
            session.query(_MODELS["CaseComment"])
            .filter_by(case_id=case_id)
            .order_by(_MODELS["CaseComment"].created_at.desc())
            .all()
        )
        out = []
        for r in rows:
            author = session.query(User).filter_by(user_id=r.author_id).first()
            out.append({
                "comment_id": r.comment_id,
                "case_id": r.case_id,
                "author_id": r.author_id,
                "author_name": author.name if author else r.author_id,
                "content": r.content,
                "mentions": r.mentions or [],
                "created_at": r.created_at.isoformat() if r.created_at else "",
            })
        return out
    finally:
        session.close()


def add_comment(*, case_id: str, author_id: str, author_name: str, content: str) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        mentions = _parse_mentions(content)
        row = _MODELS["CaseComment"](
            comment_id=new_id(),
            case_id=case_id,
            author_id=author_id,
            content=content.strip(),
            mentions=mentions,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        for uname in mentions:
            user = session.query(User).filter_by(username=uname).first()
            if user and user.user_id != author_id:
                notify_user(
                    user_id=user.user_id,
                    title=f"Mentioned in case comment",
                    body=f"{author_name} mentioned you: {content[:120]}",
                    kind="mention",
                    case_id=case_id,
                )
        return {
            "comment_id": row.comment_id,
            "case_id": row.case_id,
            "author_id": row.author_id,
            "author_name": author_name,
            "content": row.content,
            "mentions": mentions,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def list_tasks(case_id: str) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        rows = (
            session.query(_MODELS["CaseTask"])
            .filter_by(case_id=case_id)
            .order_by(_MODELS["CaseTask"].created_at.desc())
            .all()
        )
        return [
            {
                "task_id": r.task_id,
                "case_id": r.case_id,
                "title": r.title,
                "description": r.description or "",
                "assigned_to": r.assigned_to,
                "status": r.status,
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


def create_task(
    *,
    case_id: str,
    title: str,
    description: str,
    assigned_to: str | None,
    created_by: str,
    actor_name: str = "",
) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = _MODELS["CaseTask"](
            task_id=new_id(),
            case_id=case_id,
            title=title.strip(),
            description=description.strip(),
            assigned_to=assigned_to,
            created_by=created_by,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        if assigned_to:
            notify_user(
                user_id=assigned_to,
                title="Task assigned",
                body=f"{actor_name or 'A colleague'} assigned: {title}",
                kind="task",
                case_id=case_id,
            )
        return {
            "task_id": row.task_id,
            "case_id": row.case_id,
            "title": row.title,
            "description": row.description or "",
            "assigned_to": row.assigned_to,
            "status": row.status,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def update_task_status(task_id: str, status: str) -> dict | None:
    from datetime import datetime, timezone

    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = session.query(_MODELS["CaseTask"]).filter_by(task_id=task_id).first()
        if not row:
            return None
        row.status = status
        if status == "DONE":
            row.completed_at = datetime.now(timezone.utc)
        session.commit()
        return {"task_id": row.task_id, "status": row.status}
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def list_bookmarks(case_id: str, user_id: str | None = None) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        q = session.query(_MODELS["WorkspaceBookmark"]).filter_by(case_id=case_id)
        if user_id:
            q = q.filter_by(user_id=user_id)
        rows = q.order_by(_MODELS["WorkspaceBookmark"].created_at.desc()).all()
        return [
            {
                "bookmark_id": r.bookmark_id,
                "case_id": r.case_id,
                "user_id": r.user_id,
                "entity_id": r.entity_id,
                "entity_label": r.entity_label,
                "entity_type": r.entity_type,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    finally:
        session.close()


def add_bookmark(
    *,
    case_id: str,
    user_id: str,
    entity_id: str,
    entity_label: str = "",
    entity_type: str = "",
) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        existing = (
            session.query(_MODELS["WorkspaceBookmark"])
            .filter_by(case_id=case_id, user_id=user_id, entity_id=entity_id)
            .first()
        )
        if existing:
            return {
                "bookmark_id": existing.bookmark_id,
                "entity_id": existing.entity_id,
                "entity_label": existing.entity_label,
            }
        row = _MODELS["WorkspaceBookmark"](
            bookmark_id=new_id(),
            case_id=case_id,
            user_id=user_id,
            entity_id=entity_id,
            entity_label=entity_label,
            entity_type=entity_type,
        )
        session.add(row)
        session.commit()
        return {"bookmark_id": row.bookmark_id, "entity_id": entity_id, "entity_label": entity_label}
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def list_pins(case_id: str) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        rows = (
            session.query(_MODELS["WorkspacePin"])
            .filter_by(case_id=case_id)
            .order_by(_MODELS["WorkspacePin"].created_at.desc())
            .all()
        )
        return [
            {
                "pin_id": r.pin_id,
                "case_id": r.case_id,
                "user_id": r.user_id,
                "finding_key": r.finding_key,
                "finding_label": r.finding_label,
                "finding_data": r.finding_data or {},
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    finally:
        session.close()


def add_pin(
    *,
    case_id: str,
    user_id: str,
    finding_key: str,
    finding_label: str = "",
    finding_data: dict | None = None,
) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = _MODELS["WorkspacePin"](
            pin_id=new_id(),
            case_id=case_id,
            user_id=user_id,
            finding_key=finding_key,
            finding_label=finding_label,
            finding_data=finding_data or {},
        )
        session.add(row)
        session.commit()
        return {"pin_id": row.pin_id, "finding_key": finding_key, "finding_label": finding_label}
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def activity_feed(case_id: str, limit: int = 30) -> list[dict[str, Any]]:
    """Merged activity from audit, comments, tasks, investigations."""
    from services.enterprise.cases import list_case_investigations

    feed: list[dict[str, Any]] = []
    for c in list_comments(case_id)[:10]:
        feed.append({"type": "comment", "timestamp": c["created_at"], "user": c["author_name"], "summary": c["content"][:100]})
    for t in list_tasks(case_id)[:10]:
        feed.append({"type": "task", "timestamp": t["created_at"], "user": t["created_by"], "summary": t["title"]})
    for inv in list_case_investigations(case_id)[:10]:
        feed.append({"type": "investigation", "timestamp": inv.get("created_at", ""), "user": inv.get("started_by", ""), "summary": inv.get("query", "")})
    feed.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return feed[:limit]
