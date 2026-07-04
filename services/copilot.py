"""Investigation copilot — fast Qwen via Ollama with streaming + cached context."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from services.brief_indexer import get_brief
from services.copilot_context import (
    PACK_VERSION,
    build_case_copilot_llm_context,
    build_copilot_llm_context,
    build_raw_investigation_pack,
    get_raw_full,
)
from services.copilot_llm import (
    chat_with_qwen,
    context_max_chars,
    copilot_model,
    ollama_available,
    prewarm_copilot_model,
    stream_chat_with_qwen,
)
from services.copilot_store import (
    append_case_chat_turn,
    append_chat_turn,
    load_case_copilot_pack,
    load_copilot_pack,
)
from services.investigation_brief import brief_to_text

logger = logging.getLogger(__name__)

# In-memory cache — avoids rewriting multi-MB packs to disk on every chat message.
_SESSION_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL_SEC = 3600

_LLM_OFFLINE_MSG = (
    f"Copilot requires {copilot_model()} via Ollama.\n\n"
    f"  ollama pull {copilot_model()}\n  ollama serve\n\n"
    f"Endpoint: {os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')}"
)


def _build_brief_in_memory(raw_full: dict[str, Any], *, query: str = "") -> dict[str, Any]:
    from services.investigation_brief import empty_brief, finalize_brief_from_result, merge_brief_tool

    brief = empty_brief(query=query or str(raw_full.get("query") or ""))
    for tr in raw_full.get("tool_results") or []:
        if isinstance(tr, dict):
            merge_brief_tool(brief, tr)
    finalize_brief_from_result(brief, raw_full)
    return brief


def _case_context_max_chars() -> int:
    return int(os.getenv("COPILOT_CASE_CONTEXT_MAX_CHARS", "8000"))


def _cache_key(*, case_id: str = "", investigation_id: str = "") -> str:
    if case_id:
        return f"case:{case_id}"
    return investigation_id


def invalidate_copilot_cache(*, case_id: str = "", investigation_id: str = "") -> None:
    """Drop cached LLM context so the next chat sees fresh investigations."""
    if case_id:
        _SESSION_CACHE.pop(f"case:{case_id}", None)
    if investigation_id:
        _SESSION_CACHE.pop(investigation_id, None)


def _cache_session(cache_key: str, *, brief: dict[str, Any] | None, llm_context: str) -> None:
    if not cache_key:
        return
    _SESSION_CACHE[cache_key] = {
        "brief": brief,
        "llm_context": llm_context,
        "ts": time.time(),
    }


def _get_cached_session(cache_key: str) -> dict[str, Any] | None:
    if not cache_key:
        return None
    entry = _SESSION_CACHE.get(cache_key)
    if not entry:
        return None
    if time.time() - float(entry.get("ts") or 0) > _CACHE_TTL_SEC:
        _SESSION_CACHE.pop(cache_key, None)
        return None
    return entry


async def _resolve_brief_and_context(
    investigation_id: str,
    raw_full: dict[str, Any],
    *,
    query: str,
    message: str,
    pack: dict[str, Any] | None,
    case_id: str = "",
    current_result: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    cache_key = _cache_key(case_id=case_id, investigation_id=investigation_id)
    limit = _case_context_max_chars() if case_id else context_max_chars()
    cached = _get_cached_session(cache_key)
    if cached:
        brief = cached.get("brief")
        ctx = str(cached.get("llm_context") or "")
        if ctx:
            return (brief if isinstance(brief, dict) else None), ctx[:limit]

    brief: dict[str, Any] | None = None
    if pack:
        brief = pack.get("investigation_brief")
    if not brief and investigation_id:
        brief = get_brief(investigation_id)
    if not brief and raw_full:
        brief = await asyncio.to_thread(_build_brief_in_memory, raw_full, query=query)

    if case_id:
        llm_ctx = await asyncio.to_thread(
            build_case_copilot_llm_context,
            case_id,
            current_investigation_id=investigation_id,
            current_result=current_result or raw_full,
            current_query=query,
            max_chars=limit,
        )
    else:
        llm_ctx = await asyncio.to_thread(build_copilot_llm_context, raw_full, max_chars=limit)

    _cache_session(cache_key, brief=brief if isinstance(brief, dict) else None, llm_context=llm_ctx)
    return brief, llm_ctx


async def _prepare_llm_session(
    message: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    investigation_id = str(context.get("investigation_id") or "")
    case_id = str(context.get("case_id") or "")
    result = context.get("result") or {}
    query = str(context.get("query") or result.get("query") or "")

    pack = load_copilot_pack(investigation_id) if investigation_id else None
    raw_full = get_raw_full(pack) if pack else result
    if not raw_full:
        raw_full = result

    # Case scope can answer from sibling investigations even if current result is empty.
    if not raw_full and not result and not case_id:
        return {"error": "no_data", "answer": "No investigation data available. Complete an investigation first."}

    if case_id and not raw_full and not result:
        # Still allow case-wide chat when only case_id is known.
        pass

    asyncio.create_task(prewarm_copilot_model(force=True))

    online_task = asyncio.create_task(ollama_available())
    context_task = asyncio.create_task(
        _resolve_brief_and_context(
            investigation_id,
            raw_full or result,
            query=query,
            message=message,
            pack=pack,
            case_id=case_id,
            current_result=result if isinstance(result, dict) else None,
        )
    )
    online, (brief, context_json) = await asyncio.gather(online_task, context_task)
    if not online:
        return {
            "error": "offline",
            "answer": _LLM_OFFLINE_MSG,
            "investigation_id": investigation_id,
            "case_id": case_id,
        }

    if case_id:
        case_pack = load_case_copilot_pack(case_id) or {}
        history = list(case_pack.get("chat_history") or [])
    else:
        history = list((pack or {}).get("chat_history") or [])

    if not context_json or context_json in ("{}", "null"):
        return {
            "error": "no_data",
            "answer": "No investigation data available for this case yet. Run at least one investigation.",
            "investigation_id": investigation_id,
            "case_id": case_id,
        }

    return {
        "investigation_id": investigation_id,
        "case_id": case_id,
        "query": query,
        "pack": pack,
        "brief": brief,
        "context_json": context_json,
        "history": history,
        "scope": "case" if case_id else "investigation",
    }


def _persist_chat_turn(session: dict[str, Any], role: str, content: str) -> None:
    case_id = str(session.get("case_id") or "")
    investigation_id = str(session.get("investigation_id") or "")
    if case_id:
        asyncio.create_task(asyncio.to_thread(append_case_chat_turn, case_id, role, content))
    elif investigation_id:
        asyncio.create_task(asyncio.to_thread(append_chat_turn, investigation_id, role, content))


async def answer_copilot_async(message: str, context: dict[str, Any]) -> dict[str, Any]:
    session = await _prepare_llm_session(message, context)

    if session.get("error") == "no_data":
        return {"answer": session["answer"], "data": {}, "engine": "none"}

    if session.get("error") == "offline":
        return {
            "answer": session["answer"],
            "data": {"investigation_id": session.get("investigation_id")},
            "engine": "offline",
        }

    investigation_id = session.get("investigation_id", "")
    case_id = session.get("case_id", "")
    try:
        answer = await chat_with_qwen(
            message,
            context_json=session["context_json"],
            chat_history=session["history"],
        )
    except Exception as exc:
        logger.warning("Copilot LLM failed: %r", exc)
        return {
            "answer": f"Copilot LLM request failed: {exc!r}\n\n{_LLM_OFFLINE_MSG}",
            "data": {"investigation_id": investigation_id, "case_id": case_id, "error": repr(exc)},
            "engine": "error",
        }

    _persist_chat_turn(session, "user", message)
    _persist_chat_turn(session, "assistant", answer)

    brief = session.get("brief")
    return {
        "answer": answer,
        "data": {
            "investigation_id": investigation_id,
            "case_id": case_id,
            "scope": session.get("scope") or "investigation",
            "model": copilot_model(),
            "mode": "llm",
            "brief_status": brief.get("status") if isinstance(brief, dict) else None,
            "pack_version": (session.get("pack") or {}).get("pack_version", PACK_VERSION),
        },
        "engine": "qwen",
    }


async def stream_copilot_events(message: str, context: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE events: status, token chunks, done, or error."""
    yield {"status": "thinking"}

    session = await _prepare_llm_session(message, context)

    if session.get("error"):
        yield {"error": session["answer"], "engine": session.get("error")}
        yield {"done": True, "answer": session["answer"]}
        return

    parts: list[str] = []

    try:
        async for token in stream_chat_with_qwen(
            message,
            context_json=session["context_json"],
            chat_history=session["history"],
        ):
            parts.append(token)
            yield {"token": token}

        answer = "".join(parts).strip()
        if not answer:
            raise RuntimeError("Empty response from Ollama stream")

        _persist_chat_turn(session, "user", message)
        _persist_chat_turn(session, "assistant", answer)

        brief = session.get("brief")
        yield {
            "done": True,
            "answer": answer,
            "engine": "qwen",
            "mode": "llm_stream",
            "model": copilot_model(),
            "scope": session.get("scope") or "investigation",
            "case_id": session.get("case_id") or "",
            "brief_status": brief.get("status") if isinstance(brief, dict) else None,
        }
    except Exception as exc:
        logger.warning("Copilot stream failed: %r — trying non-stream fallback", exc)
        try:
            answer = await chat_with_qwen(
                message,
                context_json=session["context_json"],
                chat_history=session["history"],
            )
            if parts:
                answer = "".join(parts) + answer
            _persist_chat_turn(session, "user", message)
            _persist_chat_turn(session, "assistant", answer)
            yield {"token": answer[len("".join(parts)):] if parts else answer}
            yield {
                "done": True,
                "answer": answer,
                "engine": "qwen",
                "mode": "llm_fallback",
                "scope": session.get("scope") or "investigation",
            }
        except Exception as exc2:
            logger.warning("Copilot fallback also failed: %r", exc2)
            partial = "".join(parts).strip()
            yield {
                "error": str(exc2),
                "engine": "error",
                "done": True,
                "answer": partial or f"Copilot failed: {exc2}",
            }


def answer_copilot(message: str, context: dict[str, Any]) -> dict[str, Any]:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, answer_copilot_async(message, context))
                return future.result(timeout=120)
    except RuntimeError:
        pass
    return asyncio.run(answer_copilot_async(message, context))


def build_copilot_pack_from_result(
    investigation_id: str,
    result: dict[str, Any],
    *,
    query: str = "",
) -> dict[str, Any]:
    from services.brief_indexer import finalize_investigation_brief
    from services.copilot_store import ensure_copilot_pack, load_copilot_pack, save_copilot_pack

    ensure_copilot_pack(investigation_id, result, query=query)
    finalize_investigation_brief(investigation_id, result, query=query)

    pack = load_copilot_pack(investigation_id) or {}
    brief = pack.get("investigation_brief")
    if isinstance(brief, dict):
        llm_ctx = build_copilot_llm_context(result, max_chars=context_max_chars())
        pack["llm_context_cached"] = llm_ctx
        _cache_session(investigation_id, brief=brief, llm_context=llm_ctx)
        save_copilot_pack(pack)

    return pack


def schedule_copilot_pack_build(
    investigation_id: str,
    result: dict[str, Any],
    *,
    query: str = "",
) -> None:
    async def _run() -> None:
        await asyncio.to_thread(build_copilot_pack_from_result, investigation_id, result, query=query)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        build_copilot_pack_from_result(investigation_id, result, query=query)


def warm_session_from_result(investigation_id: str, result: dict[str, Any], *, query: str = "") -> None:
    """Pre-cache brief + LLM context when investigation completes (no disk wait on first chat)."""
    if not investigation_id or not result:
        return
    try:
        brief = _build_brief_in_memory(result, query=query)
        llm_ctx = build_copilot_llm_context(result, max_chars=context_max_chars())
        _cache_session(investigation_id, brief=brief, llm_context=llm_ctx)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(prewarm_copilot_model(force=True))
        except RuntimeError:
            pass
    except Exception as exc:
        logger.warning("Copilot session warm failed: %r", exc)
