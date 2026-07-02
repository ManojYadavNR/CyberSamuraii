"""Merge per-hop investigation results into accumulated intelligence."""

from __future__ import annotations

from schemas.common import FeatureResult
from schemas.fusion import Entity, FusionOutput
from services.correlation.engine import correlation_engine
from services.evidence.engine import evidence_engine
from services.fusion_engine import deduplicate_entities
from services.graph_intelligence.engine import graph_engine


def _should_enrich_profiles(seed_query: str, fusion=None) -> bool:
    from services.query_detector import detect_query_type

    if detect_query_type(seed_query) == "username":
        return True
    if fusion and fusion.deduplicated_entities:
        for ent in fusion.deduplicated_entities:
            if ent.type == "account" and (
                ent.value.startswith("image_ocr:")
                or (ent.metadata or {}).get("reverse_image_match")
            ):
                return True
            if ent.type == "email" and (ent.metadata or {}).get("image_attributed"):
                return True
    return False


def _with_source(entity: Entity) -> Entity:
    if entity.sources:
        return entity
    return entity.model_copy(update={"sources": ["discovery_hop"]})


def _merge_entities(accumulated: FeatureResult, hops: list[FeatureResult]) -> FusionOutput:
    base_fusion = accumulated.fusion or FusionOutput()
    base_entities = [_with_source(e) for e in (base_fusion.deduplicated_entities or [])]
    hop_entities: list[Entity] = []
    hop_score = 0.0
    for hop in hops:
        hop_score = max(hop_score, hop.fusion.fusion_score if hop.fusion else 0.0)
        hop_entities.extend(_with_source(e) for e in (hop.fusion.deduplicated_entities if hop.fusion else []))
    merged_entities = deduplicate_entities(base_entities + hop_entities)
    return base_fusion.model_copy(
        update={
            "deduplicated_entities": merged_entities,
            "entities": merged_entities,
            "fusion_score": max(base_fusion.fusion_score, hop_score),
        }
    )


async def merge_hop_into_result(
    accumulated: FeatureResult,
    hop: FeatureResult,
    *,
    seed_query: str,
    enrich_profiles: bool = False,
) -> FeatureResult:
    """Union entities, re-extract evidence, and re-run correlation + graph."""
    return await merge_hops_batch(
        accumulated,
        [hop],
        seed_query=seed_query,
        enrich_profiles=enrich_profiles,
    )


async def merge_hops_batch(
    accumulated: FeatureResult,
    hops: list[FeatureResult],
    *,
    seed_query: str,
    enrich_profiles: bool = False,
    light: bool = False,
) -> FeatureResult:
    """Merge one or more hop results — correlation/graph run once per batch unless light."""
    if not hops:
        return accumulated

    merged_fusion = _merge_entities(accumulated, hops)

    merged_tools = list(accumulated.tool_results)
    merged_confirmed = list(accumulated.confirmed_findings)
    merged_public = list(accumulated.public_profile_data)
    merged_leads = list(accumulated.investigation_leads)
    tools_succeeded = accumulated.tools_succeeded
    tools_failed = accumulated.tools_failed
    total_ms = accumulated.total_execution_time_ms

    for hop in hops:
        merged_tools.extend(hop.tool_results)
        merged_confirmed.extend(hop.confirmed_findings)
        merged_public.extend(hop.public_profile_data)
        merged_leads.extend(hop.investigation_leads)
        tools_succeeded += hop.tools_succeeded
        tools_failed += hop.tools_failed
        total_ms += hop.total_execution_time_ms

    if light:
        return accumulated.model_copy(
            update={
                "fusion": merged_fusion,
                "tool_results": merged_tools,
                "confirmed_findings": merged_confirmed,
                "public_profile_data": merged_public,
                "investigation_leads": merged_leads,
                "tools_succeeded": tools_succeeded,
                "tools_failed": tools_failed,
                "total_execution_time_ms": total_ms,
            }
        )

    from services.multi_input import attribution_seed_query, parse_investigation_input
    from services.multi_investigation import reapply_parsed_identity

    parsed = parse_investigation_input(seed_query)
    attr_seed = attribution_seed_query(parsed)

    updated_fusion, evidence_extraction = await evidence_engine.extract(
        merged_fusion,
        seed_query=attr_seed,
        seed_email=parsed.email,
        enrich_public_profiles=enrich_profiles and _should_enrich_profiles(seed_query, merged_fusion),
        tool_results=merged_tools or None,
    )
    merged_fusion = updated_fusion
    from services.intelligence.person import build_identity_profile

    identity_profile = build_identity_profile(
        seed_query=seed_query,
        fusion=merged_fusion,
        evidence_extraction=evidence_extraction,
        enrichment_pass=2,
    )
    identity_profile = reapply_parsed_identity(identity_profile, seed_query)

    correlation = await correlation_engine.correlate(merged_fusion, seed_query=attr_seed)
    graph = graph_engine.analyze(
        merged_fusion,
        correlation,
        seed_query=attr_seed,
        identity_profile=identity_profile,
        evidence_extraction=evidence_extraction,
    )

    return accumulated.model_copy(
        update={
            "fusion": merged_fusion,
            "correlation": correlation,
            "graph": graph,
            "evidence_extraction": evidence_extraction,
            "identity_profile": identity_profile,
            "tool_results": merged_tools,
            "confirmed_findings": merged_confirmed,
            "public_profile_data": merged_public,
            "investigation_leads": merged_leads,
            "tools_succeeded": tools_succeeded,
            "tools_failed": tools_failed,
            "total_execution_time_ms": total_ms,
        }
    )
