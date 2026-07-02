"""Security controls — rate limiting and session helpers."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

_lock = Lock()
_hits: dict[str, list[float]] = defaultdict(list)

RATE_LIMITS = {
    "/api/auth/login": (10, 60),
    "/api/dashboard/investigate": (5, 60),
    "/ws/investigate": (5, 60),
}


def check_rate_limit(key: str, path: str) -> bool:
    """Return True if allowed, False if rate limited."""
    import os

    if os.getenv("DISABLE_RATE_LIMIT", "").lower() in {"1", "true", "yes"}:
        return True
    rule = RATE_LIMITS.get(path)
    if not rule:
        return True
    max_hits, window = rule
    now = time.time()
    bucket = f"{path}:{key}"
    with _lock:
        times = [t for t in _hits[bucket] if now - t < window]
        if len(times) >= max_hits:
            _hits[bucket] = times
            return False
        times.append(now)
        _hits[bucket] = times
        return True
