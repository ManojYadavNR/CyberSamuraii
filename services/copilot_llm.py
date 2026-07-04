"""Qwen 2.5 3B via Ollama — streaming copilot with focused investigation context."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
COPILOT_TIMEOUT = float(os.getenv("COPILOT_TIMEOUT_SEC", "90"))

_semaphore: asyncio.Semaphore | None = None


def copilot_model() -> str:
    return os.getenv("COPILOT_MODEL", "qwen2.5:3b")


def chunk_max_chars() -> int:
    return int(os.getenv("COPILOT_CHUNK_MAX_CHARS", "12000"))


def single_pass_max_chars() -> int:
    return int(os.getenv("COPILOT_SINGLE_PASS_MAX_CHARS", "8000"))


def context_max_chars() -> int:
    return int(os.getenv("COPILOT_CONTEXT_MAX_CHARS", "3500"))


def hard_max_context_chars() -> int:
    """Upper bound when injecting pre-built context into the system prompt."""
    return int(os.getenv("COPILOT_HARD_MAX_CHARS", "12000"))


def map_chunk_pause_sec(*, interactive: bool = False) -> float:
    if interactive:
        return 0.0
    return float(os.getenv("COPILOT_MAP_CHUNK_PAUSE_SEC", "0"))


def prewarm_pause_sec() -> float:
    return float(os.getenv("COPILOT_PREWARM_PAUSE_SEC", "2.0"))


def _enabled() -> bool:
    return os.getenv("COPILOT_ENABLED", "true").lower() in ("1", "true", "yes", "on")


def _concurrency() -> int:
    return max(1, int(os.getenv("COPILOT_MAX_CONCURRENT", "1")))


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_concurrency())
    return _semaphore


def _ollama_options(*, max_tokens: int | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "temperature": float(os.getenv("COPILOT_TEMPERATURE", "0.1")),
        "num_predict": max_tokens or int(os.getenv("COPILOT_MAX_TOKENS", "280")),
        "num_ctx": int(os.getenv("COPILOT_NUM_CTX", "3072")),
    }
    keep_alive = os.getenv("COPILOT_KEEP_ALIVE", "30m")
    if keep_alive:
        opts["keep_alive"] = keep_alive
    threads = os.getenv("COPILOT_NUM_THREADS")
    if threads:
        opts["num_thread"] = int(threads)
    elif (cpu := os.cpu_count()):
        opts["num_thread"] = min(cpu, 8)
    return opts


_HEAVY_MODELS = ("qwen2.5:7b", "qwen2.5:14b", "llama3.1:8b", "mistral:7b")


async def release_heavy_ollama_models() -> None:
    if os.getenv("COPILOT_RELEASE_HEAVY_MODELS", "true").lower() not in ("1", "true", "yes", "on"):
        return
    current = copilot_model()
    to_stop = [m for m in _HEAVY_MODELS if m != current]
    if not to_stop:
        return
    import shutil
    import subprocess

    if not shutil.which("ollama"):
        return

    def _stop() -> None:
        for name in to_stop:
            try:
                subprocess.run(
                    ["ollama", "stop", name],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            except Exception:
                pass

    await asyncio.to_thread(_stop)


SYSTEM_PROMPT = """You are an OSINT investigation copilot. Analyze the investigation data and answer naturally.

RULES:
- Use ONLY the investigation / case data below. Never invent accounts or URLs.
- When scope is "case", the data includes ALL investigations under that case (username, email, phone, image, domain, etc.). Use every investigation, not only the current one.
- When citing findings, mention which investigation query they came from if multiple exist.
- Answer the analyst's question directly — short paragraph or a few bullets.
- No fixed headers (KEY FINDINGS, DETAILS, NOT IN DATA).
- Only real https:// URLs from data — never {username} templates.
- If something was not found (e.g. LinkedIn), say so clearly in the analyst's language.
"""

MAP_SYSTEM_PROMPT = """You extract facts from ONE slice of raw OSINT investigation data.
Rules:
- List EVERY account, URL, name, college, hackathon, post, bio, error, comment, commenter, and count you find.
- Do not summarize away details — include specific handles, domains, titles, and comment text.
- If the chunk is empty or failed, state that explicitly.
- Output compact bullet points grouped by type. No speculation.
"""

REDUCE_SYSTEM_PROMPT = SYSTEM_PROMPT + """
You receive extracted facts from EVERY data chunk of the investigation (full coverage).
Synthesize an answer to the analyst's question using only those facts.
"""



_prewarm_lock = asyncio.Lock()
_prewarm_last_at: float = 0.0
_PREWARM_COOLDOWN_SEC = 1800.0


async def prewarm_copilot_model(*, force: bool = False) -> bool:
    """Load copilot model into memory — call when copilot panel opens."""
    global _prewarm_last_at
    if not _enabled():
        return False
    if not force and time.time() - _prewarm_last_at < _PREWARM_COOLDOWN_SEC:
        return False
    async with _prewarm_lock:
        if not force and time.time() - _prewarm_last_at < _PREWARM_COOLDOWN_SEC:
            return False
        try:
            if not await ollama_available():
                return False
            await _chat_messages(
                [
                    {"role": "system", "content": "Reply ok."},
                    {"role": "user", "content": "ok"},
                ],
                max_tokens=4,
            )
            _prewarm_last_at = time.time()
            return True
        except Exception:
            return False


async def ollama_available() -> bool:
    if not _enabled():
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags")
            if r.status_code != 200:
                return False
            target = copilot_model()
            models = r.json().get("models") or []
            names = [str(m.get("name") or m.get("model") or "") for m in models]
            return any(n == target or n.startswith(f"{target}:") or target in n for n in names)
    except Exception:
        return False


def build_chat_messages(
    user_message: str,
    *,
    context_json: str,
    chat_history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    from services.copilot_language import reply_language_instruction

    limit = hard_max_context_chars()
    lang = reply_language_instruction(user_message)
    system = (
        SYSTEM_PROMPT
        + f"\n\n{lang}"
        + "\n\n--- INVESTIGATION / CASE DATA ---\n"
        + context_json[:limit]
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]


async def _chat_messages(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
) -> str:
    if not _enabled():
        raise RuntimeError("Copilot LLM disabled (COPILOT_ENABLED=false)")

    payload = {
        "model": copilot_model(),
        "messages": messages,
        "stream": False,
        "options": _ollama_options(max_tokens=max_tokens),
    }

    async with _get_semaphore():
        timeout = httpx.Timeout(15.0, read=COPILOT_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{OLLAMA_BASE}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            message = data.get("message") or {}
            text = str(message.get("content") or "").strip()
            if not text:
                raise RuntimeError("Empty response from Ollama")
            return text


async def stream_chat_with_qwen(
    user_message: str,
    *,
    context_json: str,
    chat_history: list[dict[str, str]] | None = None,
) -> AsyncIterator[str]:
    """Stream tokens from Ollama as they are generated (ChatGPT-style)."""
    if not _enabled():
        raise RuntimeError("Copilot LLM disabled (COPILOT_ENABLED=false)")

    messages = build_chat_messages(
        user_message,
        context_json=context_json,
        chat_history=chat_history,
    )
    payload = {
        "model": copilot_model(),
        "messages": messages,
        "stream": True,
        "options": _ollama_options(),
    }

    async with _get_semaphore():
        timeout = httpx.Timeout(15.0, read=COPILOT_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{OLLAMA_BASE}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = str((data.get("message") or {}).get("content") or "")
                    if token:
                        yield token
                    if data.get("done"):
                        break


async def extract_chunk_digest(chunk_label: str, chunk_json: str) -> str:
    messages = [
        {"role": "system", "content": MAP_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Investigation chunk: {chunk_label}\n\n"
                f"{chunk_json[:chunk_max_chars()]}"
            ),
        },
    ]
    return await _chat_messages(messages, max_tokens=int(os.getenv("COPILOT_MAP_MAX_TOKENS", "384")))


async def chat_with_qwen(
    user_message: str,
    *,
    context_json: str,
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    messages = build_chat_messages(user_message, context_json=context_json, chat_history=chat_history)
    return await _chat_messages(messages)


async def synthesize_from_digests(
    user_message: str,
    *,
    query: str,
    index: dict[str, Any],
    digests: dict[str, str],
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    facts_parts: list[str] = []
    for entry in index.get("chunks") or []:
        cid = str(entry.get("chunk_id") or "")
        label = str(entry.get("label") or cid)
        facts = digests.get(cid, "").strip()
        if not facts:
            facts = "(no facts extracted — chunk may be empty or failed)"
        facts_parts.append(f"### {label} [{cid}]\n{facts}")

    limit = single_pass_max_chars()
    batches = _batch_text_parts(facts_parts, max(4000, limit // 2))

    if len(batches) == 1:
        facts_block = batches[0]
    else:
        condensed: list[str] = []
        for i, batch in enumerate(batches, start=1):
            part_summary = await _chat_messages(
                [
                    {"role": "system", "content": MAP_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Consolidate ALL facts from investigation batch {i}/{len(batches)}. "
                            "Do not drop any account, URL, name, or finding.\n\n"
                            f"{batch[:limit]}"
                        ),
                    },
                ],
                max_tokens=int(os.getenv("COPILOT_MAP_MAX_TOKENS", "512")),
            )
            condensed.append(f"## Batch {i}/{len(batches)}\n{part_summary}")
        facts_block = "\n\n".join(condensed)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": REDUCE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Investigation target: {query}\n"
                f"Total chunks analyzed: {index.get('chunk_count', len(digests))} (complete coverage)\n\n"
                f"EXTRACTED FACTS FROM ALL CHUNKS:\n\n{facts_block[:limit]}"
            ),
        },
        {
            "role": "assistant",
            "content": "I have reviewed extracted facts from every investigation chunk.",
        },
    ]
    for turn in (chat_history or [])[-6:]:
        role = str(turn.get("role") or "user")
        content = str(turn.get("content") or "").strip()
        if content and role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return await _chat_messages(messages)


def _batch_text_parts(parts: list[str], max_chars: int) -> list[str]:
    batches: list[str] = []
    current: list[str] = []
    size = 0
    for part in parts:
        part_len = len(part) + 2
        if current and size + part_len > max_chars:
            batches.append("\n\n".join(current))
            current = [part]
            size = part_len
        else:
            current.append(part)
            size += part_len
    if current:
        batches.append("\n\n".join(current))
    return batches or [""]
