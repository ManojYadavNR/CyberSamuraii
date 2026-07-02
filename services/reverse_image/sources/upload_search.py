"""True reverse image search — upload image bytes to public search engines."""

from __future__ import annotations

import os
from uuid import uuid4

import httpx

from schemas.reverse_image import ReverseImageMatch
from services.reverse_image.extractors import extract_platform, extract_profile_urls
from services.reverse_image.filters import confidence_from_hash, is_junk_url, is_real_profile_url
from services.reverse_image.matcher import classify_match_type
from services.reverse_image.registry import register_source
from services.reverse_image.sources.common import hits_to_matches_verified


def _match_from_hit(hit: dict, *, source: str, seed_path: str, seed_url: str | None, hash_sim: float = 0.0) -> ReverseImageMatch | None:
    url = str(hit.get("url") or hit.get("image") or "").strip()
    if not url or is_junk_url(url):
        return None
    page_url = str(hit.get("page_url") or hit.get("page") or url)
    title = str(hit.get("title") or "")
    snippet = str(hit.get("snippet") or "")
    platform = extract_platform(page_url) or extract_platform(url) or ""
    profiles = [u for u in extract_profile_urls(page_url, title, snippet) if is_real_profile_url(u)]
    if hash_sim < 0.55 and not profiles:
        return None
    conf = confidence_from_hash(hash_sim) if hash_sim >= 0.55 else (0.62 if profiles else 0.0)
    if conf < 0.55:
        return None
    return ReverseImageMatch(
        match_id=str(uuid4()),
        source=source,
        match_type=classify_match_type(
            url_a=seed_url or seed_path,
            url_b=url,
            hash_similarity=hash_sim,
            title=title,
            snippet=snippet,
            platform=platform,
        ),
        match_url=url,
        page_url=page_url,
        title=title or None,
        snippet=snippet or None,
        platform=platform or None,
        confidence=round(min(conf, 0.95), 4),
        evidence_path=[seed_path, source, url],
        provenance={"hash_similarity": hash_sim, "hash_verified": hash_sim >= 0.55, "upload_search": True},
        profile_urls=profiles,
        organizations=[],
    )


async def _verify_upload_hits(
    seed_path: str,
    seed_url: str | None,
    hits: list[dict],
    source: str,
    *,
    context: dict | None = None,
) -> list[ReverseImageMatch]:
    if not hits:
        return []
    search_path = str((context or {}).get("face_crop_path") or seed_path)
    return await hits_to_matches_verified(
        hits, source=source, seed_image=search_path, seed_url=seed_url,
    )


@register_source
class SauceNAOSource:
    name = "saucenao"

    async def search(
        self,
        image_path: str,
        image_url: str | None,
        *,
        seed_query: str,
        context: dict | None = None,
    ) -> list[ReverseImageMatch]:
        api_key = os.getenv("SAUCENAO_API_KEY", "")
        try:
            with open(image_path, "rb") as f:
                data = f.read()
        except OSError:
            return []

        params: dict = {"output_type": "2", "numres": "16"}
        if api_key:
            params["api_key"] = api_key
        files = {"file": (os.path.basename(image_path), data)}

        try:
            async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
                resp = await client.post("https://saucenao.com/search.php", params=params, files=files)
                if resp.status_code != 200:
                    return []
                payload = resp.json()
        except Exception:
            return []

        hits: list[dict] = []
        for block in payload.get("results") or []:
            header = block.get("header") or {}
            data = block.get("data") or {}
            ext_urls = data.get("ext_urls") or []
            page = str(data.get("ext_url") or data.get("source") or ext_urls[0] if ext_urls else "")
            image_url_hit = str(ext_urls[0] if ext_urls else data.get("thumbnail") or page)
            if not image_url_hit:
                continue
            sim = float(header.get("similarity", 0)) / 100.0
            hits.append({
                "url": image_url_hit,
                "page_url": page or image_url_hit,
                "title": str(data.get("title") or data.get("member_name") or data.get("source") or ""),
                "snippet": str(data.get("source") or ""),
                "hash_similarity": min(sim, 0.99),
            })

        matches: list[ReverseImageMatch] = []
        for hit in hits:
            sim = float(hit.get("hash_similarity") or 0)
            m = _match_from_hit(hit, source=self.name, seed_path=image_path, seed_url=image_url, hash_sim=sim)
            if m:
                matches.append(m)
        return matches


# Bing/Yandex HTTP upload APIs were retired; browser_upload.py handles those source names.

