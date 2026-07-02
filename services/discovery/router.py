"""Route evidence-backed intelligence leads to orchestrator features."""

from __future__ import annotations

from uuid import uuid4

from schemas.discovery import DiscoveryLead, LeadType
from services.discovery.validators import (
    is_domain,
    is_email,
    is_fake_url_username,
    is_image_url,
    is_phone,
    is_plausible_handle,
    is_url,
    normalize_domain,
)
from services.query_detector import detect_query_type

FEATURE_FOR_QUERY_TYPE: dict[str, str] = {
    "username": "username_search",
    "email": "email_intel",
    "domain": "domain_intel",
    "image": "image_intel",
    "phone": "infra_intel",
    "infra": "infra_intel",
}


def route_lead_query(
    query: str,
    lead_type: LeadType | str | None = None,
) -> tuple[str, str, str] | None:
    """Map an evidence-backed lead to (feature, normalized_query, lead_type)."""
    q = query.strip()
    if not q or q in ("!!!", "—", "-"):
        return None

    # Never route URL-shaped values to username discovery tools.
    if lead_type == "username":
        if is_url(q) or is_fake_url_username(q) or not is_plausible_handle(q):
            return None
        return ("username_search", q.lower(), "username")

    if lead_type == "account":
        if is_url(q):
            return None
        if ":" in q and not q.startswith("http"):
            handle = q.split(":", 1)[1].strip().lower()
            if is_plausible_handle(handle) and not is_fake_url_username(handle):
                return ("username_search", handle, "username")
        return None

    if lead_type in ("name", "organization", "url"):
        return None

    if is_image_url(q):
        return ("image_intel", q, "image")

    if q.startswith(("http://", "https://")):
        domain = normalize_domain(q)
        if domain:
            return ("domain_intel", domain, "domain")
        return None

    if lead_type == "image" and is_image_url(q):
        return ("image_intel", q, "image")

    if lead_type == "email" and is_email(q):
        return ("email_intel", q.lower(), "email")

    if lead_type == "phone" and is_phone(q):
        return ("infra_intel", q, "phone")

    if lead_type == "domain":
        domain = normalize_domain(q)
        if domain:
            return ("domain_intel", domain, "domain")

    if is_email(q):
        return ("email_intel", q.lower(), "email")

    if is_phone(q):
        return ("infra_intel", q, "phone")

    domain = normalize_domain(q)
    if domain and is_domain(domain):
        return ("domain_intel", domain, "domain")

    if lead_type and lead_type in FEATURE_FOR_QUERY_TYPE:
        feature = FEATURE_FOR_QUERY_TYPE[lead_type]
        if feature == "username_search":
            return None
        return (feature, q, str(lead_type))

    detected = detect_query_type(q)
    if detected == "username":
        return None
    feature = FEATURE_FOR_QUERY_TYPE.get(detected)
    if feature:
        return (feature, q, detected)
    return None


def build_routable_lead(
    query: str,
    *,
    lead_type: LeadType | str = "username",
    depth: int = 1,
    priority: float = 0.5,
    source_entity_id: str | None = None,
    source_entity_type: str | None = None,
    source_query: str | None = None,
    reason: str = "",
    metadata: dict | None = None,
) -> DiscoveryLead | None:
    routed = route_lead_query(query, lead_type=lead_type)
    if not routed:
        return None
    feature, routed_query, resolved_type = routed
    return DiscoveryLead(
        lead_id=str(uuid4()),
        query=routed_query,
        lead_type=resolved_type,  # type: ignore[arg-type]
        feature=feature,
        depth=depth,
        priority=min(1.0, max(0.0, priority)),
        source_entity_id=source_entity_id,
        source_entity_type=source_entity_type,
        source_query=source_query,
        reason=reason,
        metadata=metadata or {},
    )
