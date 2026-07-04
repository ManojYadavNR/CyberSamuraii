"""Investigation copilot LLM — Ollama (Qwen), xAI Grok, or Google Gemini."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
XAI_BASE = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
GEMINI_BASE = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
COPILOT_TIMEOUT = float(os.getenv("COPILOT_TIMEOUT_SEC", "90"))
XAI_TIMEOUT = float(os.getenv("XAI_TIMEOUT_SEC", "120"))
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT_SEC", "120"))

_semaphore: asyncio.Semaphore | None = None


def copilot_provider() -> str:
    raw = os.getenv("COPILOT_PROVIDER", "ollama").strip().lower()
    if raw in ("xai", "grok"):
        return "xai"
    if raw in ("gemini", "google"):
        return "gemini"
    return "ollama"


def copilot_engine_name() -> str:
    provider = copilot_provider()
    if provider == "xai":
        return "grok"
    if provider == "gemini":
        return "gemini"
    return "qwen"


def copilot_model() -> str:
    provider = copilot_provider()
    if provider == "xai":
        return os.getenv("XAI_MODEL", "grok-4.3")
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    return os.getenv("COPILOT_MODEL", "qwen2.5:3b")


def gemini_api_key() -> str:
    return (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )


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


SYSTEM_PROMPT = """You are an OSINT investigation copilot with FULL CASE ACCESS when scope is "case".

The JSON includes **every investigation** linked to the case in the `investigations` array.
Each investigation has: investigation_id, query, tools_run, verified_findings, research_intel.

DATA LAYERS:
1. **verified_findings** — cross-checked accounts (Samurai live scrape, corroborated tools).
2. **research_intel** per investigation — google_dork_hits, google_search_intel (colleges, hackathons, GitHub, employment), Samurai reels/captions/links.

HOW TO ANSWER:
- Use ALL investigations — not only the latest run. Same target may appear in multiple runs; merge and dedupe in your answer.
- Cite which **query** and **investigation_id** when findings differ between runs.
- Label: "Verified:" vs "Research/dorking:" vs "From reel caption:".
- For colleges, GitHub, hackathons, web hits — use google_dork_hits and google_search_intel from any investigation.
- Never invent data outside the JSON. Scanner-only enumeration was excluded from verified but dork hits are in research_intel.

RULES:
- Short, detailed answers with URLs, titles, snippets from the data.
- Only real https:// URLs from the JSON.
"""

MAP_SYSTEM_PROMPT = """You extract facts from ONE slice of raw OSINT investigation data.
Rules:
- List accounts, URLs, names, posts, bios, errors, and counts you find.
- Mark each item's trust level: confirmed, corroborated (2+ tools), single-source lead, or tool error.
- Note tool failures, warnings, and contradictions explicitly.
- Do not treat scanner hits as verified identity.
- Output compact bullet points grouped by trust level. No speculation beyond what the data supports.
"""

REDUCE_SYSTEM_PROMPT = SYSTEM_PROMPT + """
You receive extracted facts from EVERY data chunk of the investigation (full coverage).
Synthesize an answer to the analyst's question using only those facts.
"""



_prewarm_lock = asyncio.Lock()
_prewarm_last_at: float = 0.0
_PREWARM_COOLDOWN_SEC = 1800.0


async def prewarm_copilot_model(*, force: bool = False) -> bool:
    """Load copilot model into memory — Ollama only."""
    global _prewarm_last_at
    provider = copilot_provider()
    if not _enabled() or provider in ("xai", "gemini"):
        if provider == "xai":
            return xai_configured()
        if provider == "gemini":
            return gemini_configured()
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
    if not _enabled() or copilot_provider() != "ollama":
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


def xai_configured() -> bool:
    return bool(os.getenv("XAI_API_KEY", "").strip())


async def xai_available() -> bool:
    if not _enabled() or copilot_provider() != "xai":
        return False
    return xai_configured()


def gemini_configured() -> bool:
    return bool(gemini_api_key())


async def gemini_available() -> bool:
    if not _enabled() or copilot_provider() != "gemini":
        return False
    return gemini_configured()


async def llm_available() -> bool:
    provider = copilot_provider()
    if provider == "xai":
        return await xai_available()
    if provider == "gemini":
        return await gemini_available()
    return await ollama_available()


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
        + "\n\n--- VERIFIED + RESEARCH INTELLIGENCE ---\n"
        + context_json[:limit]
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]


async def _chat_messages_xai(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
) -> str:
    api_key = os.getenv("XAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not configured. Add it to .env and restart the backend.")

    payload = {
        "model": copilot_model(),
        "messages": messages,
        "stream": False,
        "temperature": float(os.getenv("COPILOT_TEMPERATURE", "0.1")),
        "max_tokens": max_tokens or int(os.getenv("COPILOT_MAX_TOKENS", "280")),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with _get_semaphore():
        timeout = httpx.Timeout(15.0, read=XAI_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{XAI_BASE}/chat/completions", json=payload, headers=headers)
            if response.status_code >= 400:
                detail = response.text[:400]
                try:
                    err = response.json().get("error") or response.json().get("message")
                    if err:
                        detail = str(err)
                except Exception:
                    pass
                raise RuntimeError(f"xAI Grok error ({response.status_code}): {detail}")
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("Empty response from xAI Grok")
            text = str((choices[0].get("message") or {}).get("content") or "").strip()
            if not text:
                raise RuntimeError("Empty response from xAI Grok")
            return text


async def _stream_chat_messages_xai(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    api_key = os.getenv("XAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not configured. Add it to .env and restart the backend.")

    payload = {
        "model": copilot_model(),
        "messages": messages,
        "stream": True,
        "temperature": float(os.getenv("COPILOT_TEMPERATURE", "0.1")),
        "max_tokens": int(os.getenv("COPILOT_MAX_TOKENS", "280")),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with _get_semaphore():
        timeout = httpx.Timeout(15.0, read=XAI_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{XAI_BASE}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if not chunk or chunk == "[DONE]":
                        if chunk == "[DONE]":
                            break
                        continue
                    try:
                        data = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    token = str(delta.get("content") or "")
                    if token:
                        yield token


def _messages_to_gemini(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        text = str(msg.get("content") or "").strip()
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})
        else:
            contents.append({"role": "user", "parts": [{"text": text}]})
    if not contents:
        contents.append({"role": "user", "parts": [{"text": "Hello"}]})
    return "\n\n".join(system_parts), contents


def _gemini_generation_config(*, max_tokens: int | None = None) -> dict[str, Any]:
    return {
        "temperature": float(os.getenv("COPILOT_TEMPERATURE", "0.1")),
        "maxOutputTokens": max_tokens or int(os.getenv("COPILOT_MAX_TOKENS", "512")),
    }


def _gemini_error_detail(response: httpx.Response) -> str:
    detail = response.text[:400]
    try:
        err = response.json().get("error") or {}
        message = err.get("message") or err
        if message:
            return str(message)
    except Exception:
        pass
    return detail


def _extract_gemini_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()


def _gemini_text_from_response(data: dict[str, Any]) -> str:
    text = _extract_gemini_text(data)
    if not text:
        raise RuntimeError("Empty response from Gemini")
    return text


async def _chat_messages_gemini(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
) -> str:
    api_key = gemini_api_key()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Add it to .env and restart the backend."
        )

    system_instruction, contents = _messages_to_gemini(messages)
    model = copilot_model()
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": _gemini_generation_config(max_tokens=max_tokens),
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    async with _get_semaphore():
        timeout = httpx.Timeout(15.0, read=GEMINI_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, params={"key": api_key}, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Gemini error ({response.status_code}): {_gemini_error_detail(response)}"
                )
            return _gemini_text_from_response(response.json())


async def _stream_chat_messages_gemini(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    api_key = gemini_api_key()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Add it to .env and restart the backend."
        )

    system_instruction, contents = _messages_to_gemini(messages)
    model = copilot_model()
    url = f"{GEMINI_BASE}/models/{model}:streamGenerateContent"
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": _gemini_generation_config(),
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    async with _get_semaphore():
        timeout = httpx.Timeout(15.0, read=GEMINI_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                url,
                params={"key": api_key, "alt": "sse"},
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode("utf-8", errors="replace")[:400]
                    try:
                        err = json.loads(body).get("error") or {}
                        detail = str(err.get("message") or detail)
                    except Exception:
                        pass
                    raise RuntimeError(f"Gemini error ({response.status_code}): {detail}")

                emitted = ""
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if not chunk or chunk == "[DONE]":
                        continue
                    try:
                        data = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    text = _extract_gemini_text(data)
                    if not text:
                        continue
                    if text.startswith(emitted):
                        delta = text[len(emitted):]
                        emitted = text
                    else:
                        delta = text
                        emitted += text
                    if delta:
                        yield delta


async def _chat_messages(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
) -> str:
    if not _enabled():
        raise RuntimeError("Copilot LLM disabled (COPILOT_ENABLED=false)")

    if copilot_provider() == "xai":
        return await _chat_messages_xai(messages, max_tokens=max_tokens)
    if copilot_provider() == "gemini":
        return await _chat_messages_gemini(messages, max_tokens=max_tokens)

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

    if copilot_provider() == "xai":
        async for token in _stream_chat_messages_xai(messages):
            yield token
        return
    if copilot_provider() == "gemini":
        async for token in _stream_chat_messages_gemini(messages):
            yield token
        return

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
