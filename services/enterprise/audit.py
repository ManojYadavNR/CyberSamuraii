"""Immutable audit logging with hash chain integrity and rich metadata."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any

from services.enterprise.audit_categories import AUDIT_CATEGORIES, category_for_action, is_suspicious, risk_for_action
from services.enterprise.audit_context import audit_context_from_request
from services.enterprise.db import get_session, new_id


def _ts_iso(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()


def _serialize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, sort_keys=True)


def _last_hash_chain(session, AuditLog) -> str:
    row = (
        session.query(AuditLog.hash_chain)
        .filter(AuditLog.hash_chain != "")
        .order_by(AuditLog.timestamp.desc())
        .limit(1)
        .scalar()
    )
    return row or ""


def _integrity_hashes(payload: dict[str, Any], prev_hash: str) -> tuple[str, str]:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digital_signature = hashlib.sha256(canonical.encode()).hexdigest()
    hash_chain = hashlib.sha256(f"{prev_hash}:{digital_signature}".encode()).hexdigest()
    return digital_signature, hash_chain


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "audit_id": row.log_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else "",
        "user_id": row.user_id or "",
        "username": row.username or "",
        "role": row.role or "",
        "session_id": row.session_id or "",
        "category": row.category or "system",
        "action": row.action,
        "entity": row.entity or "",
        "entity_type": row.entity_type or "",
        "entity_id": row.entity_id or "",
        "case_id": row.case_id or "",
        "investigation_id": row.investigation_id or "",
        "ip": row.ip_address or "",
        "location_approx": row.location_approx or "",
        "device": row.device or "",
        "browser": row.browser or "",
        "os": row.os or "",
        "result": row.result or "success",
        "failure_reason": row.failure_reason or "",
        "risk_level": row.risk_level or "low",
        "approval_required": bool(row.approval_required),
        "supervisor_id": row.supervisor_id or "",
        "previous_value": row.previous_value or "",
        "new_value": row.new_value or "",
        "digital_signature": row.digital_signature or "",
        "hash_chain": row.hash_chain or "",
        "details": row.details or {},
        "user": row.username or row.user_id or "system",
        "suspicious": False,
    }


def log_audit(
    *,
    user_id: str = "",
    username: str = "",
    role: str = "",
    action: str,
    entity: str = "",
    entity_type: str = "",
    entity_id: str = "",
    case_id: str = "",
    investigation_id: str = "",
    ip: str = "",
    result: str = "success",
    failure_reason: str = "",
    previous_value: Any = None,
    new_value: Any = None,
    approval_required: bool = False,
    supervisor_id: str = "",
    session_id: str = "",
    device: str = "",
    browser: str = "",
    os: str = "",
    location_approx: str = "",
    category: str = "",
    risk_level: str = "",
    details: dict[str, Any] | None = None,
    request: Any = None,
) -> str | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        AuditLog = _MODELS["AuditLog"]
        ctx = audit_context_from_request(request)
        ip = ip or ctx.get("ip", "")
        session_id = session_id or ctx.get("session_id", "")
        browser = browser or ctx.get("browser", "")
        os = os or ctx.get("os", "")
        device = device or ctx.get("device", "")
        location_approx = location_approx or ctx.get("location_approx", "")

        if not entity_id and entity and ":" not in entity:
            entity_id = entity
        if not entity_type and entity:
            if entity in {"auth", "user", "case", "evidence", "report"}:
                entity_type = entity

        cat = category or category_for_action(action)
        risk = risk_level or risk_for_action(action, result=result)
        prev_serialized = _serialize_value(previous_value)
        new_serialized = _serialize_value(new_value)
        log_id = new_id()
        ts = datetime.now(timezone.utc)

        integrity_payload = {
            "log_id": log_id,
            "timestamp": _ts_iso(ts),
            "user_id": user_id,
            "username": username or "system",
            "action": action,
            "entity_id": entity_id,
            "result": result,
        }
        prev_hash = _last_hash_chain(session, AuditLog)
        digital_signature, hash_chain = _integrity_hashes(integrity_payload, prev_hash)

        row = AuditLog(
            log_id=log_id,
            timestamp=ts,
            user_id=user_id or "",
            username=username or "system",
            role=role or "",
            session_id=session_id,
            category=cat,
            action=action,
            entity=entity,
            entity_type=entity_type,
            entity_id=entity_id,
            case_id=case_id,
            investigation_id=investigation_id,
            ip_address=ip,
            location_approx=location_approx,
            device=device,
            browser=browser,
            os=os,
            result=result,
            failure_reason=failure_reason,
            risk_level=risk,
            approval_required=approval_required,
            supervisor_id=supervisor_id,
            previous_value=prev_serialized,
            new_value=new_serialized,
            digital_signature=digital_signature,
            hash_chain=hash_chain,
            details=details or {},
        )
        session.add(row)
        session.commit()
        return log_id
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def list_audit_logs(
    *,
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
) -> dict[str, Any]:
    session = get_session()
    if not session:
        return {"logs": [], "total": 0, "categories": list(AUDIT_CATEGORIES)}
    try:
        from services.enterprise.db import _MODELS

        AuditLog = _MODELS["AuditLog"]
        q = session.query(AuditLog)
        if user_id:
            q = q.filter(AuditLog.user_id == user_id)
        if username:
            q = q.filter(AuditLog.username.ilike(f"%{username}%"))
        if role:
            q = q.filter(AuditLog.role == role)
        if case_id:
            q = q.filter(AuditLog.case_id == case_id)
        if investigation_id:
            q = q.filter(AuditLog.investigation_id == investigation_id)
        if category:
            q = q.filter(AuditLog.category == category)
        if action:
            q = q.filter(AuditLog.action == action)
        if risk_level:
            q = q.filter(AuditLog.risk_level == risk_level)
        if result:
            q = q.filter(AuditLog.result == result)
        if date_from:
            q = q.filter(AuditLog.timestamp >= datetime.fromisoformat(date_from.replace("Z", "+00:00")))
        if date_to:
            q = q.filter(AuditLog.timestamp <= datetime.fromisoformat(date_to.replace("Z", "+00:00")))
        if search:
            pattern = f"%{search}%"
            q = q.filter(
                (AuditLog.username.ilike(pattern))
                | (AuditLog.action.ilike(pattern))
                | (AuditLog.entity.ilike(pattern))
                | (AuditLog.entity_id.ilike(pattern))
                | (AuditLog.ip_address.ilike(pattern))
                | (AuditLog.failure_reason.ilike(pattern))
            )

        total = q.count()
        rows = q.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()
        logs = []
        for r in rows:
            entry = _row_to_dict(r)
            entry["suspicious"] = is_suspicious(entry)
            if suspicious_only and not entry["suspicious"]:
                continue
            logs.append(entry)
        return {"logs": logs, "total": total if not suspicious_only else len(logs), "categories": list(AUDIT_CATEGORIES)}
    finally:
        session.close()


def get_audit_log(log_id: str) -> dict[str, Any] | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = session.query(_MODELS["AuditLog"]).filter_by(log_id=log_id).first()
        if not row:
            return None
        entry = _row_to_dict(row)
        entry["suspicious"] = is_suspicious(entry)
        return entry
    finally:
        session.close()


def user_activity_history(user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    return list_audit_logs(user_id=user_id, limit=limit)["logs"]


def case_activity_history(case_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    return list_audit_logs(case_id=case_id, limit=limit)["logs"]


def export_audit_csv(**filters: Any) -> str:
    data = list_audit_logs(limit=5000, offset=0, **filters)
    buf = io.StringIO()
    fieldnames = [
        "audit_id", "timestamp", "category", "action", "user_id", "username", "role",
        "case_id", "investigation_id", "entity_type", "entity_id", "ip", "location_approx",
        "device", "browser", "os", "session_id", "result", "failure_reason", "risk_level",
        "approval_required", "supervisor_id", "previous_value", "new_value",
        "digital_signature", "hash_chain", "suspicious",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in data["logs"]:
        writer.writerow(row)
    return buf.getvalue()


def rebuild_audit_hash_chain() -> int:
    """Recompute digital signatures and hash chain for all audit rows (chronological)."""
    session = get_session()
    if not session:
        return 0
    try:
        from services.enterprise.db import _MODELS

        AuditLog = _MODELS["AuditLog"]
        rows = session.query(AuditLog).order_by(AuditLog.timestamp.asc(), AuditLog.log_id.asc()).all()
        prev_hash = ""
        for row in rows:
            entity_id = row.entity_id or (row.entity if row.entity and ":" not in str(row.entity) else "")
            payload = {
                "log_id": row.log_id,
                "timestamp": _ts_iso(row.timestamp),
                "user_id": row.user_id or "",
                "username": row.username or "system",
                "action": row.action,
                "entity_id": entity_id,
                "result": row.result or "success",
            }
            digital_signature, hash_chain = _integrity_hashes(payload, prev_hash)
            row.digital_signature = digital_signature
            row.hash_chain = hash_chain
            prev_hash = hash_chain
        session.commit()
        return len(rows)
    except Exception:
        session.rollback()
        return 0
    finally:
        session.close()


def ensure_audit_chain_integrity() -> dict[str, Any]:
    """Backfill missing hashes or rebuild chain when verification fails."""
    session = get_session()
    if not session:
        return {"rebuilt": 0, "valid": False}
    try:
        from services.enterprise.db import _MODELS

        AuditLog = _MODELS["AuditLog"]
        total = session.query(AuditLog).count()
        if total == 0:
            return {"rebuilt": 0, "valid": True, "checked": 0}
        missing = session.query(AuditLog).filter(
            (AuditLog.hash_chain == "") | (AuditLog.hash_chain.is_(None))
        ).count()
        session.close()
        rebuilt = 0
        if missing > 0:
            rebuilt = rebuild_audit_hash_chain()
        else:
            check = verify_hash_chain(limit=total + 1)
            if not check["valid"]:
                rebuilt = rebuild_audit_hash_chain()
        final = verify_hash_chain(limit=total + 1)
        return {"rebuilt": rebuilt, **final}
    finally:
        try:
            session.close()
        except Exception:
            pass


def verify_hash_chain(*, limit: int = 500) -> dict[str, Any]:
    session = get_session()
    if not session:
        return {"valid": False, "checked": 0, "broken_at": None}
    try:
        from services.enterprise.db import _MODELS

        AuditLog = _MODELS["AuditLog"]
        rows = (
            session.query(AuditLog)
            .filter(AuditLog.hash_chain != "")
            .order_by(AuditLog.timestamp.asc())
            .limit(limit)
            .all()
        )
        prev_hash = ""
        for idx, row in enumerate(rows):
            entity_id = row.entity_id or (row.entity if row.entity and ":" not in str(row.entity) else "")
            payload = {
                "log_id": row.log_id,
                "timestamp": _ts_iso(row.timestamp),
                "user_id": row.user_id or "",
                "username": row.username or "system",
                "action": row.action,
                "entity_id": entity_id,
                "result": row.result or "success",
            }
            expected_sig, expected_chain = _integrity_hashes(payload, prev_hash)
            if row.hash_chain != expected_chain:
                return {"valid": False, "checked": idx + 1, "broken_at": row.log_id}
            prev_hash = row.hash_chain
        return {"valid": True, "checked": len(rows), "broken_at": None}
    finally:
        session.close()
