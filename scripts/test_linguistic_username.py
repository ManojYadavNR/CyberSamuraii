#!/usr/bin/env python3
"""Run username investigation and evaluate linguistic ML on real tool data."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("LINGUISTIC_ANALYSIS_ENABLED", "true")
os.environ.setdefault("LINGUISTIC_ML_ENABLED", "true")
os.environ.setdefault("LINGUISTIC_LOW_MEMORY", "true")
os.environ.setdefault("LINGUISTIC_USE_GPU", "false")


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def _print_linguistic(ling: dict) -> None:
    if not ling:
        print("  (no linguistic analysis)")
        return

    print(f"  Engine: {ling.get('engine_mode', 'unknown')}")
    print(f"  Artifacts: {ling.get('artifacts_analyzed', 0)}")
    print(f"  Characters: {ling.get('total_characters', 0)}")

    quality = ling.get("corpus_quality") or {}
    if quality:
        print(
            f"  Corpus: kept {quality.get('kept_artifacts', '?')} / "
            f"raw {quality.get('raw_artifacts', '?')} "
            f"(dropped noise: {quality.get('dropped_noise', 0)})"
        )

    profile = ling.get("language_profile") or {}
    print(f"  Primary language: {profile.get('primary', 'unknown')}")

    sentiment = ling.get("sentiment_overview") or {}
    print(
        f"  Sentiment: +{sentiment.get('positive_artifacts', 0)} "
        f"/ -{sentiment.get('negative_artifacts', 0)} "
        f"/ ~{sentiment.get('neutral_artifacts', 0)}"
    )

    signals = ling.get("identity_signals") or []
    if signals:
        print("  Identity matches (seed username):")
        for s in signals[:6]:
            print(f"    - [{s.get('kind')}] {s.get('text')} ({s.get('score', 0):.2f})")

    topics = ling.get("topics") or []
    if topics:
        print("  Top topics:")
        for t in topics[:5]:
            if isinstance(t, dict):
                print(f"    - {t.get('topic')} ({float(t.get('score', 0)):.2f})")

    entities = ling.get("named_entities") or []
    if entities:
        print("  Key entities:")
        for e in entities[:8]:
            if isinstance(e, dict):
                print(f"    - [{e.get('kind')}] {e.get('text')} ({float(e.get('confidence', 0)):.2f})")

    keywords = ling.get("keywords") or []
    if keywords:
        print(f"  Keywords: {', '.join(str(k) for k in keywords[:10])}")

    cross = ling.get("cross_links") or []
    if cross:
        print(f"  Cross-text links: {len(cross)} (semantic + stylometry)")


async def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "ManojYadavNR"
    mode = sys.argv[2] if len(sys.argv) > 2 else "standard"

    from schemas.discovery import DiscoveryConfig
    from services.investigation_runner import investigation_runner

    _section(f"INVESTIGATION: {query}")
    print(f"Mode: {mode} | Linguistic ML: on | Low-memory: on")
    started = time.monotonic()

    inv_id, result = await investigation_runner.run(
        query=query,
        query_type="username",
        timeout_per_tool=120.0,
        discovery_config=DiscoveryConfig(enabled=False),
        investigation_mode=mode if mode in ("fast", "standard", "deep") else "standard",
    )

    elapsed = time.monotonic() - started
    evidence = result.evidence_extraction
    ling = (evidence.linguistic_analysis if evidence else None) or {}

    print(f"\nInvestigation ID: {inv_id}")
    print(f"Elapsed: {elapsed / 60:.1f} min")
    if evidence and evidence.extraction_strategies:
        print(f"Strategies: {', '.join(evidence.extraction_strategies)}")

    _section("LINGUISTIC ML EVALUATION")
    _print_linguistic(ling)

    slug = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
    out_path = Path(f"data/linguistic_eval_{slug}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ling, indent=2, default=str))
    print(f"\nSaved: {out_path}")

    if ling.get("engine_mode") == "ml" and ling.get("artifacts_analyzed", 0) > 0:
        print("\n✓ ML linguistic stack ran on real investigation data.")
        return 0
    if ling.get("artifacts_analyzed", 0) > 0:
        print("\n~ Linguistic ran but not in full ML mode.")
        return 0
    print("\n✗ No analyzable text from tools — try standard/deep mode.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
