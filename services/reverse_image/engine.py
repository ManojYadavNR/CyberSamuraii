"""Reverse Image Discovery Engine — parallel multi-source search."""

from __future__ import annotations

import asyncio
import logging
import os

from typing import Any, Awaitable, Callable

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

from adapters.image_common import resolve_image_source
from orchestrator.parallel_config import BROWSER_REVERSE_SOURCES, SKIP_BROWSER_MIN_MATCHES
from schemas.fusion import Entity
from schemas.reverse_image import ReverseImageDiscoveryOutput
from services.fusion_engine import _make_entity, deduplicate_entities
from services.image_intelligence.path_utils import is_local_path
from services.reverse_image.filters import is_junk_url, verify_and_filter_matches
from services.reverse_image.leads import evidence_chains_from_matches, leads_from_matches
from services.reverse_image.registry import build_sources

logger = logging.getLogger(__name__)

# Import sources to register them
import services.reverse_image.sources.web  # noqa: F401
import services.reverse_image.sources.investigation_db  # noqa: F401
import services.reverse_image.sources.upload_search  # noqa: F401
import services.reverse_image.sources.browser_upload  # noqa: F401
import services.reverse_image.sources.platform_crawl  # noqa: F401
import services.reverse_image.sources.face_kb  # noqa: F401

SOURCE_TIMEOUT_SECONDS = float(os.getenv("REVERSE_SOURCE_TIMEOUT", "25"))


class ReverseImageDiscoveryEngine:
    """Run all reverse image sources in parallel and produce leads + entities."""

    def __init__(self, source_names: list[str] | None = None):
        self._source_names = source_names

    async def discover(
        self,
        image_source: str,
        *,
        seed_query: str | None = None,
        depth: int = 0,
        context: dict | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ReverseImageDiscoveryOutput:
        path, url, err = await resolve_image_source(image_source)
        if err or not path:
            return ReverseImageDiscoveryOutput(seed_image=image_source)

        from services.intelligence_cache import get_cached, image_content_key, set_cached

        cache_key = image_content_key(path)
        cached = get_cached("reverse_discovery", cache_key)
        if cached and isinstance(cached, dict):
            try:
                return ReverseImageDiscoveryOutput.model_validate(cached)
            except Exception:
                pass

        sources = build_sources(self._source_names)
        fast_sources = [s for s in sources if s.name not in BROWSER_REVERSE_SOURCES]
        browser_sources = [s for s in sources if s.name in BROWSER_REVERSE_SOURCES]
        sources_run: list[str] = []
        sources_failed: list[str] = []
        all_matches = []
        seen_urls: set[str] = set()

        async def _emit(event: dict[str, Any]) -> None:
            if on_progress:
                try:
                    await on_progress(event)
                except Exception:
                    pass

        async def _run_source(source) -> None:
            try:
                matches = await asyncio.wait_for(
                    source.search(path, url, seed_query=seed_query or image_source, context=context),
                    timeout=SOURCE_TIMEOUT_SECONDS,
                )
                for m in matches:
                    key = m.match_url.lower().rstrip("/")
                    if key in seen_urls:
                        continue
                    seen_urls.add(key)
                    all_matches.append(m)
                    await _emit({
                        "phase": "finding_discovered",
                        "finding_type": "reverse_image_match",
                        "value": m.page_url or m.match_url,
                        "platform": m.platform or m.source,
                        "confidence": m.confidence,
                        "source": source.name,
                    })
                sources_run.append(source.name)
                await _emit({
                    "phase": "source_completed",
                    "source": source.name,
                    "matches": len(matches),
                    "status": "done",
                })
            except asyncio.TimeoutError:
                sources_failed.append(f"{source.name}:Timeout")
                await _emit({"phase": "source_completed", "source": source.name, "status": "timeout"})
            except Exception as exc:
                logger.warning("Reverse source %s failed: %s", source.name, exc)
                sources_failed.append(f"{source.name}:{type(exc).__name__}:{exc}")
                await _emit({"phase": "source_completed", "source": source.name, "status": "failed", "error": str(exc)})

        async with asyncio.TaskGroup() as tg:
            for source in fast_sources:
                tg.create_task(_run_source(source))

        if len(all_matches) < SKIP_BROWSER_MIN_MATCHES and browser_sources:
            async with asyncio.TaskGroup() as tg:
                for source in browser_sources:
                    tg.create_task(_run_source(source))

        ctx = context or {}
        verified = await verify_and_filter_matches(
            path,
            all_matches,
            face_count=int(ctx.get("face_count") or 0),
            image_category=str(ctx.get("image_category") or ""),
            face_crop_path=str(ctx.get("face_crop_path") or "") or None,
        )

        # Deduplicate matches by URL
        seen_urls: set[str] = set()
        unique_matches = []
        for m in sorted(verified, key=lambda x: -x.confidence):
            key = m.match_url.lower().rstrip("/")
            if key in seen_urls:
                continue
            seen_urls.add(key)
            unique_matches.append(m)

        generated_leads = leads_from_matches(
            unique_matches,
            source_query=seed_query or image_source,
            depth=depth,
        )
        chains = evidence_chains_from_matches(unique_matches, seed_image=path)

        output = ReverseImageDiscoveryOutput(
            seed_image=image_source,
            sources_run=sources_run,
            sources_failed=sources_failed,
            matches=unique_matches,
            generated_leads=generated_leads,
            evidence_chains=chains,
            total_matches=len(unique_matches),
        )
        try:
            set_cached("reverse_discovery", cache_key, output.model_dump())
        except Exception:
            pass
        return output

    def matches_to_entities(self, discovery: ReverseImageDiscoveryOutput) -> list[Entity]:
        entities: list[Entity] = []
        for match in discovery.matches:
            meta = {
                "platform": match.platform or match.source,
                "intel_group": "reverse_image_search",
                "match_type": match.match_type,
                "match_url": match.match_url,
                "page_url": match.page_url,
                "title": match.title,
                "snippet": match.snippet,
                "profile_urls": match.profile_urls,
                "organizations": match.organizations,
                "linked_profiles": match.profile_urls,
                "similarity_matches": [match.match_url],
                "evidence_path": match.evidence_path,
                "provenance": match.provenance,
                "finding_confidence": match.confidence,
                "hash_verified": bool(match.provenance.get("hash_verified")),
                "reverse_image_match": True,
            }
            val = match.match_url
            if is_local_path(val) or is_junk_url(val):
                continue
            if match.page_url and not is_junk_url(str(match.page_url)):
                page = str(match.page_url)
                if page != val and not is_local_path(page):
                    meta["page_url"] = page
            entities.append(_make_entity("image", val, match.source, meta, raw_source_ref=val))
            for profile_url in match.profile_urls[:3]:
                entities.append(_make_entity(
                    "account",
                    profile_url,
                    match.source,
                    {
                        **meta,
                        "url": profile_url,
                        "verified": False,
                        "reverse_image_match": True,
                        "pivotable": True,
                        "image_attributed": True,
                    },
                    raw_source_ref=profile_url,
                ))
            for org in match.organizations[:2]:
                if not match.provenance.get("hash_verified"):
                    continue
                entities.append(_make_entity(
                    "document",
                    org[:300],
                    match.source,
                    {**meta, "organization": org, "reverse_image_match": True},
                ))
        if discovery.seed_image and not is_local_path(discovery.seed_image):
            entities.append(_make_entity(
                "image",
                discovery.seed_image,
                "reverse_image_engine",
                {
                    "platform": "reverse_image_engine",
                    "match_count": discovery.total_matches,
                    "sources_run": discovery.sources_run,
                },
                raw_source_ref=discovery.seed_image,
            ))
        return deduplicate_entities(entities)


reverse_image_engine = ReverseImageDiscoveryEngine()
