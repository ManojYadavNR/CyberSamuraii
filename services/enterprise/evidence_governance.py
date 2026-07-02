"""Evidence governance — SHA256 chain, archive-only."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from services.enterprise.audit import log_audit
from services.enterprise.db import get_session, new_id


def _last_hash(session, case_id: str) -> str:
    from services.enterprise.db import _MODELS

    row = (
        session.query(_MODELS["EvidenceRecord"])
        .filter_by(case_id=case_id, archived=False)
        .order_by(_MODELS["EvidenceRecord"].created_at.desc())
        .first()
    )
    return row.sha256 if row else ""


def record_evidence(
    *,
    case_id: str,
    investigation_id: str | None,
    source: str,
    collector_id: str,
    payload: dict[str, Any] | str,
    label: str = "",
    important: bool = False,
    username: str = "",
) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        raw = json.dumps(payload, sort_keys=True, default=str) if isinstance(payload, dict) else str(payload)
        sha = hashlib.sha256(raw.encode()).hexdigest()
        prev = _last_hash(session, case_id)
        chain_input = f"{prev}:{sha}" if prev else sha
        chain_hash = hashlib.sha256(chain_input.encode()).hexdigest()
        row = _MODELS["EvidenceRecord"](
            evidence_id=new_id(),
            case_id=case_id,
            investigation_id=investigation_id or "",
            sha256=chain_hash,
            previous_hash=prev,
            source=source,
            collector_id=collector_id,
            payload_ref=raw[:4000],
            label=label,
            important=important,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        log_audit(
            user_id=collector_id,
            username=username,
            action="record_evidence",
            entity=row.evidence_id,
            details={"case_id": case_id, "sha256": chain_hash},
        )
        return _evidence_out(row)
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def _evidence_out(row) -> dict:
    return {
        "evidence_id": row.evidence_id,
        "case_id": row.case_id,
        "investigation_id": row.investigation_id or "",
        "sha256": row.sha256,
        "previous_hash": row.previous_hash or "",
        "source": row.source,
        "collector_id": row.collector_id,
        "label": row.label or "",
        "important": bool(row.important),
        "archived": bool(row.archived),
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def list_evidence(case_id: str, *, include_archived: bool = False) -> list[dict]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        q = session.query(_MODELS["EvidenceRecord"]).filter_by(case_id=case_id)
        if not include_archived:
            q = q.filter_by(archived=False)
        rows = q.order_by(_MODELS["EvidenceRecord"].created_at.asc()).all()
        return [_evidence_out(r) for r in rows]
    finally:
        session.close()


def mark_evidence_important(evidence_id: str, important: bool = True) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = session.query(_MODELS["EvidenceRecord"]).filter_by(evidence_id=evidence_id).first()
        if not row:
            return None
        row.important = important
        session.commit()
        return _evidence_out(row)
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def archive_evidence(evidence_id: str, *, actor_id: str = "", username: str = "") -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = session.query(_MODELS["EvidenceRecord"]).filter_by(evidence_id=evidence_id).first()
        if not row:
            return None
        row.archived = True
        session.commit()
        log_audit(user_id=actor_id, username=username, action="archive_evidence", entity=evidence_id)
        return _evidence_out(row)
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()
