"""Entity processors — each returns PivotResult with evidence + generated_leads."""

from __future__ import annotations

import os
from uuid import uuid4

from schemas.discovery import DiscoveryLead
from schemas.fusion import Entity
from schemas.pivot import PivotEvidence, PivotOpportunity, PivotResult
from services.discovery.attribution import (
    account_handle_matches_seed,
    email_linked_to_seed,
    entity_image_attributed,
    extract_phones_from_text,
    is_image_seed_query,
    phone_attributed_to_username,
)
from services.query_detector import detect_query_type
from services.reverse_image.extractors import extract_usernames_from_url
from services.discovery.profile import ProfileIntelligence, build_profile_intelligence
from services.discovery.router import build_routable_lead
from services.discovery.validators import extract_emails_from_text, is_email, is_image_url, is_phone, is_plausible_handle, is_known_platform_domain, normalize_domain
from services.pivot.registry import opportunities_for

TYPE_PRIORITY_BOOST: dict[str, float] = {
    "email": 0.18,
    "domain": 0.14,
    "image": 0.12,
    "phone": 0.1,
    "username": 0.06,
}


def _email_matches_seed(email: str, seed_query: str) -> bool:
    return email_linked_to_seed(email, seed_query)


def _should_pivot_username(handle: str, source_query: str) -> bool:
    """Block junk handles and unrelated username hops during username investigations."""
    if not is_plausible_handle(handle):
        return False
    from services.correlation.handle_quality import is_correlatable_handle

    if not is_correlatable_handle(handle):
        return False
    if detect_query_type(source_query) == "username":
        return account_handle_matches_seed(handle, source_query)
    return True


def _is_expandable(entity: Entity, *, source_query: str = "") -> bool:
    meta = entity.metadata or {}
    if meta.get("investigation_lead") or meta.get("status") == "rate_limited":
        return False
    if meta.get("check_type") in ("google_dork", "dataset_lookup") and not meta.get("verified"):
        return False
    if meta.get("pivotable") is False:
        return False
    if entity.type in ("document", "domain") and meta.get("check_type") == "google_dork":
        return False
    if entity.type == "document" and meta.get("reverse_image_match"):
        return True
    if entity.type == "email" and meta.get("check_type") == "google_dork" and not meta.get("username_attributed"):
        if not entity_image_attributed(meta):
            return False
    # Technical image signals (hashes, embeddings) are not investigation leads.
    if entity.type == "image" and meta.get("category") in ("fingerprint", "face") and not meta.get("reverse_image_match"):
        if meta.get("field") in (
            "face_embedding", "perceptual_hash_ahash", "perceptual_hash_phash",
            "perceptual_hash_dhash", "perceptual_hash_whash", "opencv_orb_signature",
        ):
            return False
    if entity.type == "account":
        if meta.get("reverse_image_match") or meta.get("image_attributed") or meta.get("pivotable"):
            return True
        if entity.value.startswith("image_ocr:"):
            return True
        if not (meta.get("verified") or meta.get("registered")):
            return False
    if entity.type == "account" and meta.get("corroboration_status") not in (None, "confirmed"):
        sources = set(entity.sources)
        if "holehe" in sources and not (sources & {"sherlock", "maigret", "social_analyzer"}):
            return False
    if entity.type == "email" and is_image_seed_query(source_query):
        if entity_image_attributed(meta):
            return True
    return True


def _priority(entity: Entity, depth: int, lead_type: str, boost: float = 0.0) -> float:
    base = float(entity.fusion_score or 0.5)
    type_boost = TYPE_PRIORITY_BOOST.get(lead_type, 0.03)
    return max(0.1, min(1.0, base + type_boost + boost - (0.05 * depth)))


def _evidence(
    entity: Entity,
    *,
    field: str,
    value: str,
    strategy: str,
    platform: str = "",
    confidence: float = 0.75,
) -> PivotEvidence:
    return PivotEvidence(
        evidence_id=str(uuid4()),
        entity_id=entity.entity_id,
        entity_type=entity.type,
        field=field,
        value=value,
        source_tool=entity.sources[0] if entity.sources else None,
        source_platform=platform or str((entity.metadata or {}).get("platform", "")),
        source_ref=str((entity.metadata or {}).get("url") or entity.value),
        strategy=strategy,
        confidence=confidence,
    )


def _lead_from_value(
    entity: Entity,
    profile: ProfileIntelligence | None,
    *,
    query: str,
    lead_type: str,
    depth: int,
    source_query: str,
    field: str,
    strategy: str,
    evidence: str,
    priority_boost: float = 0.0,
) -> DiscoveryLead | None:
    return build_routable_lead(
        query,
        lead_type=lead_type,
        depth=depth,
        priority=_priority(entity, depth, lead_type, priority_boost),
        source_entity_id=entity.entity_id,
        source_entity_type=entity.type,
        source_query=source_query,
        reason=f"{strategy}: {field}",
        metadata={
            "expansion_strategy": strategy,
            "source_field": field,
            "evidence": evidence,
            "pivot": True,
            **(profile.provenance if profile else {}),
        },
    )


def process_entity(
    entity: Entity,
    *,
    source_query: str,
    depth: int,
    max_leads: int = 20,
) -> PivotResult:
    """Generic pivot processor — delegates by entity type via opportunity registry."""
    if not _is_expandable(entity, source_query=source_query):
        return PivotResult(opportunities=opportunities_for(entity.type))

    profile = build_profile_intelligence(entity)
    opportunities = opportunities_for(entity.type)
    evidence: list[PivotEvidence] = []
    leads: list[DiscoveryLead] = []
    seen: set[str] = set()

    def add_lead(query: str, lead_type: str, field: str, strategy: str, ev: str, boost: float = 0.0) -> None:
        if len(leads) >= max_leads:
            return
        if lead_type == "username" and not _should_pivot_username(query, source_query):
            return
        key = f"{lead_type}:{query.lower()}"
        if key in seen:
            return
        lead = _lead_from_value(
            entity, profile, query=query, lead_type=lead_type, depth=depth,
            source_query=source_query, field=field, strategy=strategy, evidence=ev,
            priority_boost=boost,
        )
        if lead:
            seen.add(key)
            leads.append(lead)

    if entity.type == "account":
        meta = entity.metadata or {}
        handle = profile.handle
        if entity.value.startswith("image_ocr:"):
            handle = entity.value.split(":", 1)[1].strip().lower()
            evidence.append(_evidence(entity, field="username", value=handle, strategy="image_ocr_username", confidence=0.78))
            if is_plausible_handle(handle):
                add_lead(handle, "username", "username", "image_ocr_username_pivot", handle, 0.12)
        if profile.display_name:
            evidence.append(_evidence(entity, field="display_name", value=profile.display_name, strategy="account_display_name", platform=profile.platform))
        if profile.bio:
            evidence.append(_evidence(entity, field="bio", value=profile.bio, strategy="account_bio", platform=profile.platform))
        if profile.location:
            evidence.append(_evidence(entity, field="location", value=profile.location, strategy="account_location", platform=profile.platform))
        if profile.email and is_email(profile.email) and email_linked_to_seed(
            profile.email,
            source_query,
            profile_url=profile.profile_url,
            handle=profile.handle,
        ):
            evidence.append(_evidence(entity, field="email", value=profile.email, strategy="account_email", platform=profile.platform, confidence=0.85))
            add_lead(profile.email, "email", "email", "account_email_pivot", profile.email, 0.08)

        if account_handle_matches_seed(profile.handle, source_query, profile.profile_url):
            contact_blob = " ".join(p for p in (profile.bio, profile.display_name) if p)
            for found_email in extract_emails_from_text(contact_blob):
                if is_email(found_email) and email_linked_to_seed(
                    found_email, source_query, profile_url=profile.profile_url, handle=profile.handle,
                ):
                    evidence.append(_evidence(entity, field="email", value=found_email, strategy="account_bio_email", platform=profile.platform, confidence=0.82))
                    add_lead(found_email, "email", "email", "account_bio_email_pivot", found_email, 0.07)
            for found_phone in extract_phones_from_text(contact_blob):
                if is_phone(found_phone) and phone_attributed_to_username(
                    found_phone,
                    source_query,
                    source_url=profile.profile_url,
                    title=profile.display_name or "",
                    snippet=profile.bio or "",
                ):
                    evidence.append(_evidence(entity, field="phone", value=found_phone, strategy="account_bio_phone", platform=profile.platform, confidence=0.8))
                    add_lead(found_phone, "phone", "phone", "account_phone_pivot", found_phone, 0.06)
        for domain in profile.website_domains:
            if is_known_platform_domain(domain):
                continue
            account_platform = normalize_domain(profile.platform) if profile.platform else None
            if account_platform and normalize_domain(domain) == account_platform:
                continue
            evidence.append(_evidence(entity, field="website", value=domain, strategy="account_website", platform=profile.platform))
            add_lead(domain, "domain", "website", "account_website_pivot", domain)
        for image_url in profile.image_urls:
            evidence.append(_evidence(entity, field="avatar_url", value=image_url, strategy="account_profile_image", platform=profile.platform))
            # Username investigations: keep profile photos as evidence only — no reverse-image hops.
            if detect_query_type(source_query) != "username":
                add_lead(image_url, "image", "avatar_url", "account_image_pivot", image_url)
        for org in profile.organizations:
            evidence.append(_evidence(entity, field="organization", value=org, strategy="account_organization", platform=profile.platform))
            domain = normalize_domain(org)
            if domain:
                add_lead(domain, "domain", "organization", "account_org_pivot", org)
        if profile.handle and is_plausible_handle(profile.handle):
            evidence.append(_evidence(entity, field="username", value=profile.handle, strategy="account_username", platform=profile.platform))
            add_lead(profile.handle, "username", "handle", "account_handle_pivot", profile.handle)
        elif meta.get("reverse_image_match") and entity.value.startswith("http"):
            for handle in extract_usernames_from_url(entity.value):
                evidence.append(_evidence(entity, field="username", value=handle, strategy="reverse_image_profile_username", confidence=0.82))
                add_lead(handle, "username", "username", "reverse_image_profile_username_pivot", handle, 0.14)

    elif entity.type == "email" and is_email(entity.value):
        meta = entity.metadata or {}
        if not email_linked_to_seed(
            entity.value,
            source_query,
            profile_url=str(meta.get("source_url") or meta.get("url") or ""),
            username_attributed=bool(meta.get("username_attributed")),
            handle=str(meta.get("username") or meta.get("handle") or ""),
            entity_meta=meta,
        ):
            return PivotResult(opportunities=opportunities_for(entity.type))
        evidence.append(_evidence(entity, field="email", value=entity.value.lower(), strategy="email_discovery", confidence=0.85))
        add_lead(entity.value.lower(), "email", "email", "email_account_pivot", entity.value, 0.1)

    elif entity.type == "phone" and is_phone(entity.value):
        meta = entity.metadata or {}
        if not meta.get("username_attributed") and not entity_image_attributed(meta):
            return PivotResult(opportunities=opportunities_for(entity.type))
        evidence.append(_evidence(entity, field="phone", value=entity.value.strip(), strategy="phone_discovery"))
        add_lead(entity.value.strip(), "phone", "phone", "phone_reference_pivot", entity.value)

    elif entity.type == "domain":
        domain = normalize_domain(entity.value) or entity.value
        evidence.append(_evidence(entity, field="domain", value=domain, strategy="website_domain"))
        if not is_known_platform_domain(domain):
            add_lead(domain, "domain", "domain", "domain_enrichment_pivot", domain)

    elif entity.type == "document":
        meta = entity.metadata or {}
        org = str(meta.get("organization") or entity.value).strip()
        if org and (meta.get("reverse_image_match") or entity_image_attributed(meta)):
            evidence.append(_evidence(entity, field="organization", value=org, strategy="reverse_image_organization", confidence=0.72))
            domain = normalize_domain(org)
            if domain and not is_known_platform_domain(domain):
                add_lead(domain, "domain", "organization", "organization_domain_pivot", org)

    elif entity.type == "image":
        image_url = profile.profile_url or entity.value
        meta = entity.metadata or {}
        if image_url and is_image_url(image_url) and meta.get("reverse_image_match"):
            evidence.append(_evidence(entity, field="image_url", value=image_url, strategy="image_source_reference"))
            add_lead(image_url, "image", "image", "image_similarity_pivot", image_url, 0.08)
        for linked in meta.get("linked_profiles") or meta.get("profile_urls") or []:
            if isinstance(linked, str) and linked.startswith("http"):
                evidence.append(_evidence(entity, field="linked_profile", value=linked, strategy="reverse_image_match", confidence=0.8))
                routed_username = False
                for handle in extract_usernames_from_url(linked):
                    add_lead(handle, "username", "username", "reverse_image_username_pivot", handle, 0.14)
                    routed_username = True
                if not routed_username:
                    add_lead(linked, "image", "image", "reverse_image_pivot", linked, 0.1)
        if meta.get("reverse_image_match"):
            for profile_url in meta.get("profile_urls") or []:
                if isinstance(profile_url, str):
                    for handle in extract_usernames_from_url(profile_url):
                        add_lead(handle, "username", "username", "reverse_image_entity_username_pivot", handle, 0.15)

    leads.sort(key=lambda item: -item.priority)
    return PivotResult(evidence=evidence, generated_leads=leads[:max_leads], opportunities=opportunities)


def process_result(
    result,
    *,
    source_query: str,
    depth: int,
    max_leads: int = 20,
) -> PivotResult:
    """Process all entities from a feature result."""
    from schemas.common import FeatureResult

    if not isinstance(result, FeatureResult):
        return PivotResult()

    entities = (result.fusion.deduplicated_entities if result.fusion else []) or []
    all_evidence: list[PivotEvidence] = []
    all_leads: list[DiscoveryLead] = []
    all_opportunities: list[PivotOpportunity] = []
    seen: set[str] = set()

    for entity in entities:
        pivot = process_entity(entity, source_query=source_query, depth=depth, max_leads=max_leads)
        all_evidence.extend(pivot.evidence)
        all_opportunities.extend(pivot.opportunities)
        for lead in pivot.generated_leads:
            key = f"{lead.lead_type}:{lead.query.lower()}"
            if key in seen:
                continue
            seen.add(key)
            all_leads.append(lead)
            if len(all_leads) >= max_leads:
                break
        if len(all_leads) >= max_leads:
            break

    all_leads.sort(key=lambda item: -item.priority)
    return PivotResult(
        evidence=all_evidence,
        generated_leads=all_leads[:max_leads],
        opportunities=all_opportunities,
    )
