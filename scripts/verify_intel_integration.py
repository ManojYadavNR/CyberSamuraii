#!/usr/bin/env python3
"""Run username investigation and print college + Instagram integration summary."""

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
    print(f"Starting investigation for: {query}")
    started = time.monotonic()

    inv_id, result = await investigation_runner.run(
        query=query,
        query_type="username",
        timeout_per_tool=120.0,
        discovery_config=DiscoveryConfig(max_hops=2, max_total_leads=8),
    )

    elapsed = time.monotonic() - started
    print(f"Investigation ID: {inv_id}")
    print(f"Elapsed: {elapsed / 60:.1f} min")

    evidence = result.evidence_extraction
    intel = (evidence.google_search_intel if evidence else None) or {}

    _section("COLLEGE NAMES (google_search_intel.colleges)")
    colleges = intel.get("colleges") or []
    if not colleges:
        print("  (none extracted)")
    for i, c in enumerate(colleges, 1):
        print(f"  {i}. college={c.get('college')!r}")
        if c.get("page_name"):
            print(f"     page_name={c.get('page_name')!r}")
        if c.get("page_url"):
            print(f"     page_url={c.get('page_url')}")
        print(f"     platform={c.get('platform')} preview={bool(c.get('preview_url'))}")
        print(f"     post_url={c.get('url')}")

    _section("INSTAGRAM POSTS")
    ig_posts = intel.get("instagram_posts") or [
        p for p in (intel.get("social_posts") or []) if p.get("platform") == "instagram"
    ]
    if not ig_posts:
        print("  (none extracted)")
    for i, p in enumerate(ig_posts, 1):
        print(f"  {i}. {p.get('title', '')[:100]}")
        print(f"     url={p.get('url')}")
        print(f"     preview={bool(p.get('preview_url'))}")

    _section("INSTAGRAM POSTS FROM COLLEGE PAGE / COLLEGE CONTEXT")
    college_keys = {str(c.get("college") or "").lower() for c in colleges}
    college_keys.update(str(c.get("page_name") or "").lower() for c in colleges)
    college_keys.discard("")
    college_ig = []
    for p in ig_posts:
        blob = f"{p.get('title', '')} {p.get('snippet', '')}".lower()
        if any(k in blob for k in college_keys if len(k) >= 3):
            college_ig.append(p)
            continue
        if any(k in blob for k in ("college", "institute", "university", "campus", "congrat")):
            college_ig.append(p)
    if not college_ig:
        print("  (no Instagram posts matched college context)")
    for i, p in enumerate(college_ig, 1):
        print(f"  {i}. {p.get('title', '')[:100]}")
        print(f"     url={p.get('url')}")

    _section("FACEBOOK POSTS (for comparison)")
    fb = intel.get("facebook_posts") or [
        p for p in (intel.get("social_posts") or []) if p.get("platform") == "facebook"
    ]
    print(f"  count={len(fb)}")
    for i, p in enumerate(fb[:5], 1):
        print(f"  {i}. {p.get('title', '')[:90]}")

    _section("HACKATHON WINS")
    for w in (intel.get("hackathon_wins") or [])[:5]:
        print(f"  - {w.get('hackathon')} ({w.get('platform')}) placement={w.get('placement')}")

    _section("EMPLOYMENT")
    for j in (intel.get("employment") or [])[:5]:
        print(f"  - {j.get('employer')} ({j.get('platform')})")

    _section("INTEGRATION CHECKS")
    tool_ok = sum(1 for tr in (result.tool_results or []) if tr.success)
    tool_total = len(result.tool_results or [])
    print(f"  tools: {tool_ok}/{tool_total} succeeded")
    print(f"  colleges: {len(colleges)}")
    print(f"  instagram_posts: {len(ig_posts)}")
    print(f"  facebook_posts: {len(fb)}")
    print(f"  hackathon_wins: {len(intel.get('hackathon_wins') or [])}")
    print(f"  employment: {len(intel.get('employment') or [])}")
    print(f"  lead_visuals: {len((evidence.lead_visuals if evidence else None) or [])}")
    print(f"  correlation clusters: {len((result.correlation.clusters if result.correlation else None) or [])}")

    schools = [
        str(c.get("official_name") or c.get("college") or "").strip()
        for c in colleges
        if c.get("official_name") or c.get("college")
    ]
    if evidence and evidence.unified_profile:
        for fp in evidence.unified_profile.search_findings or []:
            if fp.field in ("education", "school") and fp.value:
                schools.append(fp.value)
    print(f"  unified_profile schools: {schools[:6]}")

    _section("SUMMARY JSON (colleges + instagram only)")
    summary = {
        "query": query,
        "investigation_id": inv_id,
        "colleges": colleges,
        "instagram_posts": ig_posts,
        "college_instagram_posts": college_ig,
        "facebook_post_count": len(fb),
    }
    print(json.dumps(summary, indent=2, default=str)[:8000])

    return 0 if colleges or ig_posts else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
