"""Universal evidence extraction from discovered OSINT data."""

__all__ = ["UniversalEvidenceExtractionEngine", "evidence_engine"]


def __getattr__(name: str):
    if name in ("UniversalEvidenceExtractionEngine", "evidence_engine"):
        from services.evidence.engine import UniversalEvidenceExtractionEngine, evidence_engine
        if name == "UniversalEvidenceExtractionEngine":
            return UniversalEvidenceExtractionEngine
        return evidence_engine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
