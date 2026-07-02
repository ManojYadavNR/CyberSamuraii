"""User-initiated investigation cancellation (one active investigation at a time)."""

from __future__ import annotations

import asyncio
from typing import Any

_state: dict[str, Any] = {"id": None, "event": None}


class InvestigationCancelledError(Exception):
    """Raised when the user stops a running investigation."""


def begin_investigation(investigation_id: str) -> asyncio.Event:
    event = asyncio.Event()
    _state["id"] = investigation_id
    _state["event"] = event
    return event


def use_cancel_event(investigation_id: str, event: asyncio.Event) -> None:
    _state["id"] = investigation_id
    _state["event"] = event


def end_investigation(investigation_id: str) -> None:
    if _state.get("id") == investigation_id:
        _state["id"] = None
        _state["event"] = None


def active_investigation_id() -> str | None:
    inv_id = _state.get("id")
    return str(inv_id) if inv_id else None


def cancel_investigation(investigation_id: str | None = None) -> bool:
    if investigation_id and _state.get("id") != investigation_id:
        return False
    event = _state.get("event")
    if isinstance(event, asyncio.Event) and not event.is_set():
        event.set()
        return True
    return False


def clear_cancel_state() -> None:
    """Release investigation slot tracking after a stop or completion."""
    _state["id"] = None
    _state["event"] = None


def is_cancelled() -> bool:
    event = _state.get("event")
    return bool(isinstance(event, asyncio.Event) and event.is_set())


def ensure_not_cancelled() -> None:
    if is_cancelled():
        raise InvestigationCancelledError("Investigation stopped by user")
