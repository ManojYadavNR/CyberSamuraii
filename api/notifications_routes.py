"""Notification SSE stream."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.deps import get_current_user
from services.enterprise.notifications import list_notifications

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def get_notifications(user=Depends(get_current_user), unread_only: bool = False):
    return {"notifications": list_notifications(user.user_id, unread_only=unread_only)}


@router.post("/{notification_id}/read")
async def read_notification(notification_id: str, user=Depends(get_current_user)):
    from services.enterprise.notifications import mark_read

    return {"ok": mark_read(notification_id, user.user_id)}


@router.post("/read-all")
async def read_all(user=Depends(get_current_user)):
    from services.enterprise.notifications import mark_all_read

    return {"count": mark_all_read(user.user_id)}


@router.get("/stream")
async def notification_stream(user=Depends(get_current_user)):
    async def event_gen():
        last_count = -1
        while True:
            notes = list_notifications(user.user_id, unread_only=True, limit=20)
            if len(notes) != last_count:
                payload = json.dumps({"notifications": notes, "unread": len(notes)})
                yield f"data: {payload}\n\n"
                last_count = len(notes)
            await asyncio.sleep(5)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
