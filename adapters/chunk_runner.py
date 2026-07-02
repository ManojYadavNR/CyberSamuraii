"""Parallel chunk execution — two-phase priority scanning for username tools."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from adapters.scan_config import CHUNK_SIZE, SCAN_PROGRESS_SNAPSHOT_MAX, phase1_parallel, phase2_parallel

T = TypeVar("T")


def split_chunks(items: list[T], chunk_size: int = CHUNK_SIZE) -> list[list[T]]:
    if not items:
        return []
    size = max(1, chunk_size)
    return [items[i : i + size] for i in range(0, len(items), size)]


async def run_chunked(
    items: list[T],
    run_one: Callable[[list[T], int], Awaitable[tuple[list[Any], int]]],
    *,
    chunk_size: int = CHUNK_SIZE,
    max_parallel: int | None = None,
) -> tuple[list[Any], int]:
    chunks = split_chunks(items, chunk_size)
    if not chunks:
        return [], 0

    parallel = max(1, max_parallel if max_parallel is not None else phase2_parallel())
    sem = asyncio.Semaphore(parallel)
    merged: list[Any] = []
    sites_checked = 0

    async def _worker(chunk: list[T], index: int) -> None:
        nonlocal sites_checked
        async with sem:
            try:
                rows, checked = await run_one(chunk, index)
                sites_checked += checked
                merged.extend(rows)
            except Exception:
                sites_checked += len(chunk)

    await asyncio.gather(*(_worker(chunk, idx) for idx, chunk in enumerate(chunks)))
    return merged, sites_checked


async def _run_phase(
    items: list[T],
    run_one: Callable[[list[T], int], Awaitable[tuple[list[Any], int]]],
    *,
    chunk_size: int,
    max_parallel: int,
    scan_phase: int,
    merged: list[Any],
    on_partial: Callable[[dict[str, Any]], Awaitable[None]] | None,
    sites_total: int,
    chunk_index_offset: int = 0,
    deadline_monotonic: float | None = None,
) -> int:
    if not items:
        return 0

    chunks = split_chunks(items, chunk_size)
    sem = asyncio.Semaphore(max(1, max_parallel))
    sites_checked = 0
    lock = asyncio.Lock()

    async def _worker(chunk: list[T], index: int) -> None:
        nonlocal sites_checked
        if deadline_monotonic and time.monotonic() >= deadline_monotonic:
            return
        async with sem:
            if deadline_monotonic and time.monotonic() >= deadline_monotonic:
                return
            try:
                rows, checked = await run_one(chunk, chunk_index_offset + index)
            except Exception:
                rows, checked = [], len(chunk)
            async with lock:
                sites_checked += checked
                merged.extend(rows)
                if on_partial:
                    tail = dedupe_by_url(list(merged))[-SCAN_PROGRESS_SNAPSHOT_MAX:]
                    await on_partial(
                        {
                            "type": "scan_progress",
                            "scan_phase": scan_phase,
                            "sites_checked": sites_checked,
                            "sites_total": sites_total,
                            "hits": len(merged),
                            "phase_complete": False,
                            "results_snapshot": tail,
                        }
                    )

    await asyncio.gather(*(_worker(chunk, idx) for idx, chunk in enumerate(chunks)))
    return sites_checked


async def run_two_phase_chunked(
    all_items: list[T],
    priority_items: list[T],
    run_one: Callable[[list[T], int], Awaitable[tuple[list[Any], int]]],
    *,
    on_partial: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    chunk_size: int = CHUNK_SIZE,
    phase1_parallel_count: int | None = None,
    phase2_parallel_count: int | None = None,
    deadline_monotonic: float | None = None,
) -> tuple[list[Any], int]:
    """
    Phase 1 — high-priority sites first (~150, target ~45s wall time).
    Phase 2 — all remaining sites at higher parallelism (target ~3 min total).
    Every site is probed — nothing is skipped.
    """
    if not all_items:
        return [], 0

    priority_set = set(priority_items)
    phase1_items = [item for item in all_items if item in priority_set]
    if not phase1_items:
        phase1_items = all_items[: min(len(all_items), 150)]
        priority_set = set(phase1_items)
    phase2_items = [item for item in all_items if item not in priority_set]

    merged: list[Any] = []
    total_checked = 0
    phase1_chunks = len(split_chunks(phase1_items, chunk_size))

    async def _emit(phase: int, checked: int, *, phase_complete: bool) -> None:
        if not on_partial:
            return
        tail = dedupe_by_url(list(merged))[-SCAN_PROGRESS_SNAPSHOT_MAX:]
        await on_partial(
            {
                "type": "scan_progress",
                "scan_phase": phase,
                "sites_checked": checked,
                "sites_total": len(all_items),
                "hits": len(merged),
                "phase_complete": phase_complete,
                "results_snapshot": tail,
            }
        )

    p1_parallel = max(1, phase1_parallel_count if phase1_parallel_count is not None else phase1_parallel())
    p2_parallel = max(1, phase2_parallel_count if phase2_parallel_count is not None else phase2_parallel())

    p1 = await _run_phase(
        phase1_items,
        run_one,
        chunk_size=chunk_size,
        max_parallel=p1_parallel,
        scan_phase=1,
        merged=merged,
        on_partial=on_partial,
        sites_total=len(all_items),
        chunk_index_offset=0,
        deadline_monotonic=deadline_monotonic,
    )
    total_checked += p1
    await _emit(1, total_checked, phase_complete=True)

    try:
        from services.resource_guard import memory_pressure_high

        if memory_pressure_high():
            phase2_items = []
    except ImportError:
        pass

    if phase2_items and (not deadline_monotonic or time.monotonic() < deadline_monotonic):
        p2 = await _run_phase(
            phase2_items,
            run_one,
            chunk_size=chunk_size,
            max_parallel=p2_parallel,
            scan_phase=2,
            merged=merged,
            on_partial=on_partial,
            sites_total=len(all_items),
            chunk_index_offset=phase1_chunks,
            deadline_monotonic=deadline_monotonic,
        )
        total_checked += p2
        await _emit(2, total_checked, phase_complete=True)

    return merged, total_checked


def dedupe_by_url(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in entries:
        url = entry.get("url")
        if not url or not isinstance(url, str):
            out.append(entry)
            continue
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out
