"""Crawl public platform image results and visually match against the seed photo."""

from __future__ import annotations

import asyncio

from schemas.reverse_image import ReverseImageMatch
from services.reverse_image.registry import register_source
from services.reverse_image.sources.common import ddgs_image_search, hits_to_matches_verified

PERSON_IMAGE_QUERIES = [
    "profile photo portrait headshot",
    "account avatar profile picture",
    "public profile portrait photo",
    "passport style portrait photo",
]


@register_source
class PlatformCrawlSource:
    name = "platform_crawl"

    async def search(
        self,
        image_path: str,
        image_url: str | None,
        *,
        seed_query: str,
        context: dict | None = None,
    ) -> list[ReverseImageMatch]:
        ctx = context or {}
        if not ctx.get("is_person_photo"):
            return []

        hits: list[dict] = []
        tasks = [ddgs_image_search(q, num=8) for q in PERSON_IMAGE_QUERIES[:6]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for batch in results:
            if isinstance(batch, list):
                hits.extend(batch)

        # Also search with face crop if available
        crop = ctx.get("face_crop_path")
        if crop:
            crop_hits = await ddgs_image_search("portrait profile photo", num=10)
            hits.extend(crop_hits)

        return await hits_to_matches_verified(
            hits, source=self.name, seed_image=str((context or {}).get("face_crop_path") or image_path), seed_url=image_url,
        )
