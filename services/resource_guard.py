"""Global caps so parallel OSINT runs do not exhaust RAM (OOM / SIGKILL)."""

from __future__ import annotations

import asyncio
import contextvars
import os
from contextlib import asynccontextmanager

MAX_CONCURRENT_INVESTIGATIONS = max(1, int(os.getenv("MAX_CONCURRENT_INVESTIGATIONS", "1")))
GLOBAL_TOOL_SUBPROCESS_CAP = max(2, int(os.getenv("GLOBAL_TOOL_SUBPROCESS_CAP", "8")))
MULTI_INPUT_PARALLEL = os.getenv("MULTI_INPUT_PARALLEL", "true").lower() in ("1", "true", "yes")
# Run username + email branches concurrently (each branch still capped via dual_identity_scan).
DUAL_BRANCH_PARALLEL = os.getenv("DUAL_BRANCH_PARALLEL", "true").lower() in ("1", "true", "yes")
INVESTIGATION_QUEUE_TIMEOUT_SEC = float(os.getenv("INVESTIGATION_QUEUE_TIMEOUT_SEC", "2"))

# Applied ONLY when username + email are searched together (multi-input combo).
DUAL_GLOBAL_TOOL_SUBPROCESS_CAP = max(2, int(os.getenv("DUAL_GLOBAL_TOOL_SUBPROCESS_CAP", "6")))
DUAL_USERNAME_TOOL_CONCURRENCY = max(1, int(os.getenv("DUAL_USERNAME_TOOL_CONCURRENCY", "4")))
DUAL_EMAIL_TOOL_CONCURRENCY = max(1, int(os.getenv("DUAL_EMAIL_TOOL_CONCURRENCY", "3")))
DUAL_USERNAME_PHASE1_PARALLEL = max(1, int(os.getenv("DUAL_USERNAME_PHASE1_PARALLEL", "14")))
DUAL_USERNAME_PHASE2_PARALLEL = max(1, int(os.getenv("DUAL_USERNAME_PHASE2_PARALLEL", "14")))
DUAL_USERNAME_WALL_SEC = max(60, float(os.getenv("DUAL_USERNAME_WALL_SEC", "150")))
DUAL_EMAIL_WALL_SEC = max(60, float(os.getenv("DUAL_EMAIL_WALL_SEC", "120")))
DUAL_SOCIAL_ANALYZER_MAX_SITES = max(40, int(os.getenv("DUAL_SOCIAL_ANALYZER_MAX_SITES", "160")))
DUAL_SOCIAL_ANALYZER_PHASE2_PARALLEL = max(1, int(os.getenv("DUAL_SOCIAL_ANALYZER_PHASE2_PARALLEL", "12")))

_dual_identity_scan: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "dual_identity_scan",
    default=False,
)
_full_scan_mode: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "full_scan_mode",
    default=False,
)
_investigation_mode: contextvars.ContextVar[str] = contextvars.ContextVar(
    "investigation_mode",
    default="standard",
)

_loop_state: dict[int, dict[str, asyncio.Semaphore | int]] = {}


class InvestigationBusyError(Exception):
    """Raised when another investigation is already using the server slot."""

    def __init__(self, message: str | None = None):
        super().__init__(
            message
            or (
                "Another investigation is already running. "
                "Wait for it to finish before starting another scan."
            )
        )


def is_dual_identity_scan() -> bool:
    """True only for combined username + email multi-input investigations."""
    return _dual_identity_scan.get()


def is_full_scan_mode() -> bool:
    """Deep multi-input: keep parallel branches but use full (non-dual) scan budgets."""
    return _full_scan_mode.get()


def get_investigation_mode() -> str:
    return _investigation_mode.get()


@asynccontextmanager
async def investigation_mode_scope(mode: str):
    """Set Standard / Quick / Deep for scan budgets, tool lists, and discovery."""
    normalized = mode if mode in ("standard", "fast", "deep", "samurai") else "standard"
    token = _investigation_mode.set(normalized)
    try:
        yield
    finally:
        _investigation_mode.reset(token)


@asynccontextmanager
async def full_scan_mode():
    """Disable dual budget caps while username+email branches still run in parallel."""
    token = _full_scan_mode.set(True)
    try:
        yield
    finally:
        _full_scan_mode.reset(token)


@asynccontextmanager
async def dual_identity_scan():
    """Enable low-memory limits for username + email combo scans."""
    token = _dual_identity_scan.set(True)
    try:
        yield
    finally:
        _dual_identity_scan.reset(token)


def _state() -> dict[str, asyncio.Semaphore | int]:
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _loop_state:
        _loop_state[loop_id] = {
            "investigation_sem": asyncio.Semaphore(MAX_CONCURRENT_INVESTIGATIONS),
            "tool_sem": asyncio.Semaphore(GLOBAL_TOOL_SUBPROCESS_CAP),
            "dual_tool_sem": asyncio.Semaphore(DUAL_GLOBAL_TOOL_SUBPROCESS_CAP),
            "active": 0,
        }
    return _loop_state[loop_id]


@asynccontextmanager
async def investigation_slot():
    """One active investigation by default — prevents duplicate heavy scans."""
    state = _state()
    investigation_sem = state["investigation_sem"]
    assert isinstance(investigation_sem, asyncio.Semaphore)

    try:
        await asyncio.wait_for(investigation_sem.acquire(), timeout=INVESTIGATION_QUEUE_TIMEOUT_SEC)
    except asyncio.TimeoutError as exc:
        raise InvestigationBusyError() from exc

    state["active"] = int(state["active"]) + 1
    try:
        yield
    finally:
        state["active"] = max(0, int(state["active"]) - 1)
        investigation_sem.release()


@asynccontextmanager
async def tool_subprocess_slot():
    """Shared cap on concurrent tool adapters (subprocess / network heavy work)."""
    state = _state()
    tool_sem = state["tool_sem"]
    assert isinstance(tool_sem, asyncio.Semaphore)

    dual_sem = state["dual_tool_sem"]
    assert isinstance(dual_sem, asyncio.Semaphore)

    if is_dual_identity_scan():
        await dual_sem.acquire()
    await tool_sem.acquire()
    try:
        yield
    finally:
        tool_sem.release()
        if is_dual_identity_scan():
            dual_sem.release()


def active_investigation_count() -> int:
    try:
        return int(_state()["active"])
    except RuntimeError:
        return 0


def effective_tool_concurrency(feature: str, requested: int | None) -> int:
    """Clamp per-feature parallelism to the global subprocess budget."""
    if memory_pressure_high():
        return 1
    if is_dual_identity_scan():
        if feature == "username_search":
            return DUAL_USERNAME_TOOL_CONCURRENCY
        if feature == "email_intel":
            return DUAL_EMAIL_TOOL_CONCURRENCY
        return DUAL_GLOBAL_TOOL_SUBPROCESS_CAP

    base = max(1, requested or 4)
    cap = GLOBAL_TOOL_SUBPROCESS_CAP
    active = active_investigation_count()
    if active > 1:
        cap = max(2, cap // active)
    return max(1, min(base, cap))


def memory_pressure_high() -> bool:
    """True when available RAM is low — skip heavy phase-2 scans."""
    threshold = float(os.getenv("MEMORY_PRESSURE_PERCENT", "82"))
    try:
        with open("/proc/meminfo") as f:
            info: dict[str, int] = {}
            for line in f:
                key, rest = line.split(":", 1)
                info[key.strip()] = int(rest.split()[0])
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        if total <= 0:
            return False
        used_pct = 100.0 * (1.0 - avail / total)
        return used_pct >= threshold
    except OSError:
        return False
