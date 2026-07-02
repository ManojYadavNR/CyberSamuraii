"""Attach linguistic analysis to evidence output without changing frontend contracts."""

from __future__ import annotations

import logging
from typing import Any

from schemas.evidence import EvidenceExtractionOutput
from services.linguistic.engine import linguistic_enabled, linguistic_engine

logger = logging.getLogger(__name__)


def apply_linguistic_analysis(
    evidence: EvidenceExtractionOutput | None,
    *,
    seed_query: str,
    tool_results: list[Any] | None = None,
) -> EvidenceExtractionOutput | None:
    """Return evidence with linguistic_analysis populated (additive only)."""
    if evidence is None or not linguistic_enabled():
        return evidence
    try:
        analysis = linguistic_engine.analyze(
            seed_query=seed_query,
            tool_results=tool_results,
            evidence=evidence,
        )
        strategies = set(evidence.extraction_strategies or [])
        strategies.add("linguistic_analysis")
        return evidence.model_copy(
            update={
                "linguistic_analysis": analysis.model_dump(),
                "extraction_strategies": sorted(strategies),
            }
        )
    except Exception as exc:
        logger.warning("Linguistic analysis failed (non-fatal): %r", exc)
        return evidence
