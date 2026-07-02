"""Username scan timing — full coverage within ~3 minutes."""

from __future__ import annotations

import os

# Total collection budget (tools run in parallel; each tool respects this internally).
SCAN_BUDGET_SEC = float(os.getenv("USERNAME_SCAN_BUDGET_SEC", "175"))
DUAL_USERNAME_SCAN_BUDGET_SEC = float(os.getenv("DUAL_USERNAME_SCAN_BUDGET_SEC", "150"))
SOCIAL_ANALYZER_BUDGET_SEC = float(os.getenv("SOCIAL_ANALYZER_BUDGET_SEC", "280"))
DUAL_SOCIAL_ANALYZER_BUDGET_SEC = float(os.getenv("DUAL_SOCIAL_ANALYZER_BUDGET_SEC", "180"))
GOOGLE_DORK_BUDGET_SEC = float(os.getenv("GOOGLE_DORK_BUDGET_SEC", "120"))
DUAL_GOOGLE_DORK_BUDGET_SEC = float(os.getenv("DUAL_GOOGLE_DORK_BUDGET_SEC", "90"))

FAST_USERNAME_SCAN_BUDGET_SEC = float(os.getenv("FAST_USERNAME_SCAN_BUDGET_SEC", "90"))
FAST_SOCIAL_ANALYZER_BUDGET_SEC = float(os.getenv("FAST_SOCIAL_ANALYZER_BUDGET_SEC", "60"))
FAST_GOOGLE_DORK_BUDGET_SEC = float(os.getenv("FAST_GOOGLE_DORK_BUDGET_SEC", "45"))
FAST_SOCIAL_ANALYZER_MAX_SITES = max(40, int(os.getenv("FAST_SOCIAL_ANALYZER_MAX_SITES", "80")))

# Phase 1: high-priority sites — verified cards should appear within this window.
PHASE1_BUDGET_SEC = float(os.getenv("USERNAME_SCAN_PHASE1_SEC", "45"))

TOP_PRIORITY_SITES = int(os.getenv("USERNAME_TOP_PRIORITY_SITES", "120"))

CHUNK_SIZE = int(os.getenv("USERNAME_CHUNK_SIZE", "32"))
PHASE1_PARALLEL = int(os.getenv("USERNAME_PHASE1_PARALLEL", "12"))
PHASE2_PARALLEL = int(os.getenv("USERNAME_PHASE2_PARALLEL", "10"))
SOCIAL_ANALYZER_CHUNK_SIZE = int(os.getenv("SOCIAL_ANALYZER_CHUNK_SIZE", "12"))
SOCIAL_ANALYZER_PHASE2_PARALLEL = int(os.getenv("SOCIAL_ANALYZER_PHASE2_PARALLEL", "12"))
SOCIAL_ANALYZER_MAX_SITES_DEFAULT = max(80, int(os.getenv("SOCIAL_ANALYZER_MAX_SITES", "200")))
MAIGRET_MAX_SITES_DEFAULT = max(80, int(os.getenv("MAIGRET_MAX_SITES", "280")))
SHERLOCK_MAX_SITES_DEFAULT = max(60, int(os.getenv("SHERLOCK_MAX_SITES", "180")))
FAST_MAIGRET_MAX_SITES = max(60, int(os.getenv("FAST_MAIGRET_MAX_SITES", "100")))
FAST_SHERLOCK_MAX_SITES = max(40, int(os.getenv("FAST_SHERLOCK_MAX_SITES", "80")))
DUAL_MAIGRET_MAX_SITES = max(60, int(os.getenv("DUAL_MAIGRET_MAX_SITES", "160")))
DUAL_SHERLOCK_MAX_SITES = max(40, int(os.getenv("DUAL_SHERLOCK_MAX_SITES", "120")))
SCAN_PROGRESS_SNAPSHOT_MAX = max(8, int(os.getenv("SCAN_PROGRESS_SNAPSHOT_MAX", "32")))
SITE_PROBE_TIMEOUT = int(os.getenv("USERNAME_SITE_TIMEOUT", "8"))


def _deep_mode() -> bool:
    from services.resource_guard import get_investigation_mode

    return get_investigation_mode() == "deep"


def social_analyzer_max_sites() -> int | None:
    """Cap site list so the scan finishes within the tool budget (999 sites always times out)."""
    if _deep_mode():
        return None
    cap = SOCIAL_ANALYZER_MAX_SITES_DEFAULT
    if _fast_mode():
        return min(cap, FAST_SOCIAL_ANALYZER_MAX_SITES)
    if _dual_mode():
        from services.resource_guard import DUAL_SOCIAL_ANALYZER_MAX_SITES

        return min(cap, DUAL_SOCIAL_ANALYZER_MAX_SITES)
    return cap


def maigret_max_sites() -> int | None:
    """Cap Maigret inventory — full 3000+ site scans OOM typical laptops."""
    if _deep_mode():
        return None
    cap = MAIGRET_MAX_SITES_DEFAULT
    if _fast_mode():
        return min(cap, FAST_MAIGRET_MAX_SITES)
    if _dual_mode():
        return min(cap, DUAL_MAIGRET_MAX_SITES)
    return cap


def sherlock_max_sites() -> int | None:
    if _deep_mode():
        return None
    cap = SHERLOCK_MAX_SITES_DEFAULT
    if _fast_mode():
        return min(cap, FAST_SHERLOCK_MAX_SITES)
    if _dual_mode():
        return min(cap, DUAL_SHERLOCK_MAX_SITES)
    return cap


def _fast_mode() -> bool:
    from services.resource_guard import get_investigation_mode

    return get_investigation_mode() == "fast"


def _dual_mode() -> bool:
    from services.resource_guard import is_dual_identity_scan, is_full_scan_mode

    return is_dual_identity_scan() and not is_full_scan_mode()


def phase1_parallel() -> int:
    if _dual_mode():
        from services.resource_guard import DUAL_USERNAME_PHASE1_PARALLEL

        return DUAL_USERNAME_PHASE1_PARALLEL
    return PHASE1_PARALLEL


def phase2_parallel() -> int:
    if _dual_mode():
        from services.resource_guard import DUAL_USERNAME_PHASE2_PARALLEL

        return DUAL_USERNAME_PHASE2_PARALLEL
    return PHASE2_PARALLEL


def social_analyzer_phase2_parallel() -> int:
    if _dual_mode():
        from services.resource_guard import DUAL_SOCIAL_ANALYZER_PHASE2_PARALLEL

        return DUAL_SOCIAL_ANALYZER_PHASE2_PARALLEL
    return SOCIAL_ANALYZER_PHASE2_PARALLEL


def scan_budget_sec() -> float:
    if _fast_mode():
        return FAST_USERNAME_SCAN_BUDGET_SEC
    if _dual_mode():
        return DUAL_USERNAME_SCAN_BUDGET_SEC
    return SCAN_BUDGET_SEC


def social_analyzer_budget_sec() -> float:
    if _fast_mode():
        return FAST_SOCIAL_ANALYZER_BUDGET_SEC
    if _dual_mode():
        return DUAL_SOCIAL_ANALYZER_BUDGET_SEC
    return SOCIAL_ANALYZER_BUDGET_SEC


def google_dork_budget_sec() -> float:
    if _fast_mode():
        return FAST_GOOGLE_DORK_BUDGET_SEC
    if _dual_mode():
        return DUAL_GOOGLE_DORK_BUDGET_SEC
    return GOOGLE_DORK_BUDGET_SEC
