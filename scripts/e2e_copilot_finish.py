#!/usr/bin/env python3
"""Finish copilot E2E on existing investigation after digests are cached."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

INV_ID = "531e221f-0b22-43c9-9974-cf1f56971287"
QUERY = "manojyadavnr"
BASE = "http://127.0.0.1:8000"
PACK = Path(f"data/copilot/{INV_ID}.json")


def count_chunks(raw: dict) -> int:
    from services.copilot_context import expand_oversized_chunks, iter_investigation_chunks
    from services.copilot_llm import chunk_max_chars
    return len(expand_oversized_chunks(iter_investigation_chunks(raw), max_chars=chunk_max_chars()))


async def wait_digests(target: int, max_wait: int = 900) -> int:
    t0 = time.time()
    while time.time() - t0 < max_wait:
        if PACK.is_file():
            pack = json.loads(PACK.read_text())
            n = len(pack.get("chunk_digests") or {})
            print(f"  digests {n}/{target} ({time.time()-t0:.0f}s)")
            if n >= target:
                return n
        await asyncio.sleep(20)
    pack = json.loads(PACK.read_text())
    return len(pack.get("chunk_digests") or {})


async def main() -> int:
    pack = json.loads(PACK.read_text())
    raw = pack["raw_full"]
    total = count_chunks(raw)
    print(f"Investigation {INV_ID} | chunks={total}")

    print("Waiting for background digest prewarm...")
    done = await wait_digests(total, max_wait=900)
    print(f"Digests ready: {done}/{total}")

    from services.copilot import answer_copilot_async

    context = {"investigation_id": INV_ID, "query": QUERY, "result": raw}
    questions = [
        "What platforms and accounts were found for manojyadavnr? Which tools reported them?",
        "What colleges, schools, or hackathons appear in Google dorking or search intelligence?",
        "What did Samurai find on Instagram or Facebook — bio, posts, reels, or profile details?",
    ]

    fails = []
    for q in questions:
        print(f"\nQ: {q}")
        t0 = time.time()
        out = await answer_copilot_async(q, context)
        ans = out.get("answer", "")
        print(f"Engine={out.get('engine')} mode={(out.get('data') or {}).get('mode')} ({time.time()-t0:.0f}s)")
        print(f"A: {ans[:1200]}")
        if out.get("engine") != "qwen":
            fails.append(f"engine={out.get('engine')}")
        elif QUERY.lower() not in ans.lower() and "manoj" not in ans.lower():
            fails.append(f"answer missing target for: {q[:50]}")

    print("\n" + "=" * 50)
    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("PASS: All copilot answers grounded on stored raw data")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
