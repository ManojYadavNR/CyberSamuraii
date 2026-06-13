"""Run investigations with live progress callbacks for WebSocket streaming."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from orchestrator.engine import ToolOrchestratorEngine
from schemas.common import FeatureResult, ToolResult
from services.query_detector import detect_query_type

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

_investigations: dict[str, dict[str, Any]] = {}


def get_investigation(investigation_id: str) -> dict[str, Any] | None:
    return _investigations.get(investigation_id)


class InvestigationRunner:
    def __init__(self):
        self._orchestrator = ToolOrchestratorEngine()

    async def run(
        self,
        query: str,
        query_type: str | None = None,
        timeout_per_tool: float = 120.0,
        on_progress: ProgressCallback | None = None,
    ) -> tuple[str, FeatureResult]:
        investigation_id = str(uuid4())
        qtype = query_type or detect_query_type(query)
        _investigations[investigation_id] = {
            "id": investigation_id,
            "query": query,
            "query_type": qtype,
            "status": "running",
        }

        async def emit(event: dict[str, Any]) -> None:
            if on_progress:
                await on_progress({**event, "investigation_id": investigation_id})

        await emit({"phase": "start", "query": query, "query_type": qtype, "status": "running"})

        if qtype == "username":
            result = await self._run_with_progress(
                "username_search", query, timeout_per_tool, emit, use_username=True
            )
        elif qtype == "email":
            result = await self._run_email(query, timeout_per_tool, emit)
        elif qtype == "image":
            result = await self._run_with_progress("image_intel", query, timeout_per_tool, emit)
        elif qtype == "domain":
            result = await self._run_with_progress("domain_intel", query, timeout_per_tool, emit)
        elif qtype in ("phone", "infra"):
            result = await self._run_with_progress("infra_intel", query, timeout_per_tool, emit)
        else:
            result = await self._run_with_progress("username_search", query, timeout_per_tool, emit)

        _investigations[investigation_id].update({
            "status": "complete",
            "result": result.model_dump(),
        })
        await emit({"phase": "complete", "status": "complete", "result": result.model_dump()})
        return investigation_id, result

    async def _run_email(self, email: str, timeout: float, emit: ProgressCallback) -> FeatureResult:
        from orchestrator.config import FEATURE_TOOLS

        tools = FEATURE_TOOLS.get("email_intel", [])
        for tool in tools:
            await emit({"phase": "tool", "tool": tool, "status": "running"})
        result = await self._orchestrator.execute_email_intel(email, timeout)
        for tr in result.tool_results:
            await emit({
                "phase": "tool",
                "tool": tr.tool,
                "status": "done",
                "success": tr.success,
                "execution_time_ms": tr.execution_time_ms,
                "error": tr.error,
            })
        await emit({"phase": "fusion", "status": "done", "fusion_score": result.fusion.fusion_score if result.fusion else 0})
        await emit({"phase": "correlation", "status": "done"})
        await emit({"phase": "graph", "status": "done"})
        return result

    async def _run_with_progress(
        self,
        feature: str,
        query: str,
        timeout: float,
        emit: ProgressCallback,
        *,
        use_username: bool = False,
    ) -> FeatureResult:
        from orchestrator.config import DEFAULT_TIMEOUTS, FEATURE_TOOLS
        from services.correlation.engine import correlation_engine
        from services.fusion import build_fusion_output, fuse_results
        from services.graph_intelligence.engine import graph_engine
        from services.normalization import build_confidence_inputs, normalize_tool_results
        from services.persistence.postgres import persist_investigation
        from services.username import normalize_username

        start = time.monotonic()
        tool_names = FEATURE_TOOLS.get(feature, [])
        default_timeout = timeout or DEFAULT_TIMEOUTS.get(feature, 120.0)
        warnings: list[str] = []
        query_normalized = None
        scan_query = query

        if use_username:
            normalized, warnings = normalize_username(query)
            scan_query = normalized or query
            query_normalized = scan_query if scan_query != query else None

        tool_results: list[ToolResult] = []
        for tool in tool_names:
            await emit({"phase": "tool", "tool": tool, "status": "running"})
            tr = await self._orchestrator._run_tool_safe(tool, scan_query, default_timeout)
            tool_results.append(tr)
            await emit({
                "phase": "tool",
                "tool": tool,
                "status": "done",
                "success": tr.success,
                "execution_time_ms": tr.execution_time_ms,
                "error": tr.error,
            })

        await emit({"phase": "fusion", "status": "running"})
        normalized_results = normalize_tool_results(tool_results)
        merged = fuse_results(normalized_results)
        confidence_inputs = build_confidence_inputs(tool_results)
        fusion = build_fusion_output(tool_results, feature, query)
        await emit({"phase": "fusion", "status": "done", "fusion_score": fusion.fusion_score})

        await emit({"phase": "correlation", "status": "running"})
        correlation = await correlation_engine.correlate(fusion, seed_query=query)
        await emit({"phase": "correlation", "status": "done", "clusters": correlation.total_clusters})

        await emit({"phase": "graph", "status": "running"})
        graph = graph_engine.analyze(fusion, correlation, seed_query=query)
        await emit({"phase": "graph", "status": "done", "nodes": graph.node_count})
        persist_investigation(feature, query, fusion, correlation, graph.model_dump())

        succeeded = sum(1 for r in tool_results if r.success)
        return FeatureResult(
            feature=feature,
            query=query,
            query_normalized=query_normalized,
            warnings=warnings,
            tool_results=tool_results,
            merged_results=merged,
            fusion=fusion,
            correlation=correlation,
            graph=graph,
            confidence_raw_inputs=confidence_inputs,
            total_execution_time_ms=(time.monotonic() - start) * 1000,
            tools_succeeded=succeeded,
            tools_failed=len(tool_results) - succeeded,
        )


investigation_runner = InvestigationRunner()
