import asyncio
import time
from typing import Any

from adapters.base import BaseAdapter
from orchestrator.config import ADAPTER_MAP, DEFAULT_TIMEOUTS, FEATURE_TOOLS
from schemas.common import FeatureResult, ToolResult
from services.correlation.engine import correlation_engine
from services.email_intel import build_email_investigation, fetch_gravatar_profile
from services.fusion import build_fusion_output, fuse_results
from services.graph_intelligence.engine import graph_engine
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
        self, tool_name: str, query: str, timeout: float
    ) -> ToolResult:
        """Run a single tool with failure isolation."""
        try:
            adapter = self._get_adapter(tool_name)
            return await adapter.run(query, timeout=timeout)
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
    ) -> FeatureResult:
        """
        Execute all tools for a feature in parallel.
        One tool failure does not break the pipeline.
        """
        start = time.monotonic()
        scan_query = query_override or query
        tool_names = tools_override or FEATURE_TOOLS.get(feature, [])
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

        async with asyncio.TaskGroup() as tg:
            tasks = {
                tool: tg.create_task(
                    self._run_tool_safe(tool, scan_query, default_timeout),
                    name=f"{feature}:{tool}",
                )
                for tool in tool_names
            }

        tool_results: list[ToolResult] = []
        for tool_name in tool_names:
            try:
                tool_results.append(tasks[tool_name].result())
            except Exception as e:
                tool_results.append(
                    ToolResult(
                        tool=tool_name,
                        success=False,
                        error=f"TaskGroup failure: {type(e).__name__}: {e}",
                    )
                )

        normalized = normalize_tool_results(tool_results)
        merged = fuse_results(normalized)
        confidence_inputs = build_confidence_inputs(tool_results)
        fusion = build_fusion_output(tool_results, feature, query)
        correlation = await correlation_engine.correlate(fusion, seed_query=query)
        graph = graph_engine.analyze(fusion, correlation, seed_query=query)
        persist_investigation(feature, query, fusion, correlation, graph.model_dump())

        succeeded = sum(1 for r in tool_results if r.success)
        failed = len(tool_results) - succeeded

        return FeatureResult(
            feature=feature,
            query=query,
            query_normalized=query_normalized,
            warnings=warnings or [],
            tool_results=tool_results,
            merged_results=merged,
            fusion=fusion,
            correlation=correlation,
            graph=graph,
            confidence_raw_inputs=confidence_inputs,
            total_execution_time_ms=(time.monotonic() - start) * 1000,
            tools_succeeded=succeeded,
            tools_failed=failed,
        )

    async def execute_username_search(
        self, username: str, timeout: float | None = None, tools: list[str] | None = None
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
        )

    async def execute_email_intel(
        self, email: str, timeout: float | None = None, tools: list[str] | None = None
    ) -> FeatureResult:
        result = await self.execute_feature("email_intel", email, timeout, tools)

        gravatar = await fetch_gravatar_profile(email)
        public_profiles = [gravatar] if gravatar else []

        confirmed, public_data, leads, summary = build_email_investigation(
            result.tool_results, email, public_profiles
        )

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
        result.correlation = await correlation_engine.correlate(result.fusion, seed_query=email)
        result.graph = graph_engine.analyze(result.fusion, result.correlation, seed_query=email)
        persist_investigation("email_intel", email, result.fusion, result.correlation, result.graph.model_dump())
        return result

    async def execute_domain_intel(
        self, domain: str, timeout: float | None = None, tools: list[str] | None = None
    ) -> FeatureResult:
        return await self.execute_feature("domain_intel", domain, timeout, tools)

    async def execute_infra_intel(
        self, query: str, timeout: float | None = None, tools: list[str] | None = None
    ) -> FeatureResult:
        return await self.execute_feature("infra_intel", query, timeout, tools)

    async def execute_image_intel(
        self, source: str, timeout: float | None = None
    ) -> FeatureResult:
        return await self.execute_feature("image_intel", source, timeout)


orchestrator = ToolOrchestratorEngine()
