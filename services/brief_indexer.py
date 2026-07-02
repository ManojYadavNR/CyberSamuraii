"""Incremental brief indexing during investigation — rule-based first, optional LLM queue."""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
from typing import Any

from services.investigation_brief import (
    empty_brief,
    finalize_brief_from_result,
    merge_brief_tool,
)
from services.json_utils import to_json_safe

logger = logging.getLogger(__name__)

_inv_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("brief_inv_id", default="")
_query_var: contextvars.ContextVar[str] = contextvars.ContextVar("brief_query", default="")

_llm_queues: dict[str, asyncio.Queue[str | None]] = {}
_llm_workers: dict[str, asyncio.Task[None]] = {}


class brief_investigation_scope:
    """Set investigation scope for per-tool brief indexing."""

    def __init__(self, investigation_id: str, query: str) -> None:
        self._investigation_id = investigation_id
        self._query = query
        self._tokens: tuple[Any, Any] | None = None

    def __enter__(self) -> brief_investigation_scope:
        self._tokens = (_inv_id_var.set(self._investigation_id), _query_var.set(self._query))
        self._ensure_pack_stub()
        return self

    def __exit__(self, *args: object) -> None:
        if self._tokens:
            _inv_id_var.reset(self._tokens[0])
            _query_var.reset(self._tokens[1])
        self._stop_llm_worker()

    def _ensure_pack_stub(self) -> None:
        from services.copilot_store import load_copilot_pack, save_copilot_pack

        pack = load_copilot_pack(self._investigation_id)
        if pack and pack.get("investigation_brief"):
            return
        if not pack:
            from services.copilot_context import build_raw_investigation_pack

            pack = build_raw_investigation_pack({}, investigation_id=self._investigation_id, query=self._query)
        pack["investigation_brief"] = empty_brief(
            investigation_id=self._investigation_id,
            query=self._query,
        )
        save_copilot_pack(pack)

    def _stop_llm_worker(self) -> None:
        inv_id = self._investigation_id
        queue = _llm_queues.get(inv_id)
        if queue:
            try:
                queue.put_nowait(None)
            except Exception:
                pass
        task = _llm_workers.pop(inv_id, None)
        if task and not task.done():
            task.cancel()


def on_tool_completed(tool_result: Any, *, query: str = "") -> None:
    """Rule-based brief update when a tool finishes (sync, no Ollama)."""
    inv_id = _inv_id_var.get()
    if not inv_id:
        return

    from schemas.common import ToolResult
    from services.copilot_store import load_copilot_pack, save_copilot_pack

    if isinstance(tool_result, ToolResult):
        tr_dict = to_json_safe(tool_result.model_dump())
    elif isinstance(tool_result, dict):
        tr_dict = to_json_safe(tool_result)
    else:
        return

    pack = load_copilot_pack(inv_id)
    if not pack:
        pack = {
            "investigation_id": inv_id,
            "query": query or _query_var.get(),
            "investigation_brief": empty_brief(investigation_id=inv_id, query=query),
        }

    brief = pack.get("investigation_brief") or empty_brief(investigation_id=inv_id, query=pack.get("query", ""))
    merge_brief_tool(brief, tr_dict)
    pack["investigation_brief"] = brief
    save_copilot_pack(pack)

    if _llm_enrich_enabled():
        _enqueue_llm_tool(inv_id, str(tr_dict.get("tool") or ""))


def finalize_investigation_brief(investigation_id: str, result: dict[str, Any], *, query: str = "") -> None:
    from services.copilot_store import ensure_copilot_pack, load_copilot_pack, save_copilot_pack

    pack = ensure_copilot_pack(investigation_id, result, query=query)
    brief = pack.get("investigation_brief") or empty_brief(investigation_id=investigation_id, query=query)

    # Index any tools not yet seen during incremental hooks
    for tr in result.get("tool_results") or []:
        if isinstance(tr, dict):
            tool = str(tr.get("tool") or "")
            if tool and tool not in brief.get("tools_done", []):
                merge_brief_tool(brief, tr)

    finalize_brief_from_result(brief, result)
    pack["investigation_brief"] = brief
    from services.investigation_brief import brief_to_text

    pack["llm_context_cached"] = brief_to_text(brief)
    save_copilot_pack(pack)
    logger.info("Investigation brief ready: %s tools", len(brief.get("tools_done") or []))


def get_brief(investigation_id: str) -> dict[str, Any] | None:
    from services.copilot_store import load_copilot_pack

    pack = load_copilot_pack(investigation_id)
    if not pack:
        return None
    brief = pack.get("investigation_brief")
    return brief if isinstance(brief, dict) else None


def _llm_enrich_enabled() -> bool:
    return os.getenv("COPILOT_BRIEF_LLM_ENRICH", "false").lower() in ("1", "true", "yes", "on")


def _enqueue_llm_tool(inv_id: str, tool: str) -> None:
    if not tool:
        return
    queue = _llm_queues.get(inv_id)
    if queue is None:
        queue = asyncio.Queue()
        _llm_queues[inv_id] = queue
        try:
            loop = asyncio.get_running_loop()
            _llm_workers[inv_id] = loop.create_task(_llm_worker(inv_id, queue))
        except RuntimeError:
            return
    try:
        queue.put_nowait(tool)
    except Exception:
        pass


async def _llm_worker(inv_id: str, queue: asyncio.Queue[str | None]) -> None:
    pause = float(os.getenv("COPILOT_BRIEF_LLM_PAUSE_SEC", "3.0"))
    while True:
        tool = await queue.get()
        if tool is None:
            break
        try:
            await _enrich_tool_with_llm(inv_id, tool)
        except Exception as exc:
            logger.warning("Brief LLM enrich failed for %s: %r", tool, exc)
        if pause > 0:
            await asyncio.sleep(pause)


async def _enrich_tool_with_llm(inv_id: str, tool: str) -> None:
    from services.copilot_llm import extract_chunk_digest, ollama_available, release_heavy_ollama_models
    from services.copilot_store import load_copilot_pack, save_copilot_pack
    import json

    if not await ollama_available():
        return
    await release_heavy_ollama_models()

    pack = load_copilot_pack(inv_id)
    if not pack:
        return
    brief = pack.get("investigation_brief") or {}
    entry = (brief.get("by_tool") or {}).get(tool)
    if not entry:
        return

    chunk_json = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))[:12000]
    note = await extract_chunk_digest(f"{tool} brief", chunk_json)
    brief.setdefault("llm_notes", {})[tool] = note
    pack["investigation_brief"] = brief
    save_copilot_pack(pack)
