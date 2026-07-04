"""Run investigations with live progress callbacks for WebSocket streaming."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from orchestrator.engine import ToolOrchestratorEngine
from schemas.common import FeatureResult, ToolResult
from schemas.discovery import DiscoveryConfig, discovery_config_for_query_type
from schemas.investigation_mode import (
    resolve_investigation_mode,
    tool_profile_for_mode,
    username_tools_override,
)
from services.discovery.engine import RecursiveDiscoveryEngine
from services.investigation_cache import load_investigation_record, save_investigation_record
from services.json_utils import to_json_safe
from services.multi_input import parse_investigation_input
from services.query_detector import detect_query_type
from services.resource_guard import (
    DUAL_BRANCH_PARALLEL,
    MULTI_INPUT_PARALLEL,
    InvestigationBusyError,
    dual_identity_scan,
    effective_tool_concurrency,
    full_scan_mode,
    get_investigation_mode,
    investigation_mode_scope,
    investigation_slot,
    is_dual_identity_scan,
    tool_subprocess_slot,
)

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

_investigations: dict[str, dict[str, Any]] = {}


def _dump_result(result) -> dict:
    """Pydantic mode='json' fails on numpy scalars nested in tool data — sanitize manually."""
    return to_json_safe(result.model_dump())


def _safe_tool_result(tr: ToolResult) -> ToolResult:
    return ToolResult(**to_json_safe(tr.model_dump()))


async def _emit_email_tool_findings(emit: ProgressCallback, tr: ToolResult) -> None:
    if not tr.success or not tr.data:
        return
    rows = tr.data if isinstance(tr.data, list) else [tr.data]
    emitted = 0
    for item in rows:
        if not isinstance(item, dict) or item.get("platform") == "_scan_summary":
            continue
        if tr.tool == "holehe" and item.get("status") == "registered":
            platform = str(item.get("platform") or "site")
            await emit({
                "phase": "finding_discovered",
                "finding_type": "account",
                "value": f"{platform}: email registered",
                "source": tr.tool,
                "platform": platform,
            })
            emitted += 1
        elif tr.tool == "google_dorking" and item.get("check_type") == "google_dork":
            url = item.get("url") or item.get("link")
            if url:
                await emit({
                    "phase": "finding_discovered",
                    "finding_type": "web",
                    "value": str(url),
                    "source": tr.tool,
                })
                emitted += 1
        elif tr.tool == "theharvester" and (item.get("email") or item.get("url") or item.get("hostname")):
            val = item.get("email") or item.get("url") or item.get("hostname")
            await emit({
                "phase": "finding_discovered",
                "finding_type": "harvest",
                "value": str(val),
                "source": tr.tool,
            })
            emitted += 1
        if emitted >= 12:
            break


async def _emit_email_collection_partial(
    emit: ProgressCallback,
    email: str,
    tool_results: list[ToolResult],
    *,
    tools_total: int,
) -> None:
    from services.email_intel import build_email_investigation
    from services.email_profile_resolver import enrich_confirmed_findings, enrich_public_profiles
    from services.fusion import build_fusion_output

    gravatar_tr = next((t for t in tool_results if t.tool == "gravatar" and t.success), None)
    public_profiles: list[Any] = []
    if gravatar_tr and gravatar_tr.data:
        public_profiles = list(gravatar_tr.data) if isinstance(gravatar_tr.data, list) else [gravatar_tr.data]

    confirmed, public_data, leads, _summary = build_email_investigation(tool_results, email, public_profiles)
    public_data = enrich_public_profiles(public_data)
    confirmed = enrich_confirmed_findings(confirmed, email=email, public_profiles=public_data)
    fusion = build_fusion_output(
        tool_results,
        "email_intel",
        email,
        confirmed_findings=confirmed,
        public_profile_data=public_data,
        investigation_leads=leads,
    )
    await emit({
        "phase": "collection_partial",
        "status": "running",
        "fusion": to_json_safe(fusion.model_dump()),
        "tool_results": to_json_safe([tr.model_dump() for tr in tool_results]),
        "fusion_score": fusion.fusion_score,
        "tools_done": len(tool_results),
        "tools_total": tools_total,
    })
    await emit({
        "phase": "fusion_partial",
        "latest_tool": tool_results[-1].tool if tool_results else None,
        "tools_done": len(tool_results),
        "tools_total": tools_total,
    })


def get_investigation(investigation_id: str) -> dict[str, Any] | None:
    cached = _investigations.get(investigation_id)
    if cached:
        return to_json_safe(cached)

    from_disk = load_investigation_record(investigation_id)
    if from_disk:
        from_disk = to_json_safe(from_disk)
        _investigations[investigation_id] = from_disk
        return from_disk

    from services.persistence.postgres import load_investigation_from_db

    loaded = load_investigation_from_db(investigation_id)
    if loaded:
        loaded = to_json_safe(loaded)
        _investigations[investigation_id] = loaded
        save_investigation_record(loaded)
    return loaded


def _cache_investigation(record: dict[str, Any]) -> None:
    inv_id = str(record.get("id") or "")
    if inv_id:
        safe = to_json_safe(record)
        _investigations[inv_id] = safe
        save_investigation_record(safe)


class InvestigationRunner:
    def __init__(self):
        self._orchestrator = ToolOrchestratorEngine()

    async def run(
        self,
        query: str,
        query_type: str | None = None,
        timeout_per_tool: float = 120.0,
        discovery_config: DiscoveryConfig | None = None,
        on_progress: ProgressCallback | None = None,
        *,
        image_profile: str = "fast",
        investigation_mode: str | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> tuple[str, FeatureResult]:
        from services.investigation_cancel import (
            InvestigationCancelledError,
            begin_investigation,
            end_investigation,
            ensure_not_cancelled,
        )

        investigation_id = str(uuid4())
        begin_investigation(investigation_id)
        if cancel_event is not None:
            from services.investigation_cancel import use_cancel_event

            use_cancel_event(investigation_id, cancel_event)

        parsed = parse_investigation_input(query)
        qtype = query_type or parsed.primary_type
        if parsed.is_multi:
            qtype = "multi"

        async def emit(event: dict[str, Any]) -> None:
            if on_progress:
                try:
                    await on_progress(to_json_safe({**event, "investigation_id": investigation_id}))
                except Exception:
                    pass  # client disconnected — keep processing

        heartbeat_stop = asyncio.Event()

        async def heartbeat() -> None:
            while not heartbeat_stop.is_set():
                await emit({"phase": "heartbeat", "status": "running"})
                try:
                    await asyncio.wait_for(heartbeat_stop.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass

        hb_task = asyncio.create_task(heartbeat())

        try:
            async with investigation_slot():
                _cache_investigation({
                    "id": investigation_id,
                    "query": query,
                    "query_type": qtype,
                    "status": "running",
                })
                ensure_not_cancelled()
                return await self._execute_investigation(
                    investigation_id=investigation_id,
                    query=query,
                    qtype=qtype,
                    parsed=parsed,
                    timeout_per_tool=timeout_per_tool,
                    discovery_config=discovery_config,
                    image_profile=image_profile,
                    investigation_mode=investigation_mode,
                    emit=emit,
                )
        except InvestigationCancelledError:
            _cache_investigation({
                "id": investigation_id,
                "query": query,
                "query_type": qtype,
                "status": "cancelled",
                "error": "Stopped by user",
            })
            await emit({"phase": "cancelled", "status": "cancelled", "error": "Investigation stopped by user"})
            raise
        except InvestigationBusyError as exc:
            _cache_investigation({
                "id": investigation_id,
                "query": query,
                "query_type": qtype,
                "status": "error",
                "error": str(exc),
            })
            await emit({"phase": "error", "status": "busy", "error": str(exc)})
            raise
        finally:
            end_investigation(investigation_id)
            heartbeat_stop.set()
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

    async def _execute_investigation(
        self,
        *,
        investigation_id: str,
        query: str,
        qtype: str,
        parsed,
        timeout_per_tool: float,
        discovery_config: DiscoveryConfig | None,
        image_profile: str,
        investigation_mode: str | None,
        emit: ProgressCallback,
    ) -> tuple[str, FeatureResult]:
        mode = resolve_investigation_mode(
            explicit=investigation_mode,
            discovery=discovery_config,
            image_profile=image_profile,
        )
        async with investigation_mode_scope(mode):
            return await self._execute_investigation_body(
                investigation_id=investigation_id,
                query=query,
                qtype=qtype,
                parsed=parsed,
                timeout_per_tool=timeout_per_tool,
                discovery_config=discovery_config,
                image_profile=image_profile,
                investigation_mode=mode,
                emit=emit,
            )

    async def _execute_investigation_body(
        self,
        *,
        investigation_id: str,
        query: str,
        qtype: str,
        parsed,
        timeout_per_tool: float,
        discovery_config: DiscoveryConfig | None,
        image_profile: str,
        investigation_mode: str,
        emit: ProgressCallback,
    ) -> tuple[str, FeatureResult]:
        from services.brief_indexer import brief_investigation_scope

        from services.investigation_cancel import InvestigationCancelledError, ensure_not_cancelled

        _brief_scope = brief_investigation_scope(investigation_id, query)
        _brief_scope.__enter__()
        try:
            await emit({
                "phase": "start",
                "query": query,
                "query_type": qtype,
                "investigation_mode": investigation_mode,
                "status": "running",
            })

            discovery = discovery_config or discovery_config_for_query_type(
                qtype if qtype != "multi" else detect_query_type(parsed.username or parsed.email or query),
                deep=investigation_mode == "deep",
            )
            if investigation_mode == "samurai":
                discovery = DiscoveryConfig(enabled=False)
            elif qtype in ("phone", "infra") and investigation_mode != "deep":
                discovery = DiscoveryConfig(enabled=False)
            username_profile = tool_profile_for_mode(investigation_mode, feature="username_search")
            email_profile = tool_profile_for_mode(investigation_mode, feature="email_intel")
            person_profile = tool_profile_for_mode(investigation_mode, feature="domain_intel")

            if qtype == "multi":
                await emit({"phase": "multi_input", "parsed": parsed.raw, "fields": {
                    k: v for k, v in {
                        "username": parsed.username,
                        "email": parsed.email,
                        "phone": parsed.phone,
                        "domain": parsed.domain,
                        "name": parsed.name,
                        "occupation": parsed.occupation,
                    }.items() if v
                }})
                result = await self._run_multi_input(
                    parsed, timeout_per_tool, emit, discovery_config=discovery
                )
            elif qtype == "username":
                result = await self._run_with_progress(
                    "username_search",
                    query,
                    timeout_per_tool,
                    emit,
                    use_username=True,
                    tool_profile=username_profile,
                    tools_override=username_tools_override(investigation_mode),
                )
            elif qtype == "email":
                result = await self._run_email(query, timeout_per_tool, emit, profile=email_profile)
            elif qtype == "image":
                from orchestrator.parallel_config import (
                    DISCOVERY_WALL_SECONDS,
                    IMAGE_WALL_SECONDS,
                    INVESTIGATION_WALL_SECONDS,
                )

                wall_start = time.monotonic()
                deadline = wall_start + INVESTIGATION_WALL_SECONDS
                stage_budget = min(IMAGE_WALL_SECONDS, max(30.0, deadline - time.monotonic()))
                run_coro = self._run_with_progress(
                    "image_intel", query, timeout_per_tool, emit, image_profile=image_profile
                )
                result = await asyncio.wait_for(run_coro, timeout=stage_budget)
            elif qtype == "domain":
                result = await self._run_with_progress(
                    "domain_intel", query, timeout_per_tool, emit, tool_profile=person_profile
                )
            elif qtype in ("phone", "infra"):
                result = await self._run_with_progress(
                    "infra_intel", query, timeout_per_tool, emit, tool_profile=person_profile
                )
            else:
                result = await self._run_with_progress("username_search", query, timeout_per_tool, emit)

            ensure_not_cancelled()

            if discovery.enabled and investigation_mode != "samurai":
                engine = RecursiveDiscoveryEngine()
                expand_seed_query = query
                expand_seed_type = qtype
                if qtype == "multi":
                    expand_seed_query = (parsed.raw or query).strip()
                    if parsed.username:
                        expand_seed_type = "username"
                    elif parsed.email:
                        expand_seed_type = "email"
                    else:
                        expand_seed_type = detect_query_type(parsed.email or parsed.phone or parsed.domain or query)
                if qtype == "image":
                    remaining = max(10.0, deadline - time.monotonic())
                    discovery_budget = min(DISCOVERY_WALL_SECONDS, remaining)
                    result = await asyncio.wait_for(
                        engine.expand(
                            seed_query=expand_seed_query,
                            seed_query_type=expand_seed_type,
                            seed_result=result,
                            config=discovery,
                            timeout_per_tool=min(timeout_per_tool, 40.0),
                            on_progress=emit,
                            deadline_monotonic=time.monotonic() + discovery_budget,
                        ),
                        timeout=discovery_budget + 5,
                    )
                else:
                    result = await engine.expand(
                        seed_query=expand_seed_query,
                        seed_query_type=expand_seed_type,
                        seed_result=result,
                        config=discovery,
                        timeout_per_tool=timeout_per_tool,
                        on_progress=emit,
                    )

            dumped = _dump_result(result)
            _cache_investigation({
                "id": investigation_id,
                "query": query,
                "query_type": qtype,
                "status": "complete",
                "result": dumped,
            })

            from services.copilot import schedule_copilot_pack_build, warm_session_from_result

            warm_session_from_result(investigation_id, dumped, query=query)
            schedule_copilot_pack_build(investigation_id, dumped, query=query)

            from services.persistence.postgres import persist_investigation

            if result.fusion:
                persist_investigation(
                    result.feature,
                    query,
                    result.fusion,
                    result.correlation,
                    to_json_safe(result.graph.model_dump()) if result.graph else {},
                    investigation_id=investigation_id,
                    result_snapshot=_dump_result(result),
                )

            await emit({"phase": "complete", "status": "complete", "result": _dump_result(result)})
            return investigation_id, result
        except InvestigationCancelledError:
            partial = locals().get("result")
            payload: dict[str, Any] = {
                "id": investigation_id,
                "query": query,
                "query_type": qtype,
                "status": "cancelled",
                "error": "Stopped by user",
            }
            if partial is not None:
                payload["result"] = _dump_result(partial)
                payload["partial"] = True
            _cache_investigation(payload)
            await emit({
                "phase": "cancelled",
                "status": "cancelled",
                "error": "Investigation stopped by user",
                "result": payload.get("result"),
            })
            raise
        except asyncio.TimeoutError:  # noqa: PERF203 — investigation wall budget
            partial = locals().get("result")
            if partial is not None:
                partial_dump = _dump_result(partial)
                _cache_investigation({
                    "id": investigation_id,
                    "query": query,
                    "query_type": qtype,
                    "status": "complete",
                    "result": partial_dump,
                    "partial": True,
                })
                from services.copilot import schedule_copilot_pack_build, warm_session_from_result

                warm_session_from_result(investigation_id, partial_dump, query=query)
                schedule_copilot_pack_build(investigation_id, partial_dump, query=query)
                await emit({
                    "phase": "complete",
                    "status": "complete",
                    "partial": True,
                    "message": "Investigation finished within the 5-minute budget with partial expansion results.",
                    "result": _dump_result(partial),
                })
                return investigation_id, partial
            await emit({
                "phase": "error",
                "status": "error",
                "error": "Investigation exceeded the 5-minute limit. Try again or enable Deep mode for a full scan.",
            })
            _cache_investigation({
                "id": investigation_id,
                "query": query,
                "query_type": qtype,
                "status": "error",
                "error": "timeout_5min",
            })
            raise
        except Exception as exc:
            import logging
            import traceback

            logging.getLogger(__name__).error(
                "Investigation failed: %s\n%s", exc, traceback.format_exc(),
            )
            _cache_investigation({
                "id": investigation_id,
                "query": query,
                "query_type": qtype,
                "status": "error",
                "error": str(exc),
            })
            await emit({"phase": "error", "status": "error", "error": str(exc)})
            raise
        finally:
            _brief_scope.__exit__(None, None, None)

    async def _run_multi_input(
        self,
        parsed,
        timeout: float,
        emit: ProgressCallback,
        *,
        discovery_config: DiscoveryConfig | None = None,
    ) -> FeatureResult:
        """Run email, username, domain, phone branches — sequential by default to avoid OOM."""
        dual_combo = bool(parsed.username and parsed.email)
        deep_multi = get_investigation_mode() == "deep"
        quick_multi = get_investigation_mode() == "fast"

        async def _execute() -> FeatureResult:
            return await self._run_multi_branches(parsed, timeout, emit, dual_combo=dual_combo)

        if dual_combo:
            mode_label = "dual_parallel" if DUAL_BRANCH_PARALLEL else "dual_sequential"
            if deep_multi:
                message = (
                    "Deep multi-input: username + email in parallel with full scan budgets, then discovery hops"
                    if DUAL_BRANCH_PARALLEL
                    else "Deep multi-input: username + email sequentially, then discovery hops"
                )
            elif quick_multi:
                message = (
                    "Quick multi-input: core username + email tools only, no discovery hops"
                    if DUAL_BRANCH_PARALLEL
                    else "Quick multi-input: username + email sequentially, seed tools only"
                )
            elif DUAL_BRANCH_PARALLEL:
                message = "Username + email in parallel (capped concurrency — ~5 min target)"
            else:
                message = "Username + email sequentially (low-memory mode)"
            await emit({
                "phase": "multi_input",
                "status": "running",
                "mode": mode_label,
                "deep": deep_multi,
                "message": message,
            })

            async with dual_identity_scan():
                if deep_multi:
                    async with full_scan_mode():
                        return await _execute()
                return await _execute()

        return await _execute()

    async def _run_multi_branches(
        self,
        parsed,
        timeout: float,
        emit: ProgressCallback,
        *,
        dual_combo: bool = False,
    ) -> FeatureResult:
        from services.multi_investigation import merge_feature_results

        mode = get_investigation_mode()
        username_profile = tool_profile_for_mode(mode, feature="username_search")
        email_profile = tool_profile_for_mode(mode, feature="email_intel")
        person_profile = tool_profile_for_mode(mode, feature="domain_intel")
        username_override = username_tools_override(mode)

        if mode == "samurai":
            seed = (parsed.raw or parsed.username or "").strip()
            if not seed:
                return FeatureResult(
                    feature="username_search",
                    query=parsed.raw,
                    tool_results=[
                        ToolResult(
                            tool="samurai",
                            success=False,
                            error="Username required for Samurai social lookup",
                        )
                    ],
                )
            return await self._run_with_progress(
                "username_search",
                seed,
                timeout,
                emit,
                use_username=False,
                tools_override=username_override,
            )

        parallel_branches = (MULTI_INPUT_PARALLEL and not dual_combo) or (dual_combo and DUAL_BRANCH_PARALLEL)
        mode = "parallel" if parallel_branches else "sequential"
        if not dual_combo:
            await emit({
                "phase": "multi_input",
                "status": "running",
                "mode": mode,
                "message": (
                    "Running all input types concurrently"
                    if parallel_branches
                    else "Running input types one at a time (safer for RAM)"
                ),
            })

        async def _maybe_username():
            if not parsed.username:
                return None
            return await self._run_with_progress(
                "username_search",
                parsed.username,
                timeout,
                emit,
                use_username=True,
                tool_profile=username_profile,
                tools_override=username_override,
            )

        async def _maybe_email():
            if not parsed.email:
                return None
            return await self._run_email(parsed.email, timeout, emit, profile=email_profile)

        async def _maybe_domain():
            if not parsed.domain:
                return None
            return await self._run_with_progress(
                "domain_intel", parsed.domain, timeout, emit, tool_profile=person_profile
            )

        async def _maybe_phone():
            if not parsed.phone:
                return None
            return await self._run_with_progress(
                "infra_intel", parsed.phone, timeout, emit, tool_profile=person_profile
            )

        async def _maybe_context_dork():
            dork_q = parsed.dork_query()
            if dork_q == parsed.raw.strip() and not parsed.occupation and not parsed.name:
                return None
            if mode == "fast":
                return None
            return await self._run_with_progress(
                "username_search",
                dork_q,
                timeout,
                emit,
                use_username=False,
                tool_profile=username_profile,
                tools_override=["google_dorking"],
            )

        branch_fns = [
            ("username", _maybe_username),
            ("email", _maybe_email),
            ("domain", _maybe_domain),
            ("phone", _maybe_phone),
            ("context_dork", _maybe_context_dork),
        ]

        results: list[FeatureResult] = []

        async def _run_branch(branch_name: str, coro_factory) -> FeatureResult | None:
            try:
                branch = await coro_factory()
            except Exception as exc:
                await emit({"phase": "multi_input", "status": "warning", "branch": branch_name, "error": str(exc)})
                return None
            if isinstance(branch, FeatureResult):
                return branch
            return None

        if parallel_branches:
            branches = await asyncio.gather(
                *[_run_branch(name, fn) for name, fn in branch_fns],
                return_exceptions=True,
            )
            for branch in branches:
                if isinstance(branch, FeatureResult):
                    results.append(branch)
                elif isinstance(branch, Exception):
                    await emit({"phase": "multi_input", "status": "warning", "error": str(branch)})
        else:
            for branch_name, fn in branch_fns:
                await emit({"phase": "multi_input", "status": "running", "branch": branch_name})
                branch = await _run_branch(branch_name, fn)
                if branch:
                    results.append(branch)
                if dual_combo:
                    import gc

                    gc.collect()
                    await asyncio.sleep(0.5)

        if not results:
            return await self._run_with_progress(
                "username_search",
                parsed.raw,
                timeout,
                emit,
                use_username=True,
                tool_profile=username_profile,
                tools_override=username_override,
            )

        await emit({
            "phase": "multi_input",
            "status": "done",
            "message": "Username + email branches complete — merging intelligence",
        })
        await emit({"phase": "evidence_extraction", "status": "running", "message": "Building unified person profile"})
        merged = await merge_feature_results(results, seed_query=parsed.raw, parsed=parsed)
        await emit({"phase": "fusion", "status": "done", "fusion_score": merged.fusion.fusion_score if merged.fusion else 0})
        await emit({"phase": "correlation", "status": "done"})
        await emit({"phase": "graph", "status": "done"})
        return merged

    async def _run_email(
        self,
        email: str,
        timeout: float,
        emit: ProgressCallback,
        *,
        profile: str | None = None,
    ) -> FeatureResult:
        from orchestrator.config import get_feature_tools

        effective_profile = profile or tool_profile_for_mode(get_investigation_mode(), feature="email_intel")
        tools = get_feature_tools("email_intel", target=email, profile=effective_profile)
        if is_dual_identity_scan():
            tools = [t for t in tools if t != "spiderfoot"]
        completed_results: list[ToolResult] = []

        async def on_tool_started(tool: str) -> None:
            await emit({"phase": "tool", "tool": tool, "status": "running"})

        async def on_tool_done(_tool: str, tr: ToolResult) -> None:
            completed_results.append(tr)
            await emit({
                "phase": "tool",
                "tool": tr.tool,
                "status": "done" if tr.success else "failed",
                "success": tr.success,
                "execution_time_ms": tr.execution_time_ms,
                "tool_error": tr.error,
            })
            from services.brief_indexer import on_tool_completed

            on_tool_completed(tr, query=email)
            await _emit_email_tool_findings(emit, tr)
            await _emit_email_collection_partial(
                emit,
                email,
                list(completed_results),
                tools_total=len(tools),
            )

        result = await self._orchestrator.execute_email_intel(
            email,
            timeout,
            tools,
            on_tool_started=on_tool_started,
            on_tool_done=on_tool_done,
            on_progress=emit,
        )
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
        image_profile: str = "fast",
        tool_profile: str = "fast",
        tools_override: list[str] | None = None,
    ) -> FeatureResult:
        from adapters.scan_config import google_dork_budget_sec, scan_budget_sec, social_analyzer_budget_sec
        from adapters.scan_summary import scan_summary_entry
        from adapters.site_lists import total_username_sites
        from orchestrator.config import DEFAULT_TIMEOUTS, effective_tool_timeout, get_feature_tools
        from orchestrator.parallel_config import (
            feature_tool_concurrency,
            image_tools_for_profile,
            is_ml_image_tool,
            max_io_tool_concurrency,
            max_ml_tool_concurrency,
            reverse_sources_for_profile,
        )
        from services.correlation.engine import correlation_engine
        from services.fusion import build_fusion_output, fuse_results
        from services.graph_intelligence.engine import graph_engine
        from services.intelligence.person import build_identity_profile
        from services.normalization import build_confidence_inputs, normalize_tool_results
        from services.username import normalize_username

        start = time.monotonic()
        if feature == "image_intel":
            tool_names = tools_override or get_feature_tools(feature, profile=image_profile)
            profile_tools = image_tools_for_profile(image_profile)
            tool_names = [t for t in tool_names if t in profile_tools] or profile_tools
        else:
            effective_profile = tool_profile_for_mode(get_investigation_mode(), feature=feature)
            if tool_profile in ("fast", "deep"):
                effective_profile = tool_profile
            tool_names = tools_override or get_feature_tools(
                feature,
                target=query,
                profile=effective_profile,
            )
            if feature == "username_search":
                tool_names = [t for t in tool_names if t not in ("gitfive", "nexfil")]
        default_timeout = timeout or DEFAULT_TIMEOUTS.get(feature, 120.0)
        if feature == "username_search":
            default_timeout = min(default_timeout, scan_budget_sec())
        warnings: list[str] = []
        query_normalized = None
        scan_query = query

        if use_username:
            normalized, warnings = normalize_username(query)
            scan_query = normalized or query
            query_normalized = scan_query if scan_query != query else None

        for tool in tool_names:
            await emit({"phase": "tool", "tool": tool, "status": "pending"})

        image_ml_sem = (
            asyncio.Semaphore(max_ml_tool_concurrency()) if feature == "image_intel" else None
        )
        image_io_sem = (
            asyncio.Semaphore(max_io_tool_concurrency()) if feature == "image_intel" else None
        )

        USERNAME_SCAN_TOOLS = frozenset({"maigret", "sherlock", "social_analyzer"})
        partial_scan_rows: dict[str, list] = {}
        partial_phase_done: dict[str, set[int]] = {t: set() for t in tool_names if t in USERNAME_SCAN_TOOLS}
        sites_total_estimate = total_username_sites() if feature == "username_search" else 0
        last_partial_emit = 0.0
        completed: dict[str, ToolResult] = {}
        scan_progress_totals: dict[str, int] = {}

        async def _emit_generic_partial(
            fusion_snapshot,
            tr_list: list[ToolResult],
            *,
            evidence_extraction=None,
            identity_profile=None,
        ) -> None:
            if not fusion_snapshot:
                return
            await emit({
                "phase": "collection_partial",
                "status": "running",
                "fusion": to_json_safe(fusion_snapshot.model_dump()),
                "tool_results": to_json_safe([tr.model_dump() for tr in tr_list]),
                "evidence_extraction": to_json_safe(evidence_extraction.model_dump()) if evidence_extraction else None,
                "identity_profile": to_json_safe(identity_profile.model_dump()) if identity_profile else None,
                "correlation": None,
                "graph": None,
                "fusion_score": fusion_snapshot.fusion_score,
            })

        async def _emit_live_profile_snapshot(
            fusion_snapshot,
            *,
            scan_phase: int,
            tool_results_for_ui: list[ToolResult] | None = None,
            force: bool = False,
            skip_refine: bool = False,
            evidence_extraction=None,
            identity_profile=None,
        ) -> None:
            nonlocal last_partial_emit
            if feature != "username_search":
                return
            now = time.monotonic()
            if not force and now - last_partial_emit < 2.0:
                return

            try:
                working_fusion = fusion_snapshot
                if not skip_refine and use_username and working_fusion.deduplicated_entities:
                    from services.evidence.profile_verifier import refine_username_fusion

                    working_fusion = await refine_username_fusion(working_fusion, seed_query=query)

                if evidence_extraction is None and working_fusion.deduplicated_entities:
                    from services.evidence.engine import evidence_engine

                    tr_for_linguistic = tool_results_for_ui or [
                        completed[t] for t in tool_names if t in completed
                    ]
                    working_fusion, evidence_extraction = await evidence_engine.extract(
                        working_fusion,
                        seed_query=query,
                        enrich_public_profiles=use_username,
                        tool_results=tr_for_linguistic or None,
                        run_linguistic=False,
                    )

                if identity_profile is None and working_fusion.deduplicated_entities:
                    identity_profile = build_identity_profile(
                        seed_query=query,
                        fusion=working_fusion,
                        evidence_extraction=evidence_extraction,
                        enrichment_pass=1 if tool_results_for_ui is None else 0,
                    )
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning(
                    "Partial profile snapshot skipped (%s): %s", type(exc).__name__, exc,
                )
                return

            sites_checked = sum(scan_progress_totals.values()) if scan_progress_totals else 0
            last_partial_emit = now
            tr_payload = tool_results_for_ui or [completed[t] for t in tool_names if t in completed]
            await emit({
                "phase": "collection_partial",
                "scan_phase": scan_phase,
                "status": "running",
                "sites_checked": sites_checked,
                "sites_total": sites_total_estimate,
                "fusion_score": working_fusion.fusion_score,
                "identity_profile": to_json_safe(identity_profile.model_dump()) if identity_profile else None,
                "evidence_extraction": to_json_safe(evidence_extraction.model_dump()) if evidence_extraction else None,
                "fusion": to_json_safe(working_fusion.model_dump()),
                "tool_results": to_json_safe([tr.model_dump() for tr in tr_payload]) if tr_payload else [],
            })

        async def _emit_collection_partial(scan_phase: int, *, force: bool = False) -> None:
            if feature != "username_search":
                return
            available: list[ToolResult] = []
            for tool in tool_names:
                if tool in completed:
                    available.append(completed[tool])
                elif tool in partial_scan_rows and partial_scan_rows[tool]:
                    rows = [*partial_scan_rows[tool], {
                        "platform": "_scan_summary",
                        "source_tool": tool,
                        "sites_checked": scan_progress_totals.get(tool, 0),
                        "sites_found": len(partial_scan_rows[tool]),
                        "note": f"Phase {scan_phase} partial",
                    }]
                    available.append(ToolResult(tool=tool, success=True, data=rows))
            if not available:
                return
            partial_fusion = build_fusion_output(available, feature, query)
            await _emit_live_profile_snapshot(
                partial_fusion,
                scan_phase=scan_phase,
                tool_results_for_ui=available,
                force=force,
            )

        async def on_adapter_progress(event: dict[str, Any]) -> None:
            tool = str(event.get("tool") or "")
            if tool not in USERNAME_SCAN_TOOLS:
                return
            snapshot = event.get("results_snapshot")
            if isinstance(snapshot, list) and snapshot:
                from adapters.chunk_runner import dedupe_by_url

                merged_rows = dedupe_by_url([*(partial_scan_rows.get(tool) or []), *snapshot])
                partial_scan_rows[tool] = merged_rows[-200:]
            scan_phase = int(event.get("scan_phase") or 0)
            if event.get("sites_checked") is not None:
                scan_progress_totals[tool] = int(event["sites_checked"])
            await emit({
                "phase": "scan_progress",
                "tool": tool,
                "scan_phase": scan_phase,
                "sites_checked": event.get("sites_checked"),
                "sites_total": event.get("sites_total"),
                "hits": event.get("hits"),
                "phase_complete": bool(event.get("phase_complete")),
            })
            if event.get("phase_complete") and scan_phase:
                partial_phase_done.setdefault(tool, set()).add(scan_phase)
                await _emit_collection_partial(scan_phase, force=scan_phase == 1)

        started_tools: set[str] = set()

        async def run_tool(tool: str) -> tuple[str, ToolResult]:
            from services.investigation_cancel import ensure_not_cancelled

            ensure_not_cancelled()
            started_tools.add(tool)
            await emit({"phase": "tool", "tool": tool, "status": "running"})
            tool_timeout = effective_tool_timeout(tool, default_timeout)
            if feature == "username_search" and tool == "social_analyzer":
                tool_timeout = min(tool_timeout, social_analyzer_budget_sec())
            elif feature == "username_search" and tool == "google_dorking":
                tool_timeout = min(tool_timeout, google_dork_budget_sec())
            elif feature == "username_search" and tool == "blackbird":
                tool_timeout = min(max(tool_timeout, 60.0), 90.0)
            elif feature == "username_search" and tool in USERNAME_SCAN_TOOLS:
                tool_timeout = min(tool_timeout, scan_budget_sec())
            elif feature == "infra_intel" and tool == "phone_social_intel":
                from orchestrator.parallel_config import PHONE_SOCIAL_INTEL_WALL_SEC
                tool_timeout = max(tool_timeout, PHONE_SOCIAL_INTEL_WALL_SEC)
            elif feature == "infra_intel" and tool == "phoneinfoga":
                from orchestrator.parallel_config import PHONEINFOGA_WALL_SEC
                tool_timeout = max(tool_timeout, PHONEINFOGA_WALL_SEC)
            progress_cb = on_adapter_progress if tool in USERNAME_SCAN_TOOLS else None
            # Samurai parses multi-field seeds (username | email | name) — scan_query strips pipes.
            tool_query = query if tool == "samurai" else scan_query
            adapter = self._orchestrator._get_adapter(tool)
            try:
                async with tool_subprocess_slot():
                    if image_ml_sem and image_io_sem:
                        sem = image_ml_sem if is_ml_image_tool(tool) else image_io_sem
                        async with sem:
                            tr = await adapter.run(tool_query, timeout=tool_timeout, on_progress=progress_cb)
                    elif image_ml_sem:
                        async with image_ml_sem:
                            tr = await adapter.run(tool_query, timeout=tool_timeout, on_progress=progress_cb)
                    else:
                        tr = await adapter.run(tool_query, timeout=tool_timeout, on_progress=progress_cb)
            except asyncio.CancelledError:
                partial_getter = getattr(adapter, "_partial_tool_result", None)
                partial = partial_getter() if callable(partial_getter) else None
                if partial:
                    tr = partial
                else:
                    raise
            await emit({
                "phase": "tool",
                "tool": tool,
                "status": "done" if tr.success else "failed",
                "success": tr.success,
                "execution_time_ms": tr.execution_time_ms,
                "tool_error": tr.error,
            })
            safe_tr = _safe_tool_result(tr)
            from services.brief_indexer import on_tool_completed

            on_tool_completed(safe_tr, query=query)
            completed[tool] = safe_tr
            if feature != "email_intel":
                partial_tr = [completed[t] for t in tool_names if t in completed]
                if partial_tr:
                    partial_fusion = build_fusion_output(partial_tr, feature, query)
                    await _emit_generic_partial(partial_fusion, partial_tr)
                    if feature == "username_search":
                        await _emit_live_profile_snapshot(
                            partial_fusion,
                            scan_phase=3,
                            tool_results_for_ui=partial_tr,
                        )
            return tool, safe_tr

        from orchestrator.parallel_config import batch_wall_seconds, effective_wall_seconds, feature_wall_seconds
        from orchestrator.parallel_runner import execute_tools_parallel

        def _finalize_wall_tool_result(tool: str, tr: ToolResult | None) -> ToolResult:
            partial_rows = [
                row for row in (partial_scan_rows.get(tool) or [])
                if isinstance(row, dict) and row.get("platform") != "_scan_summary"
            ]
            if tr and tr.success and tr.data:
                return tr
            if partial_rows:
                checked = scan_progress_totals.get(tool) or len(partial_rows)
                summary = scan_summary_entry(
                    tool,
                    sites_checked=checked,
                    sites_found=len(partial_rows),
                    note="Partial scan preserved after time budget",
                )
                return ToolResult(
                    tool=tool,
                    success=True,
                    data=[*partial_rows, summary],
                    raw_output=f"{checked} site(s) checked, {len(partial_rows)} hit(s) (partial)",
                )
            if tr:
                return tr
            if tool not in started_tools:
                return ToolResult(
                    tool=tool,
                    success=False,
                    error="Queued but did not start before the investigation time budget expired",
                )
            return ToolResult(
                tool=tool,
                success=False,
                error="Cancelled — investigation wall clock reached while tool was running",
            )

        async def _emit_tool_final(tr: ToolResult) -> None:
            await emit({
                "phase": "tool",
                "tool": tr.tool,
                "status": "done" if tr.success else "failed",
                "success": tr.success,
                "execution_time_ms": tr.execution_time_ms,
                "tool_error": tr.error,
            })

        async def _run_one(tool: str) -> ToolResult:
            _, tr = await run_tool(tool)
            return tr

        from adapters.scan_config import google_dork_budget_sec, scan_budget_sec, social_analyzer_budget_sec

        def _parallel_wall_for_tools() -> float:
            base = effective_wall_seconds(feature)
            if feature == "infra_intel":
                from orchestrator.parallel_config import PHONE_SOCIAL_INTEL_WALL_SEC, PHONE_WALL_SEC
                from services.query_detector import detect_query_type

                if detect_query_type(query) == "phone":
                    return max(base, PHONE_WALL_SEC, PHONE_SOCIAL_INTEL_WALL_SEC)
                return base
            if feature != "username_search":
                return base
            budgets = [base]
            for t in tool_names:
                if t == "social_analyzer":
                    budgets.append(social_analyzer_budget_sec())
                elif t == "google_dorking":
                    budgets.append(google_dork_budget_sec())
                elif t in USERNAME_SCAN_TOOLS:
                    budgets.append(scan_budget_sec())
            return max(budgets)

        def _tool_wall_sec(tool: str) -> float:
            floor = effective_tool_timeout(tool, default_timeout)
            base = max(_parallel_wall_for_tools(), floor)
            if feature == "infra_intel":
                from orchestrator.parallel_config import PHONE_SOCIAL_INTEL_WALL_SEC, PHONE_WALL_SEC
                from services.query_detector import detect_query_type

                if detect_query_type(query) == "phone":
                    import os
                    from orchestrator.parallel_config import PHONEINFOGA_WALL_SEC

                    if tool == "phone_social_intel":
                        return max(base, PHONE_SOCIAL_INTEL_WALL_SEC)
                    if tool == "phoneinfoga":
                        return max(base, PHONEINFOGA_WALL_SEC)
                    if tool == "google_dorking":
                        return max(base, float(os.getenv("PHONE_GOOGLE_DORK_WALL_SEC", "90")))
                    return max(base, PHONE_WALL_SEC)
            return base

        def _partial_for(tool: str) -> ToolResult | None:
            try:
                adapter = self._orchestrator._get_adapter(tool)
            except ValueError:
                return None
            getter = getattr(adapter, "_partial_tool_result", None)
            return getter() if callable(getter) else None

        wall = feature_wall_seconds(feature) if feature != "image_intel" else None
        if wall:
            per_tool_wall = _parallel_wall_for_tools()
            concurrency = effective_tool_concurrency(feature, feature_tool_concurrency(feature))
            batch_wall = batch_wall_seconds(feature, len(tool_names), concurrency or 1)
            batch_wall = max(batch_wall, per_tool_wall, max(_tool_wall_sec(t) for t in tool_names))
            tool_result_list, _ = await execute_tools_parallel(
                tool_names,
                _run_one,
                wall_sec=per_tool_wall,
                max_batch_sec=batch_wall,
                max_concurrency=concurrency,
                tool_wall_sec=_tool_wall_sec,
                partial_result_for=_partial_for,
            )
            from services.investigation_cancel import ensure_not_cancelled

            ensure_not_cancelled()
            by_tool = {tr.tool: tr for tr in tool_result_list}
            tool_results = []
            for tool in tool_names:
                finalized = _finalize_wall_tool_result(tool, by_tool.get(tool))
                completed[tool] = finalized
                tool_results.append(finalized)
                await _emit_tool_final(finalized)
        else:
            tasks = [asyncio.create_task(run_tool(tool)) for tool in tool_names]
            for task in asyncio.as_completed(tasks):
                tool, tr = await task
                completed[tool] = tr
            tool_results = [completed[tool] for tool in tool_names]

        await emit({"phase": "fusion", "status": "running"})
        normalized_results = normalize_tool_results(tool_results)
        merged = fuse_results(normalized_results)
        confidence_inputs = build_confidence_inputs(tool_results)
        fusion = build_fusion_output(tool_results, feature, query)
        await _emit_generic_partial(fusion, tool_results)

        if feature == "username_search" and fusion.deduplicated_entities:
            from services.evidence.profile_verifier import refine_username_fusion

            await emit({"phase": "profile_verification", "status": "running"})
            fusion = await refine_username_fusion(fusion, seed_query=query)
            await emit({"phase": "profile_verification", "status": "done"})

        intel = None
        reverse_image_discovery = None
        image_correlation = None
        if feature == "image_intel":
            from schemas.image_intelligence import ImageIntelligenceOutput
            from services.image_correlation.engine import image_correlation_engine
            from services.image_intelligence.context import build_image_search_context
            from services.image_intelligence.engine import image_intelligence_engine
            from services.reverse_image.engine import ReverseImageDiscoveryEngine

            fast = image_profile != "deep"
            search_context = build_image_search_context(tool_results)
            rev_engine = ReverseImageDiscoveryEngine(
                source_names=reverse_sources_for_profile(image_profile),
            )

            await emit({"phase": "image_intelligence", "status": "running"})
            await emit({"phase": "reverse_image_discovery", "status": "running"})

            intel, reverse_image_discovery = await asyncio.gather(
                image_intelligence_engine.analyze(
                    scan_query, tool_results=tool_results, fast=fast,
                ),
                rev_engine.discover(
                    scan_query,
                    seed_query=query,
                    context=search_context,
                    on_progress=emit,
                ),
            )

            fusion = image_intelligence_engine.merge_into_fusion(fusion, intel)
            await emit({
                "phase": "image_intelligence",
                "status": "done",
                "face_count": intel.face_count,
                "findings_count": len(intel.findings),
                "modules_run": intel.modules_run,
            })

            rev_entities = rev_engine.matches_to_entities(reverse_image_discovery)
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
            await emit({
                "phase": "reverse_image_discovery",
                "status": "done",
                "matches": reverse_image_discovery.total_matches,
                "leads": len(reverse_image_discovery.generated_leads),
                "sources_run": reverse_image_discovery.sources_run,
            })

        await emit({"phase": "fusion", "status": "done", "fusion_score": fusion.fusion_score})

        from services.intelligence.person import build_identity_profile

        evidence_extraction = None
        identity_profile = None
        if fusion and fusion.deduplicated_entities:
            from services.evidence.engine import evidence_engine

            await emit({"phase": "evidence_extraction", "status": "running"})
            fusion, evidence_extraction = await evidence_engine.extract(
                fusion,
                seed_query=query,
                enrich_public_profiles=use_username,
                tool_results=tool_results,
            )
            identity_profile = build_identity_profile(
                seed_query=query,
                fusion=fusion,
                evidence_extraction=evidence_extraction,
                enrichment_pass=1,
            )
            await emit({
                "phase": "evidence_extraction",
                "status": "done",
                "fields_extracted": evidence_extraction.fields_extracted,
                "platforms_analyzed": evidence_extraction.platforms_analyzed,
                "identity_confidence": identity_profile.confidence_score,
            })
            await _emit_generic_partial(
                fusion,
                tool_results,
                evidence_extraction=evidence_extraction,
                identity_profile=identity_profile,
            )
            if use_username:
                await _emit_live_profile_snapshot(
                    fusion,
                    scan_phase=2,
                    tool_results_for_ui=tool_results,
                    force=True,
                    skip_refine=True,
                    evidence_extraction=evidence_extraction,
                    identity_profile=identity_profile,
                )

        await emit({"phase": "correlation", "status": "running"})
        correlation = await correlation_engine.correlate(fusion, seed_query=query)
        await emit({"phase": "correlation", "status": "done", "clusters": correlation.total_clusters})

        await emit({"phase": "graph", "status": "running"})
        graph = graph_engine.analyze(
            fusion,
            correlation,
            seed_query=query,
            identity_profile=identity_profile,
            evidence_extraction=evidence_extraction,
        )
        await emit({"phase": "graph", "status": "done", "nodes": graph.node_count})
        await _emit_generic_partial(
            fusion,
            tool_results,
            evidence_extraction=evidence_extraction,
            identity_profile=identity_profile,
        )

        succeeded = sum(1 for r in tool_results if r.success)
        return FeatureResult(
            feature=feature,
            query=query,
            query_normalized=query_normalized,
            warnings=warnings,
            tool_results=tool_results,
            merged_results=to_json_safe(merged),
            fusion=fusion,
            correlation=correlation,
            graph=graph,
            confidence_raw_inputs=confidence_inputs,
            evidence_extraction=evidence_extraction,
            identity_profile=identity_profile,
            reverse_image_discovery=to_json_safe(reverse_image_discovery.model_dump()) if reverse_image_discovery else None,
            image_correlation=to_json_safe(image_correlation.model_dump()) if image_correlation else None,
            total_execution_time_ms=(time.monotonic() - start) * 1000,
            tools_succeeded=succeeded,
            tools_failed=len(tool_results) - succeeded,
        )


investigation_runner = InvestigationRunner()
