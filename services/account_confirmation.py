"""Shared account confirmation — any platform, not a fixed site list."""

from __future__ import annotations

from services.discovery.validators import DEFINITIVE_VERIFY_FAILURES, normalize_domain, verify_blocks_account_confirmation

USERNAME_TOOLS = frozenset({"sherlock", "maigret", "social_analyzer", "platform_probe"})

PROBE_TOOLS = frozenset({"sherlock", "platform_probe", "social_analyzer"})

TOOL_LIVE_CONFIRMED_STATUSES = frozenset({
    "maigret_claimed",
    "registered",
})

def _has_maigret_claimed(meta: dict, sources: set[str] | frozenset[str]) -> bool:
    if "maigret" not in sources:
        return False
    if meta.get("status") in TOOL_LIVE_CONFIRMED_STATUSES:
        return True
    details = meta.get("source_details") or {}
    if isinstance(details, dict):
        maigret = details.get("maigret")
        if isinstance(maigret, dict):
            if maigret.get("status") in TOOL_LIVE_CONFIRMED_STATUSES:
                return True
            if maigret.get("verified") and maigret.get("check_type") == "live_scan":
                return True
    if meta.get("verified") and meta.get("check_type") == "live_scan" and meta.get("contributing_source") == "maigret":
        return True
    return False


def should_skip_http_reverify(meta: dict) -> bool:
    """Maigret already live-checked the URL — skip redundant HTTP fetch."""
    if meta.get("check_type") != "live_scan":
        return False
    if meta.get("probe_source") == "platform_probe":
        return False
    if meta.get("status") in TOOL_LIVE_CONFIRMED_STATUSES:
        return True
    if meta.get("registered") and meta.get("status") == "registered":
        return True
    return False


def is_holehe_email_registration(meta: dict, sources: set[str] | frozenset[str]) -> bool:
    """Holehe live registration for a specific email address."""
    if "holehe" not in sources:
        return False
    if not (meta.get("registered") or meta.get("status") == "registered"):
        return False
    reg_email = str(meta.get("email") or "").lower().strip()
    if not reg_email or "@" not in reg_email:
        return False
    platform = str(meta.get("platform") or "")
    if not platform or platform.startswith("_"):
        return False
    return True


def _handle_passes_quality(meta: dict) -> bool:
    from services.correlation.handle_quality import is_plausible_handle_for_correlation, normalize_profile_handle

    platform = str(meta.get("platform") or "")
    url = str(meta.get("url") or meta.get("profile_url") or "")
    handle = normalize_profile_handle(url, platform, meta)
    if not handle:
        return False
    return is_plausible_handle_for_correlation(handle)


def account_confirmed(
    meta: dict,
    sources: set[str] | frozenset[str] | None = None,
    *,
    seed_email: str | None = None,
) -> bool:
    """True when a discovered account should be shown as verified to the investigator."""
    src = set(sources or ())
    if verify_blocks_account_confirmation(meta):
        return False
    if meta.get("status") == "unavailable" or meta.get("corroboration_status") == "unavailable":
        return False
    if is_holehe_email_registration(meta, src):
        reg_email = str(meta.get("email") or "").lower().strip()
        if seed_email and reg_email == seed_email.lower().strip():
            return True
    if "holehe" in src and not (src & USERNAME_TOOLS):
        return False
    if not _handle_passes_quality(meta):
        return False

    username_hits = src & USERNAME_TOOLS

    if meta.get("enrichment_source") and meta.get("verified"):
        return True
    if meta.get("check_type") == "google_dork_profile":
        return False

    if not username_hits:
        return False

    if meta.get("content_seed_verified") is False:
        return False

    # Username scanners only produce probe candidates unless Maigret live-confirmed the URL.
    if meta.get("check_type") == "username_probe" and not _has_maigret_claimed(meta, src):
        return False

    # platform_probe is a hint only — never sufficient alone.
    if username_hits == {"platform_probe"}:
        return False

    # Maigret live scan — trust on any platform (per-site HTTP existence check).
    if _has_maigret_claimed(meta, src):
        return True

    # Social Analyzer live detection + HTTP body references the seed handle.
    if (
        "social_analyzer" in src
        and meta.get("status") == "social_analyzer_detected"
        and meta.get("live_profile_verified") is True
        and meta.get("content_seed_verified") is True
    ):
        return True

    return False
