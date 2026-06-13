"""
Optional PostgreSQL persistence for fusion results.
Activated only when DATABASE_URL is set. Fusion Engine remains source of truth in-memory per request.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import uuid4

from schemas.correlation import CorrelationOutput
from schemas.fusion import FusionOutput

logger = logging.getLogger(__name__)

_ENGINE = None
_SESSION_FACTORY = None


def persistence_enabled() -> bool:
    return bool(os.getenv("DATABASE_URL"))


def _get_engine():
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        return _ENGINE, _SESSION_FACTORY

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None, None

    try:
        from sqlalchemy import JSON, Column, DateTime, Float, String, Text, create_engine
        from sqlalchemy.orm import DeclarativeBase, sessionmaker
        from datetime import datetime, timezone

        class Base(DeclarativeBase):
            pass

        class Investigation(Base):
            __tablename__ = "investigations"
            id = Column(String(36), primary_key=True)
            feature = Column(String(64), nullable=False)
            query = Column(Text, nullable=False)
            created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

        class EntityRow(Base):
            __tablename__ = "entities"
            id = Column(String(36), primary_key=True)
            investigation_id = Column(String(36), nullable=False, index=True)
            entity_type = Column(String(32), nullable=False)
            canonical_value = Column(Text, nullable=False)
            normalized_value = Column(Text)
            aliases = Column(JSON, default=list)
            reliability_score = Column(Float, default=0.0)
            fusion_score = Column(Float, default=0.0)
            first_seen = Column(String(64))
            last_seen = Column(String(64))
            payload = Column(JSON, default=dict)

        class EvidenceRow(Base):
            __tablename__ = "evidence"
            id = Column(String(36), primary_key=True)
            investigation_id = Column(String(36), nullable=False, index=True)
            entity_id = Column(String(36), nullable=False, index=True)
            tool = Column(String(64), nullable=False)
            timestamp = Column(String(64))
            raw_source_ref = Column(Text)
            source_confidence = Column(Float, default=0.0)
            raw_payload = Column(JSON, default=dict)

        class FusionResultRow(Base):
            __tablename__ = "fusion_results"
            id = Column(String(36), primary_key=True)
            investigation_id = Column(String(36), nullable=False, index=True)
            fusion_score = Column(Float, default=0.0)
            correlation_payload = Column(JSON, default=dict)
            graph_payload = Column(JSON, default=dict)
            payload = Column(JSON, default=dict)

        engine = create_engine(db_url, pool_pre_ping=True)
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)

        _ENGINE = engine
        _SESSION_FACTORY = (Investigation, EntityRow, EvidenceRow, FusionResultRow, session_factory)
        return _ENGINE, _SESSION_FACTORY
    except Exception as exc:
        logger.warning("PostgreSQL persistence unavailable: %s", exc)
        return None, None


def persist_investigation(
    feature: str,
    query: str,
    fusion: FusionOutput | None,
    correlation: CorrelationOutput | None = None,
    graph: dict[str, Any] | None = None,
) -> str | None:
    """Persist investigation artifacts. Returns investigation_id or None if disabled."""
    _, factory = _get_engine()
    if not factory:
        return None

    Investigation, EntityRow, EvidenceRow, FusionResultRow, session_factory = factory
    investigation_id = str(uuid4())

    try:
        session = session_factory()
        session.add(
            Investigation(id=investigation_id, feature=feature, query=query)
        )

        if fusion:
            for entity in fusion.deduplicated_entities:
                session.add(
                    EntityRow(
                        id=entity.entity_id,
                        investigation_id=investigation_id,
                        entity_type=entity.type,
                        canonical_value=entity.canonical_value,
                        normalized_value=entity.normalized_value,
                        aliases=entity.aliases,
                        reliability_score=entity.reliability_score,
                        fusion_score=entity.fusion_score,
                        first_seen=entity.first_seen,
                        last_seen=entity.last_seen,
                        payload=entity.model_dump(),
                    )
                )
                for ev in entity.evidence:
                    session.add(
                        EvidenceRow(
                            id=str(uuid4()),
                            investigation_id=investigation_id,
                            entity_id=entity.entity_id,
                            tool=ev.tool,
                            timestamp=ev.timestamp,
                            raw_source_ref=ev.raw_source_ref,
                            source_confidence=ev.source_confidence,
                            raw_payload=ev.raw_payload or {},
                        )
                    )

            session.add(
                FusionResultRow(
                    id=str(uuid4()),
                    investigation_id=investigation_id,
                    fusion_score=fusion.fusion_score,
                    correlation_payload=correlation.model_dump() if correlation else {},
                    graph_payload=graph or {},
                    payload=fusion.model_dump(),
                )
            )
            fusion.investigation_id = investigation_id

        session.commit()
        session.close()
        return investigation_id
    except Exception as exc:
        logger.warning("Failed to persist investigation: %s", exc)
        return None
