"""Auto Pivot Engine — generic lead queue orchestrator."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from orchestrator.parallel_config import EXPANSION_CONCURRENCY, FEATURE_EXPANSION_LIMITS
from orchestrator.engine import ToolOrchestratorEngine
from schemas.common import FeatureResult
from schemas.discovery import DiscoveryConfig, DiscoveryHop, DiscoveryOutput
from schemas.pivot import InvestigationTree, PivotResult
from services.correlation.engine import correlation_engine
from services.discovery.merge import merge_hops_batch
from services.discovery.timeline import timeline_event
from services.graph_intelligence.engine import graph_engine
from services.pivot.processors import process_result
from services.pivot.queue import LeadQueue, visit_key
from services.pivot.tree import InvestigationTreeBuilder

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


class AutoPivotEngine:
    """Automatically process generated leads from any evidence module."""

    def __init__(self):
        self._orchestrator = ToolOrchestratorEngine()

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
    ) -> tuple[FeatureResult, DiscoveryOutput, InvestigationTree]:
        from schemas.discovery import DiscoveryConfig as DC

        cfg = config or DC()
        start = time.monotonic()

        async def emit(event: dict[str, Any]) -> None:
            if on_progress:
                await on_progress(event)

        tree_builder = InvestigationTreeBuilder(seed_query)
        queue = LeadQueue()
        queue.mark_visited(seed_query_type, seed_query)

        timeline = [
            timeline_event("seed", f"Seed investigation completed for '{seed_query}'", detail=f"Type: {seed_query_type}", query=seed_query, depth=0)
        ]
        hops: list[DiscoveryHop] = []
        total_leads_discovered = 0
        total_hops = 0
        max_depth_reached = 0
        stop_reason = "no_new_leads"

        await emit({"phase": "discovery", "status": "running", "message": "Auto-pivot: extracting leads from evidence"})

        seed_pivot = process_result(seed_result, source_query=seed_query, depth=1, max_leads=cfg.max_leads_per_hop)
        for ev in seed_pivot.evidence:
            tree_builder.add_evidence(ev)
        for lead in seed_pivot.generated_leads:
            if total_leads_discovered >= cfg.max_total_leads:
                break
            if queue.enqueue(lead):
                total_leads_discovered += 1
                parent_ev = next(
                    (e for e in seed_pivot.evidence if e.value.lower() in lead.query.lower() or lead.query.lower() in e.value.lower()),
                    None,
                )
                parent_id = tree_builder.add_evidence(parent_ev) if parent_ev else tree_builder.root.node_id
                tree_builder.add_lead(lead, parent_evidence_id=parent_id)
                timeline.append(timeline_event("lead_discovered", f"Lead discovered: {lead.query}", detail=lead.reason, depth=lead.depth, query=lead.query))

        rev = getattr(seed_result, "reverse_image_discovery", None)
        if rev and isinstance(rev, dict):
            from schemas.discovery import DiscoveryLead

            for raw in rev.get("generated_leads") or []:
                if total_leads_discovered >= cfg.max_total_leads:
                    break
                try:
                    lead = DiscoveryLead.model_validate(raw)
                except Exception:
                    continue
                if queue.enqueue(lead):
                    total_leads_discovered += 1
                    tree_builder.add_lead(lead, parent_evidence_id=tree_builder.root.node_id)
                    timeline.append(timeline_event(
                        "lead_discovered",
                        f"Reverse image lead: {lead.query}",
                        detail=lead.reason,
                        depth=lead.depth,
                        query=lead.query,
                    ))

        accumulated = seed_result

        if not queue:
            discovery = self._build_discovery_output(
                seed_query, seed_query_type, cfg, hops, queue, timeline,
                total_hops, total_leads_discovered, max_depth_reached, stop_reason,
                (time.monotonic() - start) * 1000,
            )
            investigation_tree = tree_builder.build()
            await emit({"phase": "discovery", "status": "done", "stop_reason": stop_reason})
            return (
                accumulated.model_copy(update={"discovery": discovery, "execution_mode": "recursive"}),
                discovery,
                investigation_tree,
            )

        while queue and total_hops < cfg.max_hops:
            if deadline_monotonic and time.monotonic() >= deadline_monotonic:
                stop_reason = "time_budget_exceeded"
                break
            if total_leads_discovered >= cfg.max_total_leads:
                stop_reason = "max_total_leads_reached"
                break

            batch = self._collect_expansion_batch(
                queue,
                cfg,
                remaining_hops=cfg.max_hops - total_hops,
            )

            if not batch:
                break

            async def _execute_hop(lead) -> tuple:
                hop_id = str(uuid4())
                hop_start = time.monotonic()
                timeline.append(timeline_event(
                    "hop_started",
                    f"Auto-pivot: {lead.query}",
                    detail=lead.reason or lead.feature,
                    depth=lead.depth,
                    query=lead.query,
                ))
                await emit({
                    "phase": "hop_started",
                    "hop_id": hop_id,
                    "query": lead.query,
                    "lead_type": lead.lead_type,
                    "depth": lead.depth,
                    "feature": lead.feature,
                })
                hop_result, hop_error = await self._run_hop(
                    lead,
                    self._hop_timeout(lead.feature, timeout_per_tool),
                    on_progress=on_progress,
                )
                hop_ms = (time.monotonic() - hop_start) * 1000
                return lead, hop_id, hop_result, hop_error, hop_ms

            hop_tasks = [asyncio.create_task(_execute_hop(lead)) for lead in batch]
            hop_outcomes: list[tuple] = []
            merges_pending: list[FeatureResult] = []
            for task in asyncio.as_completed(hop_tasks):
                lead, hop_id, hop_result, hop_error, hop_ms = await task
                hop_outcomes.append((lead, hop_id, hop_result, hop_error, hop_ms))

            for lead, hop_id, hop_result, hop_error, hop_ms in hop_outcomes:
                if hop_result is None:
                    hop = DiscoveryHop(
                        hop_id=hop_id, depth=lead.depth, query=lead.query, feature=lead.feature,
                        lead_type=lead.lead_type, parent_lead_id=lead.lead_id, status="failed",
                        error=hop_error, reason=lead.reason, execution_time_ms=hop_ms,
                    )
                    hops.append(hop)
                    tree_builder.add_hop(hop, parent_lead_id=lead.lead_id)
                    timeline.append(timeline_event("hop_failed", f"Hop failed: {lead.query}", detail=hop_error, depth=lead.depth, query=lead.query))
                    await emit({"phase": "hop_failed", "hop_id": hop_id, "query": lead.query, "error": hop_error})
                    continue

                child_pivot = process_result(hop_result, source_query=lead.query, depth=lead.depth + 1, max_leads=cfg.max_leads_per_hop)
                spawned = 0
                for ev in child_pivot.evidence:
                    tree_builder.add_evidence(ev)
                for child in child_pivot.generated_leads:
                    if total_leads_discovered >= cfg.max_total_leads:
                        stop_reason = "max_total_leads_reached"
                        break
                    if queue.enqueue(child):
                        total_leads_discovered += 1
                        spawned += 1
                        tree_builder.add_lead(child)
                        timeline.append(timeline_event("lead_discovered", f"Lead discovered: {child.query}", detail=child.reason, depth=child.depth, query=child.query))
                        await emit({
                            "phase": "finding_discovered",
                            "finding_type": "expansion_lead",
                            "value": child.query,
                            "lead_type": child.lead_type,
                            "priority": child.priority,
                        })

                hop = DiscoveryHop(
                    hop_id=hop_id, depth=lead.depth, query=lead.query, feature=lead.feature, lead_type=lead.lead_type,
                    parent_lead_id=lead.lead_id, status="completed", entities_found=len(child_pivot.evidence),
                    leads_spawned=spawned, execution_time_ms=hop_ms, reason=lead.reason,
                )
                hops.append(hop)
                tree_builder.add_hop(hop, parent_lead_id=lead.lead_id, evidence_items=child_pivot.evidence)
                total_hops += 1
                max_depth_reached = max(max_depth_reached, lead.depth)

                timeline.append(timeline_event("hop_completed", f"Hop completed: {lead.query}", detail=f"{len(child_pivot.evidence)} evidence, {spawned} lead(s)", depth=lead.depth, query=lead.query))
                await emit({"phase": "hop_completed", "hop_id": hop_id, "query": lead.query, "entities_found": len(child_pivot.evidence), "leads_spawned": spawned})
                merges_pending.append(hop_result)

            if merges_pending:
                accumulated = await merge_hops_batch(
                    accumulated, merges_pending, seed_query=seed_query, light=True,
                )
                timeline.append(timeline_event("merge", f"Merged {len(merges_pending)} hop(s)"))
                timeline.append(timeline_event("correlation", "Re-correlated entity set"))
                timeline.append(timeline_event("graph", "Rebuilt investigation graph"))
                await emit({
                    "phase": "profile_partial",
                    "status": "running",
                    "hops_done": total_hops,
                    "entities": len(accumulated.fusion.deduplicated_entities) if accumulated.fusion else 0,
                })

        if total_hops >= cfg.max_hops and queue:
            stop_reason = "max_hops_reached"
        elif not queue:
            stop_reason = "no_new_leads"

        timeline.append(timeline_event("expansion_stopped", f"Auto-pivot stopped: {stop_reason.replace('_', ' ')}", detail=f"{total_hops} hop(s), {total_leads_discovered} lead(s)"))

        discovery = self._build_discovery_output(
            seed_query, seed_query_type, cfg, hops, queue, timeline,
            total_hops, total_leads_discovered, max_depth_reached, stop_reason,
            (time.monotonic() - start) * 1000,
        )
        investigation_tree = tree_builder.build()

        await emit({"phase": "discovery", "status": "done", "stop_reason": stop_reason, "total_hops": total_hops})

        return (
            accumulated.model_copy(update={"discovery": discovery, "execution_mode": "recursive", "total_execution_time_ms": accumulated.total_execution_time_ms + discovery.total_execution_time_ms}),
            discovery,
            investigation_tree,
        )

    def _collect_expansion_batch(self, queue: LeadQueue, cfg: DiscoveryConfig, *, remaining_hops: int) -> list:
        """Build a diverse parallel batch — spread hops across platform/feature types."""
        from collections import defaultdict

        target = min(EXPANSION_CONCURRENCY, remaining_hops)
        if target <= 0:
            return []

        staging: list = []
        while len(staging) < target * 4 and queue:
            lead = queue.pop()
            if not lead or queue.is_visited(lead):
                continue
            if lead.depth > cfg.max_depth:
                queue.mark_visited(lead.lead_type, lead.query)
                continue
            staging.append(lead)

        if not staging:
            return []

        by_feature: dict[str, list] = defaultdict(list)
        for lead in staging:
            by_feature[lead.feature].append(lead)

        batch: list = []
        feature_counts: dict[str, int] = defaultdict(int)
        # Prioritize domain hops so multiple domains search in parallel first.
        feature_order = sorted(
            by_feature.keys(),
            key=lambda f: (
                0 if f == "domain_intel" else 1 if f == "username_search" else 2,
                f,
            ),
        )
        while len(batch) < target:
            progressed = False
            for feature in feature_order:
                if len(batch) >= target:
                    break
                limit = FEATURE_EXPANSION_LIMITS.get(feature, 2)
                if feature_counts[feature] >= limit or not by_feature[feature]:
                    continue
                lead = by_feature[feature].pop(0)
                queue.mark_visited(lead.lead_type, lead.query)
                batch.append(lead)
                feature_counts[feature] += 1
                progressed = True
            if not progressed:
                break

        for leftovers in by_feature.values():
            for lead in leftovers:
                queue.enqueue(lead)

        return batch

    def _hop_timeout(self, feature: str, timeout_per_tool: float) -> float:
        from orchestrator.config import HOP_TIMEOUT_CAP
        return min(timeout_per_tool, HOP_TIMEOUT_CAP)

    async def _run_hop(
        self,
        lead,
        timeout: float,
        on_progress: ProgressCallback | None = None,
    ) -> tuple[FeatureResult | None, str | None]:
        from orchestrator.parallel_config import HOP_DOMAIN_TOOLS, HOP_IMAGE_WALL_SECONDS, HOP_USERNAME_TOOLS

        try:
            if lead.feature == "image_intel":
                from services.investigation_runner import investigation_runner

                async def _noop(_event: dict) -> None:
                    pass

                emit = on_progress or _noop
                result = await asyncio.wait_for(
                    investigation_runner._run_with_progress(
                        "image_intel",
                        lead.query,
                        min(timeout, HOP_IMAGE_WALL_SECONDS),
                        emit,
                        image_profile="hop",
                    ),
                    timeout=HOP_IMAGE_WALL_SECONDS,
                )
                return result, None

            runners = {
                "email_intel": lambda q, t: self._orchestrator.execute_email_intel(q, t),
                "username_search": lambda q, t: self._orchestrator.execute_username_search(
                    q, t, tools=HOP_USERNAME_TOOLS, hop=True,
                ),
                "domain_intel": lambda q, t: self._orchestrator.execute_domain_intel(
                    q, t, tools=HOP_DOMAIN_TOOLS, hop=True,
                ),
                "infra_intel": lambda q, t: self._orchestrator.execute_infra_intel(q, t),
            }
            runner = runners.get(lead.feature)
            if not runner:
                return None, f"Unsupported feature: {lead.feature}"
            return await asyncio.wait_for(runner(lead.query, timeout), timeout=timeout + 2), None
        except asyncio.TimeoutError:
            return None, f"Hop timed out after {timeout:.0f}s"
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}"

    def _build_discovery_output(self, seed_query, seed_query_type, config, hops, queue, timeline, total_hops, total_leads, max_depth, stop_reason, elapsed_ms):
        return DiscoveryOutput(
            enabled=True, seed_query=seed_query, seed_query_type=seed_query_type, config=config,
            hops=hops, pending_leads=queue.pending(), visited=sorted(queue.visited),
            timeline=timeline, total_hops=total_hops, total_leads_discovered=total_leads,
            total_leads_expanded=total_hops, max_depth_reached=max_depth, stop_reason=stop_reason,
            total_execution_time_ms=elapsed_ms,
        )


auto_pivot_engine = AutoPivotEngine()
