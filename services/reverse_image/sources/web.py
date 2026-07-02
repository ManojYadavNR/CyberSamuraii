"""Reverse image sources — content-aware public search (not generic avatar SERP)."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from schemas.reverse_image import ReverseImageMatch
from services.reverse_image.registry import register_source
from services.reverse_image.sources.common import browser_hits_to_matches, ddgs_image_search


def _search_queries(
    image_path: str,
    image_url: str | None,
    *,
    seed_query: str,
    context: dict | None = None,
) -> list[str]:
    ctx = context or {}
    queries: list[str] = []
    ocr_text = str(ctx.get("ocr_text") or "").strip()
    stem = os.path.splitext(os.path.basename(image_path))[0]
    clean_stem = re.sub(r"[_\-\s]+", " ", stem).strip()

    if ocr_text and len(ocr_text) >= 4:
        queries.append(f'"{ocr_text[:120]}"')
        if ctx.get("is_logo"):
            queries.append(f'"{ocr_text[:80]}" logo brand')

    if clean_stem and clean_stem.lower() not in ("image", "upload", "photo", "img", "picture"):
        queries.append(f'"{clean_stem}"')
        if ctx.get("is_logo"):
            queries.append(f'"{clean_stem}" logo design')

    if image_url:
        queries.append(f'"{image_url}"')

    if ctx.get("is_person_photo") and not ctx.get("is_logo"):
        queries.extend([
            "portrait headshot profile photo",
            "public profile avatar picture",
            "account profile portrait",
        ])

    if not queries and seed_query:
        queries.append(f'"{os.path.basename(seed_query)}"')

    return queries[:8]


@register_source
class GoogleLensDdgsSource:
    name = "google_lens_ddgs"

    async def search(
        self,
        image_path: str,
        image_url: str | None,
        *,
        seed_query: str,
        context: dict | None = None,
    ) -> list[ReverseImageMatch]:
        queries = _search_queries(image_path, image_url, seed_query=seed_query, context=context)
        hits: list[dict] = []
        for q in queries:
            hits.extend(await ddgs_image_search(q, num=8))
        return await browser_hits_to_matches(
            hits, source=self.name, seed_image=image_path, seed_url=image_url,
        )


@register_source
class BingVisualDdgsSource:
    name = "bing_visual_ddgs"

    async def search(
        self,
        image_path: str,
        image_url: str | None,
        *,
        seed_query: str,
        context: dict | None = None,
    ) -> list[ReverseImageMatch]:
        queries = _search_queries(image_path, image_url, seed_query=seed_query, context=context)
        hits: list[dict] = []
        for q in queries:
            hits.extend(await ddgs_image_search(q, num=6))
        return await browser_hits_to_matches(
            hits, source=self.name, seed_image=image_path, seed_url=image_url,
        )


@register_source
class YandexImagesSource:
    name = "yandex_images"

    async def search(
        self,
        image_path: str,
        image_url: str | None,
        *,
        seed_query: str,
        context: dict | None = None,
    ) -> list[ReverseImageMatch]:
        queries = _search_queries(image_path, image_url, seed_query=seed_query, context=context)
        hits: list[dict] = []
        for q in queries:
            hits.extend(await ddgs_image_search(q, num=8))
        return await browser_hits_to_matches(
            hits, source=self.name, seed_image=image_path, seed_url=image_url,
        )


@register_source
class TinEyeSource:
    name = "tineye"

    async def search(
        self,
        image_path: str,
        image_url: str | None,
        *,
        seed_query: str,
        context: dict | None = None,
    ) -> list[ReverseImageMatch]:
        if not image_url:
            return []
        hits = await ddgs_image_search(image_url, num=10)
        return await browser_hits_to_matches(
            hits, source=self.name, seed_image=image_path, seed_url=image_url,
        )


@register_source
class PublicSearchSource:
    name = "public_search"

    async def search(
        self,
        image_path: str,
        image_url: str | None,
        *,
        seed_query: str,
        context: dict | None = None,
    ) -> list[ReverseImageMatch]:
        queries = _search_queries(image_path, image_url, seed_query=seed_query, context=context)
        hits: list[dict] = []
        for q in queries:
            hits.extend(await ddgs_image_search(q, num=6))
        return await browser_hits_to_matches(
            hits, source=self.name, seed_image=image_path, seed_url=image_url,
        )
