"""Linguistic analysis for OSINT investigations."""

from services.linguistic.bridge import apply_linguistic_analysis
from services.linguistic.engine import linguistic_engine

__all__ = ["apply_linguistic_analysis", "linguistic_engine"]
