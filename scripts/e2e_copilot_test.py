#!/usr/bin/env python3
"""E2E: investigate manojyadavnr → stored raw pack → copilot Q&A → verify."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

BASE = "http://127.0.0.1:8000"
QUERY = "manojyadavnr"
ADMIN_USER = "admin"
ADMIN_PASS = "Socmint@CID2026!Admin"
COPILOT_DIR = Path("data/copilot")


def login(client: httpx.Client) -> str:
    r = client.post(f"{BASE}/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    r.raise_for_status()
    return r.json()["access_token"]


def create_case(client: httpx.Client, headers: dict) -> str:
    r = client.post(
        f"{BASE}/api/enterprise/cases",
        headers=headers,
        json={"title": f"Copilot E2E — {QUERY}", "description": "Raw data copilot verification", "priority": "MEDIUM"},
    )
    r.raise_for_status()
    return r.json()["case_id"]


def run_investigation(client: httpx.Client, headers: dict, case_id: str) -> dict[str, Any]:
    print(f"\n=== Investigation: '{QUERY}' (standard, discovery off) ===")
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/dashboard/investigate",
        headers=headers,
        json={
            "query": QUERY,
            "query_type": "username",
            "investigation_mode": "standard",
            "case_id": case_id,
            "discovery": {"enabled": False, "max_depth": 1, "max_hops": 0, "max_leads_per_hop": 1, "max_total_leads": 1},
            "timeout_per_tool": 180.0,
        },
        timeout=600.0,
    )
    r.raise_for_status()
    data = r.json()
    print(f"Done in {time.time() - t0:.0f}s | id={data.get('investigation_id')}")
    return data


def wait_for_stored_pack(investigation_id: str, timeout_sec: float = 120.0) -> dict[str, Any]:
    path = COPILOT_DIR / f"{investigation_id}.json"
    print(f"\n=== Waiting for stored copilot pack: {path} ===")
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        if path.is_file():
            pack = json.loads(path.read_text())
            raw = pack.get("raw_full") or pack.get("raw") or {}
            if raw.get("tool_results"):
                digests = pack.get("chunk_digests") or {}
                total_chunks = len(digests)
                print(f"Pack ready | tools={len(raw.get('tool_results', []))} | digests_cached={total_chunks}")
                return pack
        time.sleep(2)
    raise TimeoutError(f"Copilot pack not ready after {timeout_sec}s")


def extract_ground_truth(result: dict[str, Any]) -> dict[str, Any]:
    ground: dict[str, Any] = {
        "query": result.get("query"),
        "tools_ok": [],
        "tools_fail": [],
        "keywords": set(),
        "urls": set(),
        "platforms": set(),
    }
    for tr in result.get("tool_results", []):
        tool = str(tr.get("tool") or "")
        if tr.get("success"):
            ground["tools_ok"].append(tool)
        else:
            ground["tools_fail"].append(tool)
        blob = json.dumps(tr, ensure_ascii=False).lower()
        if "instagram" in blob:
            ground["platforms"].add("instagram")
        if "facebook" in blob:
            ground["platforms"].add("facebook")
        if "github" in blob:
            ground["platforms"].add("github")
        for token in (QUERY, "manoj", "yadav", "hackathon", "college", "cambridge"):
            if token in blob:
                ground["keywords"].add(token)

    evidence = result.get("evidence_extraction") or {}
    for block in (evidence.get("google_search_intel"), evidence.get("samurai_social_intel")):
        if block:
            text = json.dumps(block, ensure_ascii=False).lower()
            for token in ("hackathon", "college", "cambridge", "instagram", "facebook"):
                if token in text:
                    ground["keywords"].add(token)

    return ground


def ask_copilot(client: httpx.Client, headers: dict, investigation_id: str, message: str) -> dict[str, Any]:
    print(f"\n--- Q: {message}")
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/dashboard/copilot",
        headers=headers,
        json={"investigation_id": investigation_id, "message": message, "context": {}},
        timeout=600.0,
    )
    r.raise_for_status()
    data = r.json()
    meta = data.get("data") or {}
    print(f"Engine={data.get('engine')} model={meta.get('model')} mode={meta.get('mode')} chunks={meta.get('chunks')} ({time.time()-t0:.0f}s)")
    print(f"A: {data.get('answer', '')[:1500]}")
    return data


def verify(answer: str, ground: dict[str, Any], checks: list[str]) -> list[str]:
    fails: list[str] = []
    lower = answer.lower()
    if QUERY.lower() not in lower and "manoj" not in lower:
        fails.append(f"Answer does not mention target '{QUERY}'")
    for c in checks:
        if c.lower() not in lower:
            fails.append(f"Missing expected term: {c}")
    if ground["tools_ok"] and data_looks_empty(lower):
        fails.append("Answer claims no data but tools succeeded")
    return fails


def data_looks_empty(text: str) -> bool:
    return any(p in text for p in ("no data", "no investigation", "not available", "no information"))


def main() -> int:
    with httpx.Client() as client:
        for _ in range(30):
            try:
                client.get(f"{BASE}/api/auth/login", timeout=2.0)
                break
            except Exception:
                time.sleep(1)
        else:
            print("FAIL: backend not reachable on :8000")
            return 1

        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        case_id = create_case(client, headers)
        inv = run_investigation(client, headers, case_id)
        investigation_id = inv["investigation_id"]
        result = inv.get("result") or {}
        ground = extract_ground_truth(result)

        print("\n=== Ground truth from tool results ===")
        print(f"Tools OK ({len(ground['tools_ok'])}): {', '.join(ground['tools_ok'][:12])}")
        print(f"Keywords in raw data: {sorted(ground['keywords'])}")
        print(f"Platforms in raw data: {sorted(ground['platforms'])}")

        pack = wait_for_stored_pack(investigation_id)
        raw_tools = (pack.get("raw_full") or {}).get("tool_results") or []
        print(f"Stored pack verification: {len(raw_tools)} tool_results in data/copilot/{investigation_id}.json")

        # Let background prewarm digest a few chunks (optional, reduces first-question lag)
        print("\nWaiting 15s for background digest prewarm...")
        time.sleep(15)

        questions = [
            ("What platforms and accounts were found for manojyadavnr? Which tools reported them?", [QUERY]),
            ("What colleges, schools, or hackathons appear in the Google dorking or search data?", ["hackathon" if "hackathon" in ground["keywords"] else "google"]),
            ("What did Samurai find on Instagram or Facebook — bio, posts, or profile info?", ["instagram" if "instagram" in ground["platforms"] else "samurai"]),
        ]

        all_fails: list[str] = []
        for q, checks in questions:
            resp = ask_copilot(client, headers, investigation_id, q)
            if resp.get("engine") not in ("qwen",):
                all_fails.append(f"Copilot engine={resp.get('engine')} — {resp.get('answer', '')[:200]}")
                continue
            all_fails.extend(verify(resp.get("answer", ""), ground, checks))

        print("\n" + "=" * 60)
        if all_fails:
            print("VERDICT: ISSUES FOUND")
            for f in all_fails:
                print(f"  ✗ {f}")
            return 1
        print("VERDICT: PASS")
        print("  ✓ Investigation completed and raw pack stored")
        print("  ✓ Copilot answered via qwen2.5:3b using stored investigation data")
        print("  ✓ Answers reference target and tool findings")
        return 0


if __name__ == "__main__":
    sys.exit(main())
