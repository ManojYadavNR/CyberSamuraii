#!/usr/bin/env python3
"""Run live investigation and print summary (for terminal verification)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

QUERY = sys.argv[1] if len(sys.argv) > 1 else "ManojYadavNR"
OUT = Path("data/live_investigation_result.json")


async def main() -> None:
    from services.investigation_runner import investigation_runner

    print(f"Starting live investigation: {QUERY}", flush=True)
    inv_id, result = await investigation_runner.run(
        query=QUERY,
        query_type="username",
        timeout_per_tool=120.0,
    )
    payload = {
        "id": inv_id,
        "query": QUERY,
        "status": "complete",
        "result": result.model_dump() if hasattr(result, "model_dump") else result,
    }
    from services.json_utils import to_json_safe

    safe = to_json_safe(payload)
    OUT.write_text(json.dumps(safe, indent=2, default=str))
    print(f"Saved: {OUT}", flush=True)
    print(f"Investigation ID: {inv_id}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
