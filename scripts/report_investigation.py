#!/usr/bin/env python3
"""Run username investigation and print a full intelligence report."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemas.discovery import DiscoveryConfig
from services.investigation_runner import investigation_runner


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


async def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "ManojYadavNR"
    print(f"Investigation: {query}")
    started = time.monotonic()

    inv_id, result = await investigation_runner.run(
        query=query,
        query_type="username",
        timeout_per_tool=150.0,
        discovery_config=DiscoveryConfig(max_hops=2, max_total_leads=12),
    )

    elapsed = time.monotonic() - started
    print(f"ID: {inv_id}  |  Elapsed: {elapsed / 60:.1f} min")

    evidence = result.evidence_extraction
    intel = (evidence.google_search_intel if evidence else None) or {}
    unified = evidence.unified_profile if evidence else None
    fusion = result.fusion

    verified = [
        e for e in (fusion.deduplicated_entities if fusion else [])
        if e.type == "account" and (e.metadata or {}).get("verified")
    ]

    _section("VERIFIED ACCOUNTS")
    for e in sorted(verified, key=lambda x: -(x.fusion_score or 0))[:25]:
        meta = e.metadata or {}
        print(f"  - {meta.get('platform') or e.value}  @{meta.get('username') or meta.get('handle')}")
        print(f"    {meta.get('url') or ''}")
        print(f"    sources={e.sources}  score={e.fusion_score}")

    _section("COLLEGES")
    for i, c in enumerate(intel.get("colleges") or [], 1):
        print(f"  {i}. {c.get('official_name') or c.get('college')}")
        print(f"     FB: {c.get('page_url')}")
        print(f"     IG: {c.get('instagram_url')} handles={c.get('instagram_handles')}")
        print(f"     Web: {c.get('website_url')}")

    _section("HACKATHON / ACHIEVEMENTS")
    for w in (intel.get("hackathon_wins") or [])[:8]:
        print(f"  - {w.get('hackathon')} ({w.get('placement')}) via {w.get('platform')}")
        print(f"    {w.get('title', '')[:120]}")

    _section("SOCIAL POSTS (FB/IG)")
    for p in (intel.get("social_posts") or [])[:8]:
        print(f"  - [{p.get('platform')}] {p.get('title', '')[:100]}")
        print(f"    {p.get('url')}")

    _section("EMPLOYMENT / LINKEDIN")
    for j in (intel.get("employment") or [])[:5]:
        print(f"  - {j.get('employer')} ({j.get('platform')})")

    _section("DISCOVERED KEYWORDS")
    for kw in (intel.get("discovered_keywords") or [])[:12]:
        phrase = kw.get("phrase") if isinstance(kw, dict) else kw
        print(f"  - {phrase}")

    _section("EXTRACTION STRATEGIES")
    if evidence:
        print(f"  {', '.join(evidence.extraction_strategies or [])}")

    _section("PERSON PROFILE")
    if unified:
        print(f"  Name: {unified.primary_display_name}")
        print(f"  Bio: {(unified.primary_bio or '')[:200]}")
        print(f"  Location: {unified.primary_location}")
        print(f"  Verified platforms: {unified.verified_platform_count}/{unified.platform_count}")

    _section("SUGGESTIONS")
    suggestions = []
    if not intel.get("colleges"):
        suggestions.append("No college resolved — try Deep mode; ensure Facebook college post is in SERP")
    if not any(p.get("platform") == "instagram" for p in (intel.get("social_posts") or [])):
        suggestions.append("No Instagram posts — campus IG pass may need more time")
    if len(verified) < 5:
        suggestions.append("Few verified accounts — enable Deep scan or add email pivot")
    if not suggestions:
        suggestions.append("Consider image reverse search on profile photos; pivot discovered emails")
    for s in suggestions:
        print(f"  • {s}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
