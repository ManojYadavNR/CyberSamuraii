"""Enterprise persistence — users, cases, sessions, audit (SQLite or PostgreSQL)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

_ENGINE = None
_SESSION_FACTORY = None
_MODELS: dict[str, Any] = {}


def enterprise_enabled() -> bool:
    return os.getenv("ENTERPRISE_AUTH", "true").lower() in {"1", "true", "yes"}


def _db_url() -> str:
    return (
        os.getenv("ENTERPRISE_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or f"sqlite:///{Path('data/socmint_enterprise.db').resolve()}"
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _add_column(conn, dialect: str, table: str, column: str, col_type: str) -> None:
    from sqlalchemy import text

    if dialect == "postgresql":
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
    else:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))


def _migrate_enterprise_schema(engine) -> None:
    """Add columns introduced after initial deploy (PostgreSQL / SQLite)."""
    try:
        from sqlalchemy import inspect, text

        insp = inspect(engine)
        tables = set(insp.get_table_names())
        dialect = engine.dialect.name
        with engine.begin() as conn:
            if "enterprise_evidence_records" in tables:
                cols = {c["name"] for c in insp.get_columns("enterprise_evidence_records")}
                if "label" not in cols:
                    _add_column(conn, dialect, "enterprise_evidence_records", "label", "VARCHAR(256) DEFAULT ''")
                if "important" not in cols:
                    _add_column(conn, dialect, "enterprise_evidence_records", "important", "BOOLEAN DEFAULT FALSE")

            if "enterprise_users" in tables:
                ucols = {c["name"] for c in insp.get_columns("enterprise_users")}
                if "must_change_password" not in ucols:
                    _add_column(conn, dialect, "enterprise_users", "must_change_password", "BOOLEAN DEFAULT FALSE")
                if "mfa_enabled" not in ucols:
                    _add_column(conn, dialect, "enterprise_users", "mfa_enabled", "BOOLEAN DEFAULT FALSE")
                if "mfa_secret" not in ucols:
                    _add_column(conn, dialect, "enterprise_users", "mfa_secret", "VARCHAR(128) DEFAULT ''")
                if "employee_id" not in ucols:
                    _add_column(conn, dialect, "enterprise_users", "employee_id", "VARCHAR(64) DEFAULT ''")
                if "badge_number" not in ucols:
                    _add_column(conn, dialect, "enterprise_users", "badge_number", "VARCHAR(64) DEFAULT ''")
                if "profile_avatar" not in ucols:
                    _add_column(conn, dialect, "enterprise_users", "profile_avatar", "VARCHAR(512) DEFAULT ''")

            if "enterprise_audit_logs" in tables:
                acols = {c["name"] for c in insp.get_columns("enterprise_audit_logs")}
                audit_migrations = [
                    ("category", "VARCHAR(64) DEFAULT 'system'"),
                    ("role", "VARCHAR(64) DEFAULT ''"),
                    ("session_id", "VARCHAR(128) DEFAULT ''"),
                    ("case_id", "VARCHAR(36) DEFAULT ''"),
                    ("investigation_id", "VARCHAR(36) DEFAULT ''"),
                    ("entity_type", "VARCHAR(64) DEFAULT ''"),
                    ("entity_id", "VARCHAR(256) DEFAULT ''"),
                    ("previous_value", "TEXT DEFAULT ''"),
                    ("new_value", "TEXT DEFAULT ''"),
                    ("failure_reason", "VARCHAR(512) DEFAULT ''"),
                    ("risk_level", "VARCHAR(16) DEFAULT 'low'"),
                    ("approval_required", "BOOLEAN DEFAULT FALSE"),
                    ("supervisor_id", "VARCHAR(36) DEFAULT ''"),
                    ("device", "VARCHAR(32) DEFAULT ''"),
                    ("browser", "VARCHAR(64) DEFAULT ''"),
                    ("os", "VARCHAR(64) DEFAULT ''"),
                    ("location_approx", "VARCHAR(128) DEFAULT ''"),
                    ("digital_signature", "VARCHAR(64) DEFAULT ''"),
                    ("hash_chain", "VARCHAR(64) DEFAULT ''"),
                ]
                for col, col_type in audit_migrations:
                    if col not in acols:
                        _add_column(conn, dialect, "enterprise_audit_logs", col, col_type)
    except Exception as exc:
        logger.warning("Enterprise schema migration skipped: %s", exc)


def init_enterprise_db() -> bool:
    global _ENGINE, _SESSION_FACTORY, _MODELS
    if _SESSION_FACTORY is not None:
        return True
    try:
        from sqlalchemy import (
            JSON,
            Boolean,
            Column,
            DateTime,
            String,
            Text,
            create_engine,
        )
        from sqlalchemy.orm import DeclarativeBase, sessionmaker

        class Base(DeclarativeBase):
            pass

        class User(Base):
            __tablename__ = "enterprise_users"
            user_id = Column(String(36), primary_key=True)
            username = Column(String(64), unique=True, nullable=False, index=True)
            password_hash = Column(Text, nullable=False)
            name = Column(String(128), nullable=False)
            email = Column(String(256), unique=True, nullable=False, index=True)
            role = Column(String(64), nullable=False, default="ANALYST")
            department = Column(String(128), default="")
            designation = Column(String(128), default="")
            employee_id = Column(String(64), default="", index=True)
            badge_number = Column(String(64), default="", index=True)
            profile_avatar = Column(String(512), default="")
            active = Column(Boolean, default=True)
            must_change_password = Column(Boolean, default=False)
            mfa_enabled = Column(Boolean, default=False)
            mfa_secret = Column(String(128), default="")
            failed_logins = Column(JSON, default=dict)
            locked_until = Column(DateTime, nullable=True)
            last_login = Column(DateTime, nullable=True)
            created_at = Column(DateTime, default=_utc_now)

        class RefreshToken(Base):
            __tablename__ = "enterprise_refresh_tokens"
            token_id = Column(String(36), primary_key=True)
            user_id = Column(String(36), nullable=False, index=True)
            token_hash = Column(String(128), nullable=False, unique=True, index=True)
            expires_at = Column(DateTime, nullable=False)
            revoked = Column(Boolean, default=False)
            created_at = Column(DateTime, default=_utc_now)
            ip_address = Column(String(64), default="")
            user_agent = Column(String(256), default="")

        class PasswordResetToken(Base):
            __tablename__ = "enterprise_password_resets"
            token_id = Column(String(36), primary_key=True)
            user_id = Column(String(36), nullable=False, index=True)
            token_hash = Column(String(128), nullable=False, unique=True)
            expires_at = Column(DateTime, nullable=False)
            used = Column(Boolean, default=False)
            created_at = Column(DateTime, default=_utc_now)

        class Case(Base):
            __tablename__ = "enterprise_cases"
            case_id = Column(String(36), primary_key=True)
            case_number = Column(String(32), unique=True, nullable=False, index=True)
            title = Column(String(256), nullable=False)
            description = Column(Text, default="")
            priority = Column(String(16), default="MEDIUM")
            status = Column(String(32), default="OPEN", index=True)
            assigned_to = Column(String(36), nullable=True, index=True)
            created_by = Column(String(36), nullable=False)
            created_at = Column(DateTime, default=_utc_now)
            updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)
            archived_at = Column(DateTime, nullable=True)

        class CaseInvestigation(Base):
            __tablename__ = "enterprise_case_investigations"
            id = Column(String(36), primary_key=True)
            case_id = Column(String(36), nullable=False, index=True)
            investigation_id = Column(String(36), nullable=False, index=True)
            started_by = Column(String(36), nullable=False)
            query = Column(Text, default="")
            created_at = Column(DateTime, default=_utc_now)

        class WorkspaceNote(Base):
            __tablename__ = "enterprise_workspace_notes"
            note_id = Column(String(36), primary_key=True)
            case_id = Column(String(36), nullable=False, index=True)
            author_id = Column(String(36), nullable=False)
            content = Column(Text, nullable=False)
            pinned = Column(Boolean, default=False)
            created_at = Column(DateTime, default=_utc_now)

        class AuditLog(Base):
            __tablename__ = "enterprise_audit_logs"
            log_id = Column(String(36), primary_key=True)
            timestamp = Column(DateTime, default=_utc_now, index=True)
            user_id = Column(String(36), default="", index=True)
            username = Column(String(64), default="")
            role = Column(String(64), default="")
            session_id = Column(String(128), default="")
            category = Column(String(64), default="system", index=True)
            action = Column(String(64), nullable=False, index=True)
            entity = Column(String(256), default="")
            entity_type = Column(String(64), default="")
            entity_id = Column(String(256), default="")
            case_id = Column(String(36), default="", index=True)
            investigation_id = Column(String(36), default="", index=True)
            ip_address = Column(String(64), default="")
            location_approx = Column(String(128), default="")
            device = Column(String(32), default="")
            browser = Column(String(64), default="")
            os = Column(String(64), default="")
            result = Column(String(32), default="success", index=True)
            failure_reason = Column(String(512), default="")
            risk_level = Column(String(16), default="low", index=True)
            approval_required = Column(Boolean, default=False)
            supervisor_id = Column(String(36), default="")
            previous_value = Column(Text, default="")
            new_value = Column(Text, default="")
            digital_signature = Column(String(64), default="")
            hash_chain = Column(String(64), default="")
            details = Column(JSON, default=dict)

        class PasswordResetRequest(Base):
            __tablename__ = "enterprise_password_reset_requests"
            request_id = Column(String(36), primary_key=True)
            user_id = Column(String(36), nullable=False, index=True)
            employee_id = Column(String(64), nullable=False, index=True)
            status = Column(String(32), default="pending_supervisor", index=True)
            reason = Column(Text, default="")
            requested_at = Column(DateTime, default=_utc_now)
            supervisor_id = Column(String(36), default="")
            supervisor_notes = Column(Text, default="")
            supervisor_decision_at = Column(DateTime, nullable=True)
            admin_id = Column(String(36), default="")
            admin_notes = Column(Text, default="")
            admin_decision_at = Column(DateTime, nullable=True)
            temp_password_issued = Column(Boolean, default=False)
            completed_at = Column(DateTime, nullable=True)

        class EvidenceRecord(Base):
            __tablename__ = "enterprise_evidence_records"
            evidence_id = Column(String(36), primary_key=True)
            case_id = Column(String(36), nullable=False, index=True)
            investigation_id = Column(String(36), nullable=True, index=True)
            sha256 = Column(String(64), nullable=False)
            previous_hash = Column(String(64), default="")
            source = Column(String(128), default="")
            collector_id = Column(String(36), default="")
            payload_ref = Column(Text, default="")
            label = Column(String(256), default="")
            important = Column(Boolean, default=False)
            archived = Column(Boolean, default=False)
            created_at = Column(DateTime, default=_utc_now)

        class CaseComment(Base):
            __tablename__ = "enterprise_case_comments"
            comment_id = Column(String(36), primary_key=True)
            case_id = Column(String(36), nullable=False, index=True)
            author_id = Column(String(36), nullable=False)
            content = Column(Text, nullable=False)
            mentions = Column(JSON, default=list)
            created_at = Column(DateTime, default=_utc_now)

        class CaseTask(Base):
            __tablename__ = "enterprise_case_tasks"
            task_id = Column(String(36), primary_key=True)
            case_id = Column(String(36), nullable=False, index=True)
            title = Column(String(256), nullable=False)
            description = Column(Text, default="")
            assigned_to = Column(String(36), nullable=True, index=True)
            status = Column(String(32), default="OPEN")
            created_by = Column(String(36), nullable=False)
            created_at = Column(DateTime, default=_utc_now)
            completed_at = Column(DateTime, nullable=True)

        class WorkspaceBookmark(Base):
            __tablename__ = "enterprise_workspace_bookmarks"
            bookmark_id = Column(String(36), primary_key=True)
            case_id = Column(String(36), nullable=False, index=True)
            user_id = Column(String(36), nullable=False, index=True)
            entity_id = Column(String(256), nullable=False)
            entity_label = Column(String(512), default="")
            entity_type = Column(String(64), default="")
            created_at = Column(DateTime, default=_utc_now)

        class WorkspacePin(Base):
            __tablename__ = "enterprise_workspace_pins"
            pin_id = Column(String(36), primary_key=True)
            case_id = Column(String(36), nullable=False, index=True)
            user_id = Column(String(36), nullable=False)
            finding_key = Column(String(256), nullable=False)
            finding_label = Column(String(512), default="")
            finding_data = Column(JSON, default=dict)
            created_at = Column(DateTime, default=_utc_now)

        class ApprovalRecord(Base):
            __tablename__ = "enterprise_approval_records"
            approval_id = Column(String(36), primary_key=True)
            case_id = Column(String(36), nullable=False, index=True)
            investigation_id = Column(String(36), nullable=False, index=True)
            cluster_id = Column(String(128), default="")
            stage = Column(String(32), nullable=False)
            decision = Column(String(32), default="pending")
            reviewer_id = Column(String(36), default="")
            reviewer_name = Column(String(128), default="")
            notes = Column(Text, default="")
            created_at = Column(DateTime, default=_utc_now)

        class Notification(Base):
            __tablename__ = "enterprise_notifications"
            notification_id = Column(String(36), primary_key=True)
            user_id = Column(String(36), nullable=False, index=True)
            title = Column(String(256), nullable=False)
            body = Column(Text, default="")
            kind = Column(String(64), default="info")
            case_id = Column(String(36), default="")
            read = Column(Boolean, default=False)
            created_at = Column(DateTime, default=_utc_now)

        class AgencyScope(Base):
            __tablename__ = "enterprise_agency_scopes"
            scope_id = Column(String(36), primary_key=True)
            agency_code = Column(String(64), nullable=False, index=True)
            agency_name = Column(String(128), nullable=False)
            level = Column(String(32), default="district")
            region = Column(String(128), default="")
            active = Column(Boolean, default=True)

        url = _db_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        Path("data").mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        Base.metadata.create_all(engine)
        _migrate_enterprise_schema(engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)

        _ENGINE = engine
        _SESSION_FACTORY = session_factory
        _MODELS = {
            "User": User,
            "RefreshToken": RefreshToken,
            "PasswordResetToken": PasswordResetToken,
            "Case": Case,
            "CaseInvestigation": CaseInvestigation,
            "WorkspaceNote": WorkspaceNote,
            "AuditLog": AuditLog,
            "PasswordResetRequest": PasswordResetRequest,
            "EvidenceRecord": EvidenceRecord,
            "CaseComment": CaseComment,
            "CaseTask": CaseTask,
            "WorkspaceBookmark": WorkspaceBookmark,
            "WorkspacePin": WorkspacePin,
            "ApprovalRecord": ApprovalRecord,
            "Notification": Notification,
            "AgencyScope": AgencyScope,
        }
        try:
            from services.enterprise.audit import ensure_audit_chain_integrity
            ensure_audit_chain_integrity()
        except Exception as exc:
            logger.debug("Audit chain integrity check skipped: %s", exc)
        logger.info("Enterprise database initialized (%s)", url.split("@")[-1][:60])
        return True
    except Exception as exc:
        logger.warning("Enterprise database unavailable: %s", exc)
        return False


def get_session():
    if not init_enterprise_db():
        return None
    return _SESSION_FACTORY()


def new_id() -> str:
    return str(uuid4())
