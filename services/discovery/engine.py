"""Recursive Discovery Engine — delegates to Auto Pivot Engine."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from schemas.common import FeatureResult
from schemas.discovery import DiscoveryConfig
from services.correlation.engine import correlation_engine
from services.evidence.engine import evidence_engine
from services.graph_intelligence.engine import graph_engine
from services.intelligence.person import build_identity_profile
from services.pivot.engine import auto_pivot_engine

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


class RecursiveDiscoveryEngine:
    """Expand investigations via generic auto-pivot lead queue."""

    async def expand(
        self,
        *,
        seed_query: str,
        seed_query_type: str,
        seed_result: FeatureResult,
        config: DiscoveryConfig | None = None,
        timeout_per_tool: float = 120.0,
        on_progress: ProgressCallback | None = None,
        deadline_monotonic: float | None = None,
    ) -> FeatureResult:
        cfg = config or DiscoveryConfig()
        if not cfg.enabled:
            return seed_result

        accumulated, discovery, investigation_tree = await auto_pivot_engine.expand(
            seed_query=seed_query,
            seed_query_type=seed_query_type,
            seed_result=seed_result,
            config=cfg,
            timeout_per_tool=timeout_per_tool,
            on_progress=on_progress,
            deadline_monotonic=deadline_monotonic,
        )

        discovery = discovery.model_copy(update={"investigation_tree": investigation_tree})

        if accumulated.fusion and accumulated.fusion.deduplicated_entities:
            if on_progress:
                await on_progress({"phase": "evidence_extraction", "status": "running", "message": "Building person-centric identity profile"})

            from services.multi_input import attribution_seed_query, parse_investigation_input
            from services.multi_investigation import reapply_parsed_identity

            parsed = parse_investigation_input(seed_query)
            attr_seed = attribution_seed_query(parsed)

            fusion, evidence_extraction = await evidence_engine.extract(
                accumulated.fusion,
                seed_query=attr_seed,
                seed_email=parsed.email,
                enrich_public_profiles=seed_query_type in ("username", "image"),
                tool_results=accumulated.tool_results or None,
            )
            identity_profile = build_identity_profile(
                seed_query=seed_query,
                fusion=fusion,
                evidence_extraction=evidence_extraction,
                investigation_tree=investigation_tree,
                enrichment_pass=2,
            )
            identity_profile = reapply_parsed_identity(identity_profile, seed_query)
            correlation = await correlation_engine.correlate(fusion, seed_query=attr_seed)
            graph = graph_engine.analyze(
                fusion,
                correlation,
                seed_query=attr_seed,
                identity_profile=identity_profile,
                evidence_extraction=evidence_extraction,
                investigation_tree=investigation_tree,
            )

            accumulated = accumulated.model_copy(update={
                "fusion": fusion,
                "evidence_extraction": evidence_extraction,
                "identity_profile": identity_profile,
                "correlation": correlation,
                "graph": graph,
                "discovery": discovery,
            })

            if on_progress:
                await on_progress({
                    "phase": "evidence_extraction",
                    "status": "done",
                    "fields_extracted": evidence_extraction.fields_extracted,
                    "platforms_analyzed": evidence_extraction.platforms_analyzed,
                    "identity_confidence": identity_profile.confidence_score,
                })
        else:
            accumulated = accumulated.model_copy(update={"discovery": discovery})

        from services.persistence.postgres import persist_discovery_chain

        persist_discovery_chain(
            discovery,
            accumulated.fusion.investigation_id if accumulated.fusion else None,
        )

        return accumulated
