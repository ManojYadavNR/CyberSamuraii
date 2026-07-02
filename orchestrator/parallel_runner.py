"""Wall-clock bounded parallel tool execution."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from typing import Any

from schemas.common import ToolResult

RunToolFn = Callable[[str], Awaitable[ToolResult]]
OnToolStarted = Callable[[str], Awaitable[None]]
OnToolDone = Callable[[str, ToolResult], Awaitable[None]]
ToolWallSecFn = Callable[[str], float]
PartialResultFn = Callable[[str], ToolResult | None]


async def _safe_progress(cb: Callable[..., Awaitable[None]] | None, *args: Any) -> None:
    if not cb:
        return
    try:
        await cb(*args)
    except Exception:
        import logging

        logging.getLogger(__name__).warning("Tool progress callback failed", exc_info=True)


async def execute_tools_parallel(
    tool_names: list[str],
    run_tool: RunToolFn,
    *,
    wall_sec: float,
    max_concurrency: int | None = None,
    max_batch_sec: float | None = None,
    on_tool_started: OnToolStarted | None = None,
    on_tool_done: OnToolDone | None = None,
    tool_wall_sec: ToolWallSecFn | None = None,
    partial_result_for: PartialResultFn | None = None,
) -> tuple[list[ToolResult], dict[str, Any]]:
    """
    Launch tools with bounded concurrency.
    Each tool gets up to wall_sec once it starts (queue wait is not counted).
    max_batch_sec caps total batch time so queued tools are not starved forever.
    """
    if not tool_names:
        return [], {"wall_sec": wall_sec, "cancelled": []}

    limit = max(1, max_concurrency or len(tool_names))
    sem = asyncio.Semaphore(limit)
    results: dict[str, ToolResult] = {}
    queue_state: dict[str, str] = dict.fromkeys(tool_names, "queued")
    started = time.monotonic()

    if max_batch_sec is None:
        slots = max(1, (len(tool_names) + limit - 1) // limit)
        max_batch_sec = wall_sec * slots
    batch_deadline = started + max_batch_sec
    notified_done: set[str] = set()

    def _budget(tool: str) -> float:
        return tool_wall_sec(tool) if tool_wall_sec else wall_sec

    async def _notify_done(tool: str) -> None:
        if tool in notified_done or tool not in results:
            return
        notified_done.add(tool)
        await _safe_progress(on_tool_done, tool, results[tool])

    async def _bounded(tool: str) -> None:
        from services.investigation_cancel import is_cancelled

        try:
            if is_cancelled():
                results[tool] = ToolResult(tool=tool, success=False, error="Cancelled — investigation stopped by user")
                return
            async with sem:
                queue_state[tool] = "running"
                await _safe_progress(on_tool_started, tool)
                now = time.monotonic()
                if now >= batch_deadline:
                    results[tool] = ToolResult(
                        tool=tool,
                        success=False,
                        error="Batch time budget exhausted before this tool could start",
                    )
                    return
                remaining_batch = batch_deadline - now
                tool_budget = min(_budget(tool), remaining_batch)
                budget_label = _budget(tool)
                try:
                    results[tool] = await asyncio.wait_for(
                        run_tool(tool),
                        timeout=max(5.0, tool_budget),
                    )
                except asyncio.TimeoutError:
                    partial = partial_result_for(tool) if partial_result_for else None
                    if partial and partial.success:
                        results[tool] = partial
                    else:
                        results[tool] = ToolResult(
                            tool=tool,
                            success=False,
                            error=f"Wall timeout ({budget_label:.0f}s) — tool exceeded its run budget",
                        )
        except asyncio.CancelledError:
            if tool not in results:
                if queue_state.get(tool) == "queued":
                    results[tool] = ToolResult(
                        tool=tool,
                        success=False,
                        error="Cancelled while waiting in queue — batch time budget reached",
                    )
                else:
                    results[tool] = ToolResult(
                        tool=tool,
                        success=False,
                        error=f"Cancelled — investigation wall ({wall_sec:.0f}s) reached",
                    )
            raise
        except Exception as exc:
            results[tool] = ToolResult(
                tool=tool,
                success=False,
                error=f"Parallel runner: {type(exc).__name__}: {exc}",
            )
        finally:
            await _notify_done(tool)

    tasks = {tool: asyncio.create_task(_bounded(tool), name=f"tool:{tool}") for tool in tool_names}

    from services.investigation_cancel import is_cancelled

    pending = set(tasks.values())
    try:
        while pending:
            if is_cancelled():
                for task in pending:
                    task.cancel()
                break
            remaining = batch_deadline - time.monotonic()
            if remaining <= 0:
                break
            done, pending = await asyncio.wait(
                pending,
                timeout=min(0.5, remaining),
                return_when=asyncio.FIRST_COMPLETED,
            )
    except asyncio.CancelledError:
        for task in pending:
            task.cancel()
        raise

    cancelled: list[str] = []
    user_stopped = is_cancelled()
    for tool, task in tasks.items():
        if task.done():
            continue
        task.cancel()
        cancelled.append(tool)
        if tool not in results:
            if user_stopped:
                msg = "Cancelled — investigation stopped by user"
            elif queue_state.get(tool) == "queued":
                msg = "Cancelled while waiting in queue — batch time budget exhausted"
            else:
                msg = f"Wall timeout ({_budget(tool):.0f}s) — tool still running"
            partial = partial_result_for(tool) if partial_result_for else None
            if partial and partial.success and not user_stopped:
                results[tool] = partial
            else:
                results[tool] = ToolResult(tool=tool, success=False, error=msg)

    if cancelled:
        await asyncio.gather(*[tasks[t] for t in cancelled], return_exceptions=True)
        for tool in cancelled:
            await _notify_done(tool)

    ordered = [results.get(tool, ToolResult(tool=tool, success=False, error="No result")) for tool in tool_names]
    meta = {
        "wall_sec": wall_sec,
        "batch_sec": max_batch_sec,
        "elapsed_sec": time.monotonic() - started,
        "cancelled": cancelled,
        "concurrency": limit,
    }
    return ordered, meta
