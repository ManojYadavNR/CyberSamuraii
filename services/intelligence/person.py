"""Person-centric intelligence layer — aggregate all evidence into identity profile."""

from __future__ import annotations

from datetime import datetime, timezone

from services.evidence.document_parser import parse_dork_document
from services.fusion_engine import is_confirmed_account
from services.image_intelligence.path_utils import display_target_label, is_local_path
from schemas.evidence import EvidenceExtractionOutput, FieldProvenance, UnifiedPersonProfile
from schemas.fusion import Entity, FusionOutput
from schemas.intelligence import (
    IdentityProfile,
    IdentityRelationship,
    IdentityTimelineEvent,
    SupportingEvidence,
)
from schemas.pivot import InvestigationTree, PivotEvidence


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fp_to_supporting(fp: FieldProvenance) -> SupportingEvidence:
    return SupportingEvidence(
        field=fp.field,
        value=fp.value,
        confidence=fp.confidence,
        source_platform=fp.source_platform,
        source_tool=fp.source_tool,
        source_ref=fp.source_ref,
        extraction_strategy=fp.extraction_strategy,
    )


def _confidence_from_entities(entities: list[Entity], field_count: int) -> float:
    if not entities:
        return 0.0
    scores = [e.fusion_score for e in entities if e.fusion_score > 0]
    base = sum(scores) / len(scores) if scores else 0.3
    corroboration = min(0.3, 0.03 * len(set(e.type for e in entities)))
    field_boost = min(0.25, 0.01 * field_count)
    return round(min(1.0, base + corroboration + field_boost), 4)


def _social_accounts_from_profiles(unified: UnifiedPersonProfile | None) -> list[FieldProvenance]:
    if not unified:
        return []
    accounts: list[FieldProvenance] = []
    for pp in unified.platform_profiles:
        if pp.url or pp.handle:
            accounts.append(FieldProvenance(
                field="social_account",
                value=f"{pp.platform}:{pp.handle}" if pp.handle else (pp.url or pp.platform),
                source_entity_id=pp.entity_id,
                source_entity_type="account",
                source_platform=pp.platform,
                source_ref=pp.url,
                extraction_strategy="platform_profile",
                confidence=min(1.0, pp.fusion_score or 0.5),
            ))
    return accounts


def build_identity_profile(
    *,
    seed_query: str,
    fusion: FusionOutput | None = None,
    evidence_extraction: EvidenceExtractionOutput | None = None,
    investigation_tree: InvestigationTree | None = None,
    pivot_evidence: list[PivotEvidence] | None = None,
    enrichment_pass: int = 1,
) -> IdentityProfile:
    """Continuously enrich person-centric profile from all discovered intelligence."""
    unified = evidence_extraction.unified_profile if evidence_extraction else None
    entities = fusion.deduplicated_entities if fusion else []
    confirmed_entities = [e for e in entities if e.type != "account" or is_confirmed_account(e)]

    phones: list[FieldProvenance] = []
    domains: list[FieldProvenance] = []
    schools: list[FieldProvenance] = []
    achievements: list[FieldProvenance] = []
    projects: list[FieldProvenance] = []
    events: list[FieldProvenance] = []
    publications: list[FieldProvenance] = []
    appearances: list[FieldProvenance] = []

    def _append_fp(target: list[FieldProvenance], field: str, value: str, entity: Entity, *, strategy: str = "", confidence: float = 0.7) -> None:
        meta = entity.metadata or {}
        target.append(FieldProvenance(
            field=field,
            value=value,
            source_entity_id=entity.entity_id,
            source_entity_type=entity.type,
            source_platform=str(meta.get("platform", "")),
            source_tool=entity.sources[0] if entity.sources else None,
            source_ref=str(meta.get("url") or entity.value),
            extraction_strategy=strategy,
            confidence=confidence,
        ))

    for entity in confirmed_entities:
        meta = entity.metadata or {}
        if entity.type == "phone":
            _append_fp(phones, "phone", entity.value, entity, confidence=entity.fusion_score or 0.75)
        if entity.type == "domain":
            _append_fp(domains, "domain", entity.value, entity, confidence=entity.fusion_score or 0.7)
        if entity.type == "document" and meta.get("check_type") == "google_dork":
            for field, value, strategy, confidence in parse_dork_document(meta, entity_value=entity.value, seed_query=seed_query):
                fp_entity = entity
                if field == "school":
                    _append_fp(schools, "school", value, fp_entity, strategy=strategy, confidence=confidence)
                elif field == "achievement":
                    _append_fp(achievements, "achievement", value, fp_entity, strategy=strategy, confidence=confidence)
                elif field == "event":
                    _append_fp(events, "event", value, fp_entity, strategy=strategy, confidence=confidence)
                elif field == "media_video":
                    _append_fp(events, "media_video", value, fp_entity, strategy=strategy, confidence=confidence)
                elif field in ("news", "article", "blog", "publication", "forum"):
                    _append_fp(publications, field, value, fp_entity, strategy=strategy, confidence=confidence)
                elif field == "appearance":
                    _append_fp(appearances, "appearance", value, fp_entity, strategy=strategy, confidence=confidence)
        for key, target_list, field_name in (
            ("school", schools, "school"),
            ("education", schools, "school"),
            ("achievement", achievements, "achievement"),
            ("project", projects, "project"),
        ):
            val = meta.get(key) or meta.get(f"{key}s")
            if isinstance(val, str):
                target_list.append(FieldProvenance(field=field_name, value=val, source_entity_id=entity.entity_id, source_entity_type=entity.type, source_platform=str(meta.get("platform", "")), confidence=entity.fusion_score))
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        target_list.append(FieldProvenance(field=field_name, value=item, source_entity_id=entity.entity_id, source_entity_type=entity.type, confidence=entity.fusion_score))
        achievement_val = meta.get("achievement")
        if isinstance(achievement_val, str) and achievement_val.strip():
            _append_fp(achievements, "achievement", achievement_val.strip(), entity, strategy=str(meta.get("enrichment_source") or "metadata_achievement"), confidence=0.8)
        for school in (meta.get("schools") or []):
            if isinstance(school, str):
                _append_fp(schools, "school", school, entity, strategy="deep_education", confidence=0.75)
        for post in (meta.get("recent_posts") or [])[:5]:
            if isinstance(post, str):
                _append_fp(events, "recent_post", post, entity, strategy="deep_recent_post", confidence=0.72)

    if unified:
        profile_photos: list[FieldProvenance] = []
        for pp in unified.platform_profiles:
            if not pp.verified:
                continue
            for fp in pp.extracted_fields:
                if fp.field == "phone":
                    phones.append(fp)
                elif fp.field == "school":
                    schools.append(fp)
                elif fp.field in ("video", "media_video"):
                    events.append(fp)
                elif fp.field in ("avatar_url", "image"):
                    profile_photos.append(fp)
                elif fp.field == "email":
                    pass
            if pp.avatar_url:
                profile_photos.append(FieldProvenance(
                    field="avatar_url",
                    value=pp.avatar_url,
                    source_entity_id=pp.entity_id,
                    source_entity_type="account",
                    source_platform=pp.platform,
                    source_ref=pp.url,
                    extraction_strategy="platform_avatar",
                    confidence=min(1.0, pp.fusion_score or 0.75),
                ))
        for fp in unified.search_findings:
            if fp.field in ("avatar_url", "image", "image_url") and fp.value.startswith("http"):
                profile_photos.append(fp)
        deduped_photos = {fp.value.lower(): fp for fp in (list(unified.images) + profile_photos)}
        if unified.primary_avatar:
            deduped_photos.setdefault(
                unified.primary_avatar.lower(),
                FieldProvenance(
                    field="avatar_url",
                    value=unified.primary_avatar,
                    source_tool="enrichment",
                    extraction_strategy="primary_avatar",
                    confidence=0.85,
                ),
            )
        unified_images = list(deduped_photos.values())
    else:
        unified_images = []

    def _dedupe_fps(items: list[FieldProvenance]) -> list[FieldProvenance]:
        seen: set[tuple[str, str]] = set()
        out: list[FieldProvenance] = []
        for fp in sorted(items, key=lambda x: -(x.confidence or 0)):
            key = (fp.field, fp.value.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(fp)
        return out

    phones = _dedupe_fps(phones)
    from services.fusion_engine import normalize_phone
    from services.query_detector import detect_query_type

    if detect_query_type(seed_query) == "phone":
        seed_phone = normalize_phone(seed_query)
        if seed_phone:
            phones.insert(
                0,
                FieldProvenance(
                    field="phone",
                    value=seed_phone,
                    source_tool="seed",
                    extraction_strategy="seed_query",
                    confidence=0.95,
                ),
            )
    schools = _dedupe_fps(schools)
    achievements = _dedupe_fps(achievements)
    events = _dedupe_fps(events)
    projects = _dedupe_fps(projects)
    publications = _dedupe_fps(publications)
    appearances = _dedupe_fps(appearances)

    supporting: list[SupportingEvidence] = []
    if unified:
        for group in (unified.names, unified.aliases, unified.usernames, unified.bios, unified.emails, unified.websites, unified.organizations, unified.images, unified.locations, unified.public_links, unified.search_findings):
            supporting.extend(_fp_to_supporting(fp) for fp in group)

    for ev in pivot_evidence or []:
        supporting.append(SupportingEvidence(
            field=ev.field, value=ev.value, confidence=ev.confidence,
            source_platform=ev.source_platform, source_tool=ev.source_tool,
            source_ref=ev.source_ref, extraction_strategy=ev.strategy,
        ))

    relationships: list[IdentityRelationship] = []
    if unified and unified.organizations:
        for org in unified.organizations:
            relationships.append(IdentityRelationship(
                relation_type="affiliated_with", target=org.value,
                confidence=org.confidence, source_ref=org.source_ref,
                provenance={"field": org.field, "strategy": org.extraction_strategy},
            ))

    timeline: list[IdentityTimelineEvent] = []
    if investigation_tree:
        for node in investigation_tree.nodes:
            if node.node_type in ("evidence", "lead", "hop"):
                timeline.append(IdentityTimelineEvent(
                    timestamp=_utc_now(),
                    event_type=node.node_type,
                    description=node.label,
                    source=node.provenance.get("source_ref") or node.provenance.get("reason"),
                    confidence=float(node.provenance.get("confidence", 0.5)),
                    metadata={"node_id": node.node_id, "depth": node.depth, **node.provenance},
                ))

    total_fields = (
        len(unified.names if unified else []) + len(unified.emails if unified else []) +
        len(unified.bios if unified else []) + len(unified.search_findings if unified else []) +
        len(phones) + len(domains) +
        len(schools) + len(achievements) + len(projects) + len(events) +
        len(publications) + len(appearances) + len(supporting)
    )

    face_detected = bool(unified and (unified.images or any(
        fp.field in ("face_embedding", "image_face_crop") for fp in supporting
    )))
    raw_name = unified.primary_display_name if unified else None
    if raw_name and is_local_path(raw_name):
        raw_name = None
    from services.query_detector import detect_query_type

    if detect_query_type(seed_query) == "phone":
        primary_name = display_target_label(seed_query, face_detected=face_detected)
    else:
        primary_name = raw_name or display_target_label(seed_query, face_detected=face_detected)
    display_seed = display_target_label(seed_query, face_detected=face_detected)

    return IdentityProfile(
        seed_query=display_seed,
        confidence_score=_confidence_from_entities(confirmed_entities, total_fields),
        primary_name=primary_name,
        primary_bio=unified.primary_bio if unified else None,
        primary_location=unified.primary_location if unified else None,
        primary_avatar=unified.primary_avatar if unified else None,
        names=list(unified.names) if unified else [],
        aliases=list(unified.aliases) if unified else [],
        usernames=list(unified.usernames) if unified else [],
        photos=unified_images if unified else [],
        emails=list(unified.emails) if unified else [],
        phones=phones,
        domains=domains,
        websites=list(unified.websites) if unified else [],
        organizations=list(unified.organizations) if unified else [],
        companies=list(unified.organizations) if unified else [],
        schools=schools,
        achievements=achievements,
        projects=projects,
        events=events,
        appearances=appearances,
        publications=publications,
        bios=list(unified.bios) if unified else [],
        locations=list(unified.locations) if unified else [],
        public_links=list(unified.public_links) if unified else [],
        search_findings=list(unified.search_findings) if unified else [],
        social_accounts=_social_accounts_from_profiles(unified),
        platform_profiles=list(unified.platform_profiles) if unified else [],
        supporting_evidence=supporting,
        relationships=relationships,
        timeline=timeline,
        investigation_tree=investigation_tree,
        verified_platform_count=max(
            len([p for p in unified.platform_profiles if p.verified]),
            unified.verified_platform_count,
        ) if unified else 0,
        total_evidence_fields=total_fields,
        enrichment_passes=enrichment_pass,
    )
