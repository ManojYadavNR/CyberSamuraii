"""Phone social OSINT — ignorant registration checks, profile resolution, web matches."""

from __future__ import annotations

import asyncio

from adapters.base import BaseAdapter
from schemas.common import ToolResult


class PhoneSocialIntelAdapter(BaseAdapter):
    name = "phone_social_intel"
    default_timeout = 180.0

    async def _execute(self, query: str) -> ToolResult:
        from services.phone_intelligence.engine import run_phone_social_intel
        from services.phone_intelligence.runtime import ensure_phone_stack

        await asyncio.to_thread(ensure_phone_stack)
        return await asyncio.to_thread(run_phone_social_intel, query)
