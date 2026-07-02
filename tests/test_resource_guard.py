import asyncio

import pytest

from services.resource_guard import (
    DUAL_EMAIL_TOOL_CONCURRENCY,
    DUAL_USERNAME_TOOL_CONCURRENCY,
    GLOBAL_TOOL_SUBPROCESS_CAP,
    InvestigationBusyError,
    dual_identity_scan,
    effective_tool_concurrency,
    investigation_slot,
    tool_subprocess_slot,
)


@pytest.mark.asyncio
async def test_investigation_slot_serializes_runs():
    order: list[str] = []

    async def worker(name: str) -> None:
        async with investigation_slot():
            order.append(f"{name}_start")
            await asyncio.sleep(0.05)
            order.append(f"{name}_end")

    await asyncio.gather(worker("a"), worker("b"))
    assert order.index("a_start") < order.index("a_end")
    assert order.index("b_start") < order.index("b_end")
    # Second worker must not overlap the first when MAX_CONCURRENT_INVESTIGATIONS=1
    assert not (order.index("a_end") > order.index("b_start") and order.index("b_end") > order.index("a_start"))


@pytest.mark.asyncio
async def test_second_investigation_raises_busy():
    started = asyncio.Event()
    release = asyncio.Event()

    async def hold_slot() -> None:
        async with investigation_slot():
            started.set()
            await release.wait()

    holder = asyncio.create_task(hold_slot())
    await started.wait()

    with pytest.raises(InvestigationBusyError):
        async with investigation_slot():
            pass

    release.set()
    await holder


@pytest.mark.asyncio
async def test_tool_subprocess_cap_limits_parallel_tasks():
    running = 0
    peak = 0

    async def task() -> None:
        nonlocal running, peak
        async with tool_subprocess_slot():
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.05)
            running -= 1

    await asyncio.gather(*[task() for _ in range(GLOBAL_TOOL_SUBPROCESS_CAP + 4)])
    assert peak <= GLOBAL_TOOL_SUBPROCESS_CAP


def test_effective_tool_concurrency_clamps():
    assert effective_tool_concurrency("username_search", 12) <= GLOBAL_TOOL_SUBPROCESS_CAP


@pytest.mark.asyncio
async def test_dual_mode_uses_lower_concurrency():
    async with dual_identity_scan():
        assert effective_tool_concurrency("username_search", 12) == DUAL_USERNAME_TOOL_CONCURRENCY
        assert effective_tool_concurrency("email_intel", 8) == DUAL_EMAIL_TOOL_CONCURRENCY
