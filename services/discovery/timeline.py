"""Build discovery timeline events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from schemas.discovery import TimelineEvent

TimelinePhase = Literal[
    "seed",
    "lead_discovered",
    "hop_started",
    "hop_completed",
    "hop_failed",
    "merge",
    "correlation",
    "graph",
    "expansion_stopped",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timeline_event(
    phase: TimelinePhase,
    message: str,
    *,
    detail: str | None = None,
    depth: int | None = None,
    query: str | None = None,
) -> TimelineEvent:
    return TimelineEvent(
        event_id=str(uuid4()),
        timestamp=_now(),
        phase=phase,
        message=message,
        detail=detail,
        depth=depth,
        query=query,
    )
