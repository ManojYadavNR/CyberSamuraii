"""
Optional PostgreSQL persistence for fusion results.
Activated only when DATABASE_URL is set. Fusion Engine remains source of truth in-memory per request.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from uuid import uuid4

from schemas.correlation import CorrelationOutput
from schemas.fusion import FusionOutput
from services.json_utils import to_json_safe

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

        class DiscoveryChainRow(Base):
            __tablename__ = "discovery_chains"
            id = Column(String(36), primary_key=True)
            seed_investigation_id = Column(String(36), nullable=True, index=True)
            seed_query = Column(Text, nullable=False)
            stop_reason = Column(String(64), default="")
            total_hops = Column(Float, default=0.0)
            payload = Column(JSON, default=dict)
            created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

        engine = create_engine(db_url, pool_pre_ping=True)
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)

        _ENGINE = engine
        _SESSION_FACTORY = (
            Investigation,
            EntityRow,
            EvidenceRow,
            FusionResultRow,
            DiscoveryChainRow,
            session_factory,
        )
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
    *,
    investigation_id: str | None = None,
    result_snapshot: dict[str, Any] | None = None,
) -> str | None:
    """Persist investigation artifacts. Returns investigation_id or None if disabled."""
    _, factory = _get_engine()
    if not factory:
        return None

    Investigation, EntityRow, EvidenceRow, FusionResultRow, DiscoveryChainRow, session_factory = factory
    inv_id = investigation_id or str(uuid4())
    graph_payload = to_json_safe(dict(graph or {}))
    if result_snapshot:
        graph_payload["_result_snapshot"] = to_json_safe(result_snapshot)

    try:
        session = session_factory()
        existing = session.query(Investigation).filter(Investigation.id == inv_id).first()
        if not existing:
            session.add(Investigation(id=inv_id, feature=feature, query=query))

        if fusion:
            if existing:
                session.query(EntityRow).filter(EntityRow.investigation_id == inv_id).delete()
                session.query(EvidenceRow).filter(EvidenceRow.investigation_id == inv_id).delete()
                session.flush()

            entities_to_save = []
            seen_entity_ids: set[str] = set()
            for entity in fusion.deduplicated_entities or []:
                eid = entity.entity_id
                if eid in seen_entity_ids:
                    continue
                seen_entity_ids.add(eid)
                entities_to_save.append(entity)

            if entities_to_save:
                entity_ids = [e.entity_id for e in entities_to_save]
                session.query(EvidenceRow).filter(EvidenceRow.entity_id.in_(entity_ids)).delete(
                    synchronize_session=False
                )
                session.query(EntityRow).filter(EntityRow.id.in_(entity_ids)).delete(
                    synchronize_session=False
                )
                session.flush()

                for entity in entities_to_save:
                    session.add(
                        EntityRow(
                            id=entity.entity_id,
                            investigation_id=inv_id,
                            entity_type=entity.type,
                            canonical_value=entity.canonical_value,
                            normalized_value=entity.normalized_value,
                            aliases=entity.aliases,
                            reliability_score=entity.reliability_score,
                            fusion_score=entity.fusion_score,
                            first_seen=entity.first_seen,
                            last_seen=entity.last_seen,
                            payload=to_json_safe(entity.model_dump()),
                        )
                    )
                    for ev in entity.evidence:
                        session.add(
                            EvidenceRow(
                                id=str(uuid4()),
                                investigation_id=inv_id,
                                entity_id=entity.entity_id,
                                tool=ev.tool,
                                timestamp=ev.timestamp,
                                raw_source_ref=ev.raw_source_ref,
                                source_confidence=ev.source_confidence,
                                raw_payload=to_json_safe(ev.raw_payload or {}),
                            )
                        )
                session.flush()

            fusion_row = session.query(FusionResultRow).filter(FusionResultRow.investigation_id == inv_id).first()
            if fusion_row:
                fusion_row.fusion_score = fusion.fusion_score
                fusion_row.correlation_payload = to_json_safe(correlation.model_dump()) if correlation else {}
                fusion_row.graph_payload = graph_payload
                fusion_row.payload = to_json_safe(fusion.model_dump())
            else:
                session.add(
                    FusionResultRow(
                        id=str(uuid4()),
                        investigation_id=inv_id,
                        fusion_score=fusion.fusion_score,
                        correlation_payload=to_json_safe(correlation.model_dump()) if correlation else {},
                        graph_payload=graph_payload,
                        payload=to_json_safe(fusion.model_dump()),
                    )
                )
            fusion.investigation_id = inv_id

        session.commit()
        session.close()
        return inv_id
    except Exception as exc:
        logger.warning("Failed to persist investigation: %s", exc)
        try:
            session.rollback()
            session.close()
        except Exception:
            pass
        return None


def load_investigation_from_db(investigation_id: str) -> dict[str, Any] | None:
    """Load investigation from PostgreSQL when in-memory cache misses."""
    _, factory = _get_engine()
    if not factory:
        return None

    Investigation, EntityRow, EvidenceRow, FusionResultRow, DiscoveryChainRow, session_factory = factory

    try:
        session = session_factory()
        inv = session.query(Investigation).filter(Investigation.id == investigation_id).first()
        if not inv:
            session.close()
            return None

        fusion_row = session.query(FusionResultRow).filter(FusionResultRow.investigation_id == investigation_id).first()
        graph_payload = fusion_row.graph_payload if fusion_row else {}
        snapshot = (graph_payload or {}).get("_result_snapshot")
        if snapshot:
            session.close()
            return {
                "id": inv.id,
                "query": inv.query,
                "query_type": detect_query_type(inv.query),
                "status": "complete",
                "result": to_json_safe(snapshot),
            }

        correlation = fusion_row.correlation_payload if fusion_row else {}
        graph = {k: v for k, v in (graph_payload or {}).items() if k != "_result_snapshot"}
        fusion = fusion_row.payload if fusion_row else {}
        session.close()
        return {
            "id": inv.id,
            "query": inv.query,
            "query_type": detect_query_type(inv.query),
            "status": "complete",
            "result": to_json_safe({
                "feature": inv.feature,
                "query": inv.query,
                "fusion": fusion,
                "correlation": correlation,
                "graph": graph,
                "tool_results": [],
                "tools_succeeded": 0,
                "tools_failed": 0,
                "total_execution_time_ms": 0,
            }),
        }
    except Exception as exc:
        logger.warning("Failed to load investigation %s: %s", investigation_id, exc)
        return None


def load_recent_image_entities(limit: int = 200) -> list[dict[str, Any]]:
    """Load recent image entities for hash-based reverse matching."""
    _, factory = _get_engine()
    if not factory:
        return []
    _, EntityRow, _, _, _, session_factory = factory
    try:
        session = session_factory()
        rows = (
            session.query(EntityRow)
            .filter(EntityRow.entity_type == "image")
            .order_by(EntityRow.last_seen.desc())
            .limit(limit)
            .all()
        )
        out = []
        for row in rows:
            payload = row.payload or {}
            out.append({
                "entity_id": row.id,
                "value": row.canonical_value,
                "url": payload.get("url"),
                "metadata": payload.get("metadata") or payload,
            })
        session.close()
        return out
    except Exception as exc:
        logger.warning("Failed to load recent image entities: %s", exc)
        return []


def detect_query_type(query: str) -> str:
    from services.query_detector import detect_query_type as _detect

    return _detect(query)


def persist_discovery_chain(
    discovery,
    seed_investigation_id: str | None = None,
) -> str | None:
    """Persist recursive discovery chain when PostgreSQL is enabled."""
    _, factory = _get_engine()
    if not factory:
        return None

    _, _, _, _, DiscoveryChainRow, session_factory = factory
    chain_id = str(uuid4())

    try:
        from schemas.discovery import DiscoveryOutput

        payload = to_json_safe(discovery.model_dump() if isinstance(discovery, DiscoveryOutput) else discovery)
        session = session_factory()
        session.add(
            DiscoveryChainRow(
                id=chain_id,
                seed_investigation_id=seed_investigation_id,
                seed_query=payload.get("seed_query", ""),
                stop_reason=payload.get("stop_reason", ""),
                total_hops=float(payload.get("total_hops", 0)),
                payload=payload,
            )
        )
        session.commit()
        session.close()
        return chain_id
    except Exception as exc:
        logger.warning("Failed to persist discovery chain: %s", exc)
        return None
