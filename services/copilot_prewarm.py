"""Gradual background digest pre-warming — spreads LLM load after investigation."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from services.copilot_context import (
    build_investigation_index,
    chunk_to_json,
    expand_oversized_chunks,
    get_raw_full,
    iter_investigation_chunks,
)
from services.copilot_llm import (
    chunk_max_chars,
    extract_chunk_digest,
    map_chunk_pause_sec,
    prewarm_pause_sec,
    release_heavy_ollama_models,
)
from services.copilot_store import load_copilot_pack, update_chunk_digests

logger = logging.getLogger(__name__)

_prewarm_tasks: dict[str, asyncio.Task[None]] = {}


def prewarm_enabled() -> bool:
    return os.getenv("COPILOT_PREWARM_DIGESTS", "false").lower() in ("1", "true", "yes", "on")


async def prewarm_digests_gradually(investigation_id: str) -> None:
    """Digest one chunk at a time in the background so the first chat is fast."""
    if not prewarm_enabled():
        return

    pack = load_copilot_pack(investigation_id)
    if not pack:
        return

    raw_full = get_raw_full(pack)
    if not raw_full:
        return

    await release_heavy_ollama_models()

    base = iter_investigation_chunks(raw_full)
    chunks = expand_oversized_chunks(base, max_chars=chunk_max_chars())
    digests: dict[str, str] = dict(pack.get("chunk_digests") or {})
    pending = [c for c in chunks if c["chunk_id"] not in digests]
    if not pending:
        return

    pause = prewarm_pause_sec()
    logger.info("Copilot prewarm: %d chunks for %s", len(pending), investigation_id)

    for chunk in pending:
        if investigation_id in _prewarm_tasks and _prewarm_tasks[investigation_id].cancelled():
            return
        fresh = load_copilot_pack(investigation_id)
        if fresh and chunk["chunk_id"] in (fresh.get("chunk_digests") or {}):
            continue
        try:
            digest = await extract_chunk_digest(chunk["label"], chunk_to_json(chunk))
            update_chunk_digests(investigation_id, {chunk["chunk_id"]: digest})
        except Exception as exc:
            logger.warning("Prewarm digest failed %s: %s", chunk["chunk_id"], exc)
            update_chunk_digests(investigation_id, {chunk["chunk_id"]: f"(prewarm failed: {exc})"})
        if pause > 0:
            await asyncio.sleep(pause)


def cancel_prewarm(investigation_id: str) -> None:
    """Stop background digest work when user opens copilot — interactive path is faster."""
    task = _prewarm_tasks.pop(investigation_id, None)
    if task and not task.done():
        task.cancel()


def schedule_copilot_prewarm(investigation_id: str) -> None:
    """Fire-and-forget gradual digest build after investigation (laptop-safe)."""
    if not prewarm_enabled() or not investigation_id:
        return

    async def _run() -> None:
        await asyncio.sleep(float(os.getenv("COPILOT_PREWARM_START_DELAY_SEC", "3")))
        try:
            await prewarm_digests_gradually(investigation_id)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Copilot prewarm ended with error: %s", exc)
        finally:
            _prewarm_tasks.pop(investigation_id, None)

    try:
        loop = asyncio.get_running_loop()
        old = _prewarm_tasks.pop(investigation_id, None)
        if old and not old.done():
            old.cancel()
        _prewarm_tasks[investigation_id] = loop.create_task(_run())
    except RuntimeError:
        asyncio.run(prewarm_digests_gradually(investigation_id))


def prewarm_status(investigation_id: str) -> dict[str, Any]:
    pack = load_copilot_pack(investigation_id)
    if not pack:
        return {"ready": False, "digested": 0, "total": 0}
    raw = get_raw_full(pack)
    chunks = expand_oversized_chunks(
        iter_investigation_chunks(raw),
        max_chars=chunk_max_chars(),
    )
    digests = pack.get("chunk_digests") or {}
    total = len(chunks)
    done = sum(1 for c in chunks if c["chunk_id"] in digests)
    task = _prewarm_tasks.get(investigation_id)
    return {
        "ready": done >= total and total > 0,
        "digested": done,
        "total": total,
        "prewarming": bool(task and not task.done()),
    }
