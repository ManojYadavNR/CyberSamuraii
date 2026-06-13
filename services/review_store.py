"""In-memory human review decisions for investigations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

_reviews: dict[str, list[dict[str, Any]]] = {}


def submit_review(
    investigation_id: str,
    cluster_id: str,
    decision: str,
    reviewer: str = "investigator",
    notes: str = "",
) -> dict[str, Any]:
    record = {
        "review_id": str(uuid4()),
        "investigation_id": investigation_id,
        "cluster_id": cluster_id,
        "decision": decision,
        "reviewer": reviewer,
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _reviews.setdefault(investigation_id, []).append(record)
    return record


def get_reviews(investigation_id: str) -> list[dict[str, Any]]:
    return list(_reviews.get(investigation_id, []))
