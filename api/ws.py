"""WebSocket endpoint for live investigation progress."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.investigation_runner import investigation_runner
from services.query_detector import detect_query_type

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/investigate")
async def investigate_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        payload = json.loads(raw)
        query = str(payload.get("query", "")).strip()
        if not query:
            await websocket.send_json({"error": "query required", "status": "error"})
            await websocket.close()
            return

        query_type = payload.get("query_type") or detect_query_type(query)
        timeout = float(payload.get("timeout_per_tool", 120))

        await websocket.send_json({
            "phase": "accepted",
            "query": query,
            "query_type": query_type,
            "status": "running",
        })

        async def on_progress(event: dict) -> None:
            await websocket.send_json(event)

        investigation_id, result = await investigation_runner.run(
            query=query,
            query_type=query_type,
            timeout_per_tool=timeout,
            on_progress=on_progress,
        )

        await websocket.send_json({
            "phase": "finished",
            "investigation_id": investigation_id,
            "status": "complete",
            "result": result.model_dump(),
        })
    except WebSocketDisconnect:
        pass
    except json.JSONDecodeError:
        await websocket.send_json({"error": "invalid JSON", "status": "error"})
    except Exception as exc:
        await websocket.send_json({"error": str(exc), "status": "error"})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
