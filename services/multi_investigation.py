"""Merge parallel feature runs from multi-input investigations."""

from __future__ import annotations

from schemas.common import FeatureResult
from schemas.intelligence import FieldProvenance
from services.fusion import build_fusion_output
from services.multi_input import InvestigationInputs, attribution_seed_from_raw, attribution_seed_query


async def merge_feature_results(
    results: list[FeatureResult],
    *,
    seed_query: str,
    parsed: InvestigationInputs | None = None,
) -> FeatureResult:
    """Combine tool outputs from parallel email/username/domain runs."""
    from services.correlation.engine import correlation_engine
    from services.evidence.engine import evidence_engine
    from services.evidence.profile_verifier import refine_username_fusion
    from services.graph_intelligence.engine import graph_engine
    from services.intelligence.person import build_identity_profile
    from services.json_utils import to_json_safe
    from services.normalization import build_confidence_inputs, normalize_tool_results

    tool_results: list = []
    warnings: list[str] = []
    total_ms = 0.0
    confirmed_findings: list = []
    public_profile_data: list = []
    investigation_leads: list = []
    scan_summary: dict = {}
    for r in results:
        tool_results.extend(r.tool_results)
        warnings.extend(r.warnings or [])
        total_ms = max(total_ms, r.total_execution_time_ms or 0)
        confirmed_findings.extend(r.confirmed_findings or [])
        public_profile_data.extend(r.public_profile_data or [])
        investigation_leads.extend(r.investigation_leads or [])
        if r.scan_summary:
            scan_summary.update(r.scan_summary)

    attribution_seed = (
        attribution_seed_query(parsed) if parsed else attribution_seed_from_raw(seed_query)
    )
    fusion_query = parsed.username if parsed and parsed.username else attribution_seed

    normalized = normalize_tool_results(tool_results)
    fusion = build_fusion_output(
        tool_results,
        "multi",
        fusion_query,
        confirmed_findings=confirmed_findings,
        public_profile_data=public_profile_data,
        investigation_leads=investigation_leads,
    )
    if any(r.feature == "username_search" for r in results):
        fusion = await refine_username_fusion(fusion, seed_query=attribution_seed)

    evidence_extraction = None
    identity_profile = None
    if fusion.deduplicated_entities:
        fusion, evidence_extraction = await evidence_engine.extract(
            fusion,
            seed_query=attribution_seed,
            seed_email=parsed.email if parsed else None,
            enrich_public_profiles=True,
            tool_results=tool_results,
        )
        identity_profile = build_identity_profile(
            seed_query=seed_query,
            fusion=fusion,
            evidence_extraction=evidence_extraction,
            enrichment_pass=1,
        )
        if parsed:
            identity_profile = inject_parsed_fields(identity_profile, parsed)

    correlation = await correlation_engine.correlate(fusion, seed_query=attribution_seed)
    graph = graph_engine.analyze(
        fusion,
        correlation,
        seed_query=attribution_seed,
        identity_profile=identity_profile,
        evidence_extraction=evidence_extraction,
    )

    succeeded = sum(1 for r in tool_results if r.success)
    return FeatureResult(
        feature="multi",
        query=seed_query,
        warnings=warnings,
        tool_results=tool_results,
        merged_results=to_json_safe(normalized),
        fusion=fusion,
        correlation=correlation,
        graph=graph,
        evidence_extraction=evidence_extraction,
        identity_profile=identity_profile,
        confirmed_findings=confirmed_findings,
        public_profile_data=public_profile_data,
        investigation_leads=investigation_leads,
        scan_summary=scan_summary or None,
        confidence_raw_inputs=build_confidence_inputs(tool_results),
        total_execution_time_ms=total_ms,
        tools_succeeded=succeeded,
        tools_failed=len(tool_results) - succeeded,
    )


def inject_parsed_fields(profile, parsed: InvestigationInputs):
    """Ensure user-supplied fields appear in the identity profile."""
    updates = []
    if parsed.name:
        updates.append(FieldProvenance(field="name", value=parsed.name, confidence=0.95, source_tool="user_input"))
    if parsed.occupation:
        updates.append(
            FieldProvenance(field="occupation", value=parsed.occupation, confidence=0.95, source_tool="user_input")
        )
    if parsed.company:
        updates.append(
            FieldProvenance(field="organization", value=parsed.company, confidence=0.95, source_tool="user_input")
        )
    if parsed.username:
        updates.append(
            FieldProvenance(field="username", value=parsed.username, confidence=0.95, source_tool="user_input")
        )
    if parsed.email:
        updates.append(FieldProvenance(field="email", value=parsed.email, confidence=0.95, source_tool="user_input"))

    if not updates:
        return profile

    names = list(profile.names)
    orgs = list(profile.organizations)
    usernames = list(profile.usernames)
    emails = list(profile.emails)
    search = list(profile.search_findings)

    for fp in updates:
        if fp.field == "name" and not any(n.value.lower() == fp.value.lower() for n in names):
            names.append(fp)
        elif fp.field == "occupation" and not any(o.value.lower() == fp.value.lower() for o in orgs):
            orgs.append(fp)
            search.append(fp)
        elif fp.field == "organization" and not any(o.value.lower() == fp.value.lower() for o in orgs):
            orgs.append(fp)
        elif fp.field == "username" and not any(u.value.lower() == fp.value.lower() for u in usernames):
            usernames.append(fp)
        elif fp.field == "email" and not any(e.value.lower() == fp.value.lower() for e in emails):
            emails.append(fp)

    return profile.model_copy(
        update={
            "names": names,
            "organizations": orgs,
            "usernames": usernames,
            "emails": emails,
            "search_findings": search,
            "primary_name": profile.primary_name or parsed.name,
            "total_evidence_fields": profile.total_evidence_fields + len(updates),
        }
    )


def reapply_parsed_identity(profile, seed_query: str):
    """Re-inject user-supplied fields after discovery re-builds the profile."""
    from services.multi_input import parse_investigation_input

    parsed = parse_investigation_input(seed_query)
    if parsed.username or parsed.email or parsed.name or parsed.occupation or parsed.company:
        return inject_parsed_fields(profile, parsed)
    return profile
