#!/usr/bin/env python3
"""Smoke-test WebSocket investigate handshake for all three speed modes."""

from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import websockets

API = os.getenv("SMOKE_API", "http://127.0.0.1:8000")
WS = API.replace("http://", "ws://").replace("https://", "wss://") + "/ws/investigate"
USER = os.getenv("SMOKE_USER", "admin")
PASS = os.getenv("SMOKE_PASS", "Socmint@CID2026!Admin")


async def login() -> tuple[str, str | None]:
    import urllib.request

    req = urllib.request.Request(
        f"{API}/api/auth/login",
        data=json.dumps({"username": USER, "password": PASS}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return data["access_token"], data.get("active_case_id")


async def fetch_case_id(token: str) -> str | None:
    import urllib.request

    req = urllib.request.Request(
        f"{API}/api/enterprise/cases",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if isinstance(data, list):
            return data[0]["case_id"] if data else None
        cases = data.get("cases") or []
        return cases[0]["case_id"] if cases else None
    except Exception:
        return None


async def probe_mode(mode: str, token: str, case_id: str | None) -> dict:
    payload = {
        "query": "smoke_test_user | smoke@example.com",
        "timeout_per_tool": 30,
        "investigation_mode": mode,
        "discovery": {
            "enabled": mode != "fast",
            "max_depth": 4 if mode == "deep" else 2,
            "max_hops": 20 if mode == "deep" else 2,
            "max_leads_per_hop": 12 if mode == "deep" else 5,
            "max_total_leads": 50 if mode == "deep" else 12,
        },
        "access_token": token,
        "case_id": case_id,
    }
    events: list[dict] = []
    async with websockets.connect(WS, open_timeout=10) as ws:
        await ws.send(json.dumps(payload))
        while len(events) < 6:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            event = json.loads(raw)
            events.append(event)
            if event.get("phase") in ("accepted", "start", "multi_input", "error"):
                break
            if event.get("error"):
                break
    return {"mode": mode, "events": events}


async def main() -> int:
    token, case_id = await login()
    if not case_id:
        case_id = await fetch_case_id(token)
    if not case_id:
        print("FAIL: no case_id — create/select a case in the UI first")
        return 1

    ok = True
    for mode in ("fast", "standard", "deep"):
        try:
            result = await probe_mode(mode, token, case_id)
            phases = [e.get("phase") for e in result["events"]]
            accepted = next((e for e in result["events"] if e.get("phase") == "accepted"), None)
            mode_echo = accepted.get("investigation_mode") if accepted else None
            print(f"{mode}: phases={phases} backend_mode={mode_echo}")
            if mode_echo != mode:
                print(f"  FAIL: expected investigation_mode={mode}, got {mode_echo}")
                ok = False
            if "error" in phases:
                err = next(e for e in result["events"] if e.get("error"))
                if err.get("status") == "busy":
                    print("  SKIP: server busy (another investigation running)")
                else:
                    print(f"  FAIL: {err.get('error')}")
                    ok = False
        except Exception as exc:
            print(f"{mode}: ERROR {exc}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
