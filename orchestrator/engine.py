import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from adapters.base import BaseAdapter
from orchestrator.config import ADAPTER_MAP, DEFAULT_TIMEOUTS, effective_tool_timeout, get_feature_tools
from orchestrator.parallel_config import (
    batch_wall_seconds,
    effective_wall_seconds,
    feature_tool_concurrency,
    feature_wall_seconds,
    max_image_tool_concurrency,
)
from orchestrator.parallel_runner import execute_tools_parallel
from schemas.common import FeatureResult, ToolResult
from services.correlation.engine import correlation_engine
from services.email_intel import build_email_investigation, fetch_gravatar_profile
from services.email_profile_resolver import enrich_confirmed_findings, enrich_public_profiles
from services.fusion import build_fusion_output, fuse_results
from services.graph_intelligence.engine import graph_engine
from services.json_utils import to_json_safe
from services.normalization import build_confidence_inputs, normalize_tool_results
from services.persistence.postgres import persist_investigation
from services.username import normalize_username


class ToolOrchestratorEngine:
    """
    Multi-tool orchestration engine.
    Runs tools in parallel per feature with timeout, retry, and failure isolation.
    """

    def __init__(self):
        self._adapters: dict[str, BaseAdapter] = {}

    def _get_adapter(self, tool_name: str) -> BaseAdapter:
        if tool_name not in self._adapters:
            adapter_cls = ADAPTER_MAP.get(tool_name)
            if not adapter_cls:
                raise ValueError(f"Unknown tool: {tool_name}")
            self._adapters[tool_name] = adapter_cls()
        return self._adapters[tool_name]

    async def _run_tool_safe(
        self, tool_name: str, query: str, timeout: float, *, hop: bool = False
    ) -> ToolResult:
        """Run a single tool with failure isolation."""
        try:
            from services.resource_guard import tool_subprocess_slot

            adapter = self._get_adapter(tool_name)
            async with tool_subprocess_slot():
                return await adapter.run(
                    query, timeout=effective_tool_timeout(tool_name, timeout, hop=hop)
                )
        except Exception as e:
            return ToolResult(
                tool=tool_name,
                success=False,
                error=f"Orchestrator isolation catch: {type(e).__name__}: {e}",
            )

    async def execute_feature(
        self,
        feature: str,
        query: str,
        timeout_per_tool: float | None = None,
        tools_override: list[str] | None = None,
        query_normalized: str | None = None,
        warnings: list[str] | None = None,
        query_override: str | None = None,
        *,
        hop: bool = False,
        on_tool_started: Callable[[str], Awaitable[None]] | None = None,
        on_tool_done: Callable[[str, ToolResult], Awaitable[None]] | None = None,
    ) -> FeatureResult:
        """
        Execute all tools for a feature in parallel.
        One tool failure does not break the pipeline.
        """
        start = time.monotonic()
        scan_query = query_override or query
        tool_names = tools_override or get_feature_tools(
            feature,
            target=scan_query,
            profile="deep" if feature in ("username_search", "email_intel") else "fast",
        )
        if feature == "username_search":
            tool_names = [t for t in tool_names if t not in ("gitfive", "nexfil")]
        if not tool_names:
            return FeatureResult(
                feature=feature,
                query=query,
                tool_results=[
                    ToolResult(
                        tool="orchestrator",
                        success=False,
                        error=f"No tools configured for feature: {feature}",
                    )
                ],
            )

        default_timeout = timeout_per_tool or DEFAULT_TIMEOUTS.get(feature, 120.0)
        per_tool_wall = effective_wall_seconds(feature)
        requested = max_image_tool_concurrency() if feature == "image_intel" else feature_tool_concurrency(feature)
        if feature == "email_intel":
            requested = max(requested or 4, len(tool_names))
        from services.resource_guard import effective_tool_concurrency

        concurrency_limit = effective_tool_concurrency(feature, requested)
        batch_wall = batch_wall_seconds(feature, len(tool_names), concurrency_limit or 1)
        batch_wall = max(batch_wall, per_tool_wall)

        def _tool_wall_sec(tool: str) -> float:
            floor = effective_tool_timeout(tool, default_timeout, hop=hop)
            base = max(per_tool_wall, floor)
            if feature == "email_intel" and tool == "google_dorking":
                dork_wall = float(os.getenv("EMAIL_GOOGLE_DORK_WALL_SEC", "300"))
                return max(base, dork_wall)
            return base

        batch_wall = max(batch_wall, max(_tool_wall_sec(t) for t in tool_names))

        def _partial_result_for(tool: str) -> ToolResult | None:
            adapter = self._adapters.get(tool)
            if adapter is None:
                return None
            getter = getattr(adapter, "_partial_tool_result", None)
            return getter() if callable(getter) else None

        async def _run_one(tool: str) -> ToolResult:
            # Samurai needs the full seed (name + username) for Facebook name-directory lookup.
            run_query = query if tool == "samurai" else scan_query
            if feature == "email_intel" and tool in ("maigret", "blackbird", "sherlock"):
                from services.email_intel import email_local_part

                run_query = email_local_part(query)
            return await self._run_tool_safe(tool, run_query, default_timeout, hop=hop)

        tool_results, parallel_meta = await execute_tools_parallel(
            tool_names,
            _run_one,
            wall_sec=per_tool_wall,
            max_batch_sec=batch_wall,
            max_concurrency=concurrency_limit,
            on_tool_started=on_tool_started,
            on_tool_done=on_tool_done,
            tool_wall_sec=_tool_wall_sec,
            partial_result_for=_partial_result_for,
        )

        normalized = normalize_tool_results(tool_results)
        merged = fuse_results(normalized)
        confidence_inputs = build_confidence_inputs(tool_results)
        fusion = build_fusion_output(tool_results, feature, query)
        if feature == "username_search" and fusion.deduplicated_entities:
            from services.evidence.profile_verifier import refine_username_fusion

            fusion = await refine_username_fusion(fusion, seed_query=query)
        reverse_image_discovery = None
        image_correlation = None
        if feature == "image_intel":
            from schemas.image_intelligence import ImageIntelligenceOutput
            from services.image_correlation.engine import image_correlation_engine
            from services.image_intelligence.engine import image_intelligence_engine
            from services.reverse_image.engine import reverse_image_engine

            intel = await image_intelligence_engine.analyze(scan_query, tool_results=tool_results)
            fusion = image_intelligence_engine.merge_into_fusion(fusion, intel)
            reverse_image_discovery = await reverse_image_engine.discover(scan_query, seed_query=query)
            rev_entities = reverse_image_engine.matches_to_entities(reverse_image_discovery)
            if rev_entities:
                fusion = image_intelligence_engine.merge_into_fusion(
                    fusion,
                    ImageIntelligenceOutput(image_source=scan_query, entities=rev_entities),
                )
            image_correlation = image_correlation_engine.correlate(
                seed_image=scan_query,
                fusion=fusion,
                image_intel=intel,
                reverse_discovery=reverse_image_discovery,
            )
        evidence_extraction = None
        defer_postprocess = feature == "email_intel"
        if fusion.deduplicated_entities and not defer_postprocess:
            from services.evidence.engine import evidence_engine

            fusion, evidence_extraction = await evidence_engine.extract(
                fusion,
                seed_query=query,
                enrich_public_profiles=feature == "username_search",
                tool_results=tool_results,
            )
        correlation = None
        graph = None
        if not defer_postprocess:
            correlation = await correlation_engine.correlate(fusion, seed_query=query)
            graph = graph_engine.analyze(
                fusion,
                correlation,
                seed_query=query,
                evidence_extraction=evidence_extraction,
            )
            persist_investigation(feature, query, fusion, correlation, to_json_safe(graph.model_dump()))

        succeeded = sum(1 for r in tool_results if r.success)
        failed = len(tool_results) - succeeded

        out_warnings = list(warnings or [])
        if parallel_meta.get("cancelled"):
            out_warnings.append(
                f"Wall clock ({parallel_meta.get('wall_sec', wall_sec):.0f}s): "
                f"cancelled {', '.join(parallel_meta['cancelled'])}"
            )

        return FeatureResult(
            feature=feature,
            query=query,
            query_normalized=query_normalized,
            warnings=out_warnings,
            tool_results=tool_results,
            merged_results=to_json_safe(merged),
            fusion=fusion,
            correlation=correlation,
            graph=graph,
            evidence_extraction=evidence_extraction,
            confidence_raw_inputs=confidence_inputs,
            reverse_image_discovery=to_json_safe(reverse_image_discovery.model_dump()) if reverse_image_discovery else None,
            image_correlation=to_json_safe(image_correlation.model_dump()) if image_correlation else None,
            total_execution_time_ms=(time.monotonic() - start) * 1000,
            tools_succeeded=succeeded,
            tools_failed=failed,
        )

    async def execute_username_search(
        self, username: str, timeout: float | None = None, tools: list[str] | None = None, *, hop: bool = False
    ) -> FeatureResult:
        normalized, warnings = normalize_username(username)
        scan_query = normalized or username
        return await self.execute_feature(
            "username_search",
            username,
            timeout,
            tools,
            query_normalized=scan_query if scan_query != username else None,
            warnings=warnings,
            query_override=scan_query,
            hop=hop,
        )

    async def execute_email_intel(
        self,
        email: str,
        timeout: float | None = None,
        tools: list[str] | None = None,
        *,
        on_tool_started: Callable[[str], Awaitable[None]] | None = None,
        on_tool_done: Callable[[str, ToolResult], Awaitable[None]] | None = None,
        on_progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> FeatureResult:
        async def _emit(event: dict[str, Any]) -> None:
            if on_progress:
                await on_progress(event)

        async def _emit_snapshot(result: FeatureResult) -> None:
            await _emit({
                "phase": "collection_partial",
                "status": "running",
                "fusion": to_json_safe(result.fusion.model_dump()) if result.fusion else None,
                "identity_profile": to_json_safe(result.identity_profile.model_dump()) if result.identity_profile else None,
                "evidence_extraction": to_json_safe(result.evidence_extraction.model_dump()) if result.evidence_extraction else None,
                "correlation": to_json_safe(result.correlation.model_dump()) if result.correlation else None,
                "graph": to_json_safe(result.graph.model_dump()) if result.graph else None,
                "tool_results": to_json_safe([tr.model_dump() for tr in result.tool_results]),
                "fusion_score": result.fusion.fusion_score if result.fusion else 0,
            })

        result = await self.execute_feature(
            "email_intel",
            email,
            timeout,
            tools,
            on_tool_started=on_tool_started,
            on_tool_done=on_tool_done,
        )

        await _emit({
            "phase": "fusion",
            "status": "running",
            "message": "Merging email registrations and public profiles…",
        })

        gravatar_tr = next((tr for tr in result.tool_results if tr.tool == "gravatar" and tr.success), None)
        if gravatar_tr and gravatar_tr.data:
            public_profiles = list(gravatar_tr.data) if isinstance(gravatar_tr.data, list) else [gravatar_tr.data]
        else:
            gravatar = await fetch_gravatar_profile(email)
            public_profiles = [gravatar] if gravatar else []

        confirmed, public_data, leads, summary = build_email_investigation(
            result.tool_results, email, public_profiles
        )
        public_data = enrich_public_profiles(public_data)
        confirmed = enrich_confirmed_findings(confirmed, email=email, public_profiles=public_data)

        result.confirmed_findings = confirmed
        result.public_profile_data = public_data
        result.investigation_leads = leads
        result.scan_summary = summary
        result.merged_results = confirmed
        result.fusion = build_fusion_output(
            result.tool_results,
            "email_intel",
            email,
            confirmed_findings=confirmed,
            public_profile_data=public_data,
            investigation_leads=leads,
        )
        await _emit({
            "phase": "collection_partial",
            "status": "running",
            "fusion": to_json_safe(result.fusion.model_dump()) if result.fusion else None,
            "tool_results": to_json_safe([tr.model_dump() for tr in result.tool_results]),
            "confirmed_findings": to_json_safe(result.confirmed_findings),
            "public_profile_data": to_json_safe(result.public_profile_data),
            "investigation_leads": to_json_safe(result.investigation_leads),
            "scan_summary": to_json_safe(result.scan_summary),
            "fusion_score": result.fusion.fusion_score if result.fusion else 0,
        })
        await _emit_snapshot(result)
        await _emit({
            "phase": "fusion",
            "status": "done",
            "fusion_score": result.fusion.fusion_score if result.fusion else 0,
        })

        from services.evidence.engine import evidence_engine
        from services.intelligence.person import build_identity_profile

        await _emit({
            "phase": "evidence_extraction",
            "status": "running",
            "message": "Extracting platform profiles and public data…",
        })
        result.fusion, result.evidence_extraction = await evidence_engine.extract(
            result.fusion,
            seed_query=email,
            enrich_public_profiles=True,
            tool_results=result.tool_results,
        )
        identity_profile = build_identity_profile(
            seed_query=email,
            fusion=result.fusion,
            evidence_extraction=result.evidence_extraction,
            enrichment_pass=1,
        )
        result.identity_profile = identity_profile
        await _emit_snapshot(result)
        await _emit({
            "phase": "evidence_extraction",
            "status": "done",
            "fields_extracted": result.evidence_extraction.fields_extracted if result.evidence_extraction else 0,
            "platforms_analyzed": result.evidence_extraction.platforms_analyzed if result.evidence_extraction else 0,
        })

        await _emit({"phase": "correlation", "status": "running", "message": "Clustering linked accounts…"})
        result.correlation = await correlation_engine.correlate(result.fusion, seed_query=email)
        await _emit_snapshot(result)
        await _emit({
            "phase": "correlation",
            "status": "done",
            "clusters": result.correlation.total_clusters if result.correlation else 0,
        })

        await _emit({"phase": "graph", "status": "running", "message": "Building investigation graph…"})
        result.graph = graph_engine.analyze(
            result.fusion,
            result.correlation,
            seed_query=email,
            identity_profile=identity_profile,
            evidence_extraction=result.evidence_extraction,
        )
        await _emit_snapshot(result)
        await _emit({
            "phase": "graph",
            "status": "done",
            "nodes": result.graph.node_count if result.graph else 0,
        })

        persist_investigation("email_intel", email, result.fusion, result.correlation, result.graph.model_dump())
        return result

    async def execute_domain_intel(
        self, domain: str, timeout: float | None = None, tools: list[str] | None = None, *, hop: bool = False
    ) -> FeatureResult:
        return await self.execute_feature("domain_intel", domain, timeout, tools, hop=hop)

    async def execute_infra_intel(
        self, query: str, timeout: float | None = None, tools: list[str] | None = None
    ) -> FeatureResult:
        return await self.execute_feature("infra_intel", query, timeout, tools)

    async def execute_image_intel(
        self, source: str, timeout: float | None = None
    ) -> FeatureResult:
        return await self.execute_feature("image_intel", source, timeout)


orchestrator = ToolOrchestratorEngine()
