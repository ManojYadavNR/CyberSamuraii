"""WebSocket endpoint for live investigation progress."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from schemas.discovery import DiscoveryConfig
from services.enterprise.audit import log_audit
from services.enterprise.auth_tokens import decode_access_token
from services.enterprise.cases import link_investigation
from services.enterprise.db import enterprise_enabled
from services.enterprise.rbac import has_permission
from services.investigation_cancel import InvestigationCancelledError, cancel_investigation
from services.investigation_runner import _dump_result, investigation_runner
from services.query_detector import detect_query_type
from services.resource_guard import InvestigationBusyError

router = APIRouter(tags=["websocket"])


def _ws_user(payload: dict, query_params: dict) -> tuple[str, str, str] | None:
    if not enterprise_enabled():
        return ("anonymous", "anonymous", "SUPER_ADMIN")
    token = payload.get("access_token") or query_params.get("token")
    if not token:
        return None
    data = decode_access_token(str(token))
    if not data:
        return None
    role = data.get("role", "VIEWER")
    if not has_permission(role, "start_investigation"):
        return None
    return (data.get("sub", ""), data.get("username", ""), role)


async def _cancel_listener(websocket: WebSocket, cancel_event: asyncio.Event) -> None:
    """Listen for {action: cancel} while investigation runs."""
    try:
        while not cancel_event.is_set():
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            if str(payload.get("action") or "").lower() == "cancel":
                cancel_event.set()
                cancel_investigation()
                return
    except WebSocketDisconnect:
        cancel_event.set()
        cancel_investigation()
    except Exception:
        pass


@router.websocket("/ws/investigate")
async def investigate_ws(websocket: WebSocket):
    await websocket.accept()
    cancel_event = asyncio.Event()
    listener_task: asyncio.Task[None] | None = None
    disconnected = False
    try:
        raw = await websocket.receive_text()
        payload = json.loads(raw)
        user_info = _ws_user(payload, dict(websocket.query_params))
        if user_info is None:
            await websocket.send_json({"error": "authentication required", "status": "error"})
            await websocket.close()
            return
        user_id, username, _role = user_info

        query = str(payload.get("query", "")).strip()
        if not query:
            await websocket.send_json({"error": "query required", "status": "error"})
            await websocket.close()
            return

        query_type = payload.get("query_type") or detect_query_type(query)
        timeout = float(payload.get("timeout_per_tool", 40 if query_type == "image" else 180))
        discovery_raw = payload.get("discovery")
        discovery_config = (
            DiscoveryConfig.model_validate(discovery_raw)
            if isinstance(discovery_raw, dict)
            else None
        )
        investigation_mode = payload.get("investigation_mode")
        image_profile = str(payload.get("image_profile", "fast" if query_type == "image" else "fast"))
        case_id = payload.get("case_id")
        if enterprise_enabled() and not case_id:
            await websocket.send_json({"error": "case_id required — select a case before investigating", "status": "error"})
            await websocket.close()
            return

        from schemas.investigation_mode import resolve_investigation_mode

        resolved_mode = resolve_investigation_mode(
            explicit=str(investigation_mode) if investigation_mode else None,
            discovery=discovery_config,
            image_profile=image_profile,
        )

        await websocket.send_json({
            "phase": "accepted",
            "query": query,
            "query_type": query_type,
            "status": "running",
            "discovery_enabled": discovery_config.enabled if discovery_config else True,
            "investigation_mode": resolved_mode,
            "image_profile": image_profile,
        })

        disconnected = False
        listener_task = asyncio.create_task(_cancel_listener(websocket, cancel_event))

        async def on_progress(event: dict) -> None:
            nonlocal disconnected
            if disconnected:
                return
            try:
                await websocket.send_json(event)
            except Exception:
                disconnected = True

        investigation_id, result = await investigation_runner.run(
            query=query,
            query_type=query_type,
            timeout_per_tool=timeout,
            discovery_config=discovery_config,
            on_progress=on_progress,
            image_profile=image_profile,
            investigation_mode=resolved_mode,
            cancel_event=cancel_event,
        )

        if case_id and enterprise_enabled():
            link_investigation(case_id=case_id, investigation_id=investigation_id, started_by=user_id, query=query)
            from services.enterprise.evidence_governance import record_evidence

            record_evidence(
                case_id=case_id,
                investigation_id=investigation_id,
                source="investigation_complete",
                collector_id=user_id,
                payload={"query": query, "investigation_id": investigation_id},
                label=f"Investigation: {query[:80]}",
                username=username,
            )

        log_audit(
            user_id=user_id,
            username=username,
            action="start_investigation",
            entity=investigation_id,
            details={"query": query, "case_id": case_id, "via": "websocket"},
        )

        # Always try to deliver the final payload — disk already has status=complete
        # for poll recovery if the socket is gone.
        try:
            await websocket.send_json({
                "phase": "finished",
                "investigation_id": investigation_id,
                "status": "complete",
                "result": _dump_result(result),
            })
        except Exception:
            pass
    except InvestigationCancelledError:
        if not disconnected:
            await websocket.send_json({
                "phase": "cancelled",
                "status": "cancelled",
                "error": "Investigation stopped by user",
            })
    except InvestigationBusyError as exc:
        await websocket.send_json({"error": str(exc), "status": "busy", "phase": "error"})
    except WebSocketDisconnect:
        pass
    except json.JSONDecodeError:
        await websocket.send_json({"error": "invalid JSON", "status": "error"})
    except Exception as exc:
        await websocket.send_json({"error": str(exc), "status": "error"})
    finally:
        if listener_task and not listener_task.done():
            listener_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass
