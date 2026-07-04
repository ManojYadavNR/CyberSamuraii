"""User and authentication business logic."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from services.enterprise.audit import log_audit
from services.enterprise.auth_tokens import (
    LOCKOUT_MINUTES,
    MAX_FAILED_LOGINS,
    create_access_token,
    create_refresh_token_value,
    hash_password,
    hash_token,
    refresh_expiry,
    reset_token_expiry,
    verify_password,
)
from services.enterprise.db import get_session, new_id
from services.enterprise.password_policy import assert_strong_password, validate_password


def _user_public(row) -> dict[str, Any]:
    from services.enterprise.rbac import normalize_role, resolve_rank

    rank = getattr(row, "rank_code", "") or resolve_rank(row.role or "")
    role = normalize_role(row.role or "")
    return {
        "user_id": row.user_id,
        "username": row.username,
        "name": row.name,
        "email": row.email,
        "role": role,
        "department": row.department or "",
        "designation": row.designation or "",
        "rank_code": rank,
        "agency_code": getattr(row, "agency_code", "") or "",
        "unit": getattr(row, "unit", "") or "",
        "district": getattr(row, "district", "") or "",
        "supervisor_id": getattr(row, "supervisor_id", "") or "",
        "employee_id": getattr(row, "employee_id", "") or "",
        "badge_number": getattr(row, "badge_number", "") or "",
        "active": bool(row.active),
        "last_login": row.last_login.isoformat() if row.last_login else None,
        "must_change_password": bool(getattr(row, "must_change_password", False)),
        "mfa_enabled": bool(getattr(row, "mfa_enabled", False)),
        "avatar_url": _avatar_public_url(row),
    }


def _avatar_public_url(row) -> str | None:
    path = getattr(row, "profile_avatar", "") or ""
    if not path:
        return None
    return f"/api/enterprise/users/{row.user_id}/avatar"


def preview_next_user_ids() -> dict[str, str]:
    """Generate the next employee ID and badge number for provisioning."""
    session = get_session()
    if not session:
        year = datetime.now(timezone.utc).year
        return {"employee_id": f"CID-{year}-0001", "badge_number": f"BG-{year}-00001"}
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        year = datetime.now(timezone.utc).year
        count = session.query(User).count()
        seq = count + 1
        return {
            "employee_id": f"CID-{year}-{seq:04d}",
            "badge_number": f"BG-{year}-{seq:05d}",
        }
    finally:
        session.close()


def _ensure_unique_ids(session, User, *, employee_id: str, badge_number: str, exclude_user_id: str = "") -> tuple[str, str]:
    """Ensure generated IDs are unique; bump sequence if collision."""
    emp = employee_id.strip()
    badge = badge_number.strip()
    year = datetime.now(timezone.utc).year
    seq = 1
    while True:
        q_emp = session.query(User).filter_by(employee_id=emp)
        q_badge = session.query(User).filter_by(badge_number=badge)
        if exclude_user_id:
            q_emp = q_emp.filter(User.user_id != exclude_user_id)
            q_badge = q_badge.filter(User.user_id != exclude_user_id)
        if not q_emp.first() and not q_badge.first():
            return emp, badge
        seq += 1
        emp = f"CID-{year}-{seq:04d}"
        badge = f"BG-{year}-{seq:05d}"


def get_user_by_id(user_id: str):
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        return session.query(_MODELS["User"]).filter_by(user_id=user_id, active=True).first()
    finally:
        session.close()


def get_user_by_username(username: str):
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        return session.query(_MODELS["User"]).filter_by(username=username.lower()).first()
    finally:
        session.close()


def login_user(*, username: str, password: str, ip: str = "", user_agent: str = "", request=None) -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        RefreshToken = _MODELS["RefreshToken"]
        user = session.query(User).filter_by(username=username.strip().lower()).first()
        if not user or not user.active:
            log_audit(username=username, action="login", entity="auth", entity_type="user", ip=ip, result="failed", request=request)
            return None
        now = datetime.now(timezone.utc)
        if user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
            log_audit(
                user_id=user.user_id, username=user.username, role=user.role, action="login",
                entity="auth", entity_type="user", ip=ip, result="locked", request=request,
            )
            return None
        if not verify_password(password, user.password_hash):
            fails = int((user.failed_logins or {}).get("count", 0)) + 1
            user.failed_logins = {"count": fails}
            if fails >= MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            session.commit()
            log_audit(
                user_id=user.user_id, username=user.username, role=user.role, action="login",
                entity="auth", entity_type="user", ip=ip, result="failed",
                failure_reason="invalid_credentials", request=request,
            )
            return None
        user.failed_logins = {"count": 0}
        user.locked_until = None
        user.last_login = now
        access, expires_in = create_access_token(
            {"sub": user.user_id, "username": user.username, "role": user.role, "name": user.name}
        )
        refresh_raw = create_refresh_token_value()
        session.add(
            RefreshToken(
                token_id=new_id(),
                user_id=user.user_id,
                token_hash=hash_token(refresh_raw),
                expires_at=refresh_expiry(),
                ip_address=ip,
                user_agent=user_agent[:256],
            )
        )
        session.commit()
        log_audit(
            user_id=user.user_id, username=user.username, role=user.role, action="login",
            entity="auth", entity_type="user", entity_id=user.user_id, ip=ip, request=request,
        )
        return {
            "access_token": access,
            "refresh_token": refresh_raw,
            "expires_in": expires_in,
            "user": _user_public(user),
            "must_change_password": bool(getattr(user, "must_change_password", False)),
        }
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def refresh_access_token(refresh_token: str, *, ip: str = "") -> dict | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        RefreshToken = _MODELS["RefreshToken"]
        User = _MODELS["User"]
        row = session.query(RefreshToken).filter_by(token_hash=hash_token(refresh_token), revoked=False).first()
        if not row or row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            return None
        user = session.query(User).filter_by(user_id=row.user_id, active=True).first()
        if not user:
            return None
        access, expires_in = create_access_token(
            {"sub": user.user_id, "username": user.username, "role": user.role, "name": user.name}
        )
        log_audit(user_id=user.user_id, username=user.username, action="token_refresh", entity="auth", ip=ip)
        return {"access_token": access, "expires_in": expires_in, "user": _user_public(user)}
    finally:
        session.close()


def logout_user(*, refresh_token: str | None, user_id: str = "", username: str = "", ip: str = "") -> None:
    session = get_session()
    if session and refresh_token:
        try:
            from services.enterprise.db import _MODELS

            RT = _MODELS["RefreshToken"]
            User = _MODELS["User"]
            row = session.query(RT).filter_by(token_hash=hash_token(refresh_token)).first()
            if row:
                if not user_id:
                    user = session.query(User).filter_by(user_id=row.user_id).first()
                    if user:
                        user_id = user.user_id
                        username = user.username
                row.revoked = True
                session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()
    log_audit(user_id=user_id, username=username, action="logout", entity="auth", ip=ip)


def request_password_reset(email: str) -> str | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        PRT = _MODELS["PasswordResetToken"]
        user = session.query(User).filter_by(email=email.strip().lower()).first()
        if not user:
            return None
        raw = create_refresh_token_value()
        session.add(
            PRT(
                token_id=new_id(),
                user_id=user.user_id,
                token_hash=hash_token(raw),
                expires_at=reset_token_expiry(),
            )
        )
        session.commit()
        log_audit(user_id=user.user_id, username=user.username, action="password_reset_request", entity="auth")
        return raw
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def confirm_password_reset(token: str, new_password: str) -> bool:
    session = get_session()
    if not session:
        return False
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        PRT = _MODELS["PasswordResetToken"]
        row = session.query(PRT).filter_by(token_hash=hash_token(token), used=False).first()
        if not row or row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            return False
        user = session.query(User).filter_by(user_id=row.user_id).first()
        if not user:
            return False
        assert_strong_password(new_password, username=user.username)
        user.password_hash = hash_password(new_password)
        row.used = True
        session.commit()
        log_audit(user_id=user.user_id, username=user.username, action="password_reset_confirm", entity="auth")
        return True
    except ValueError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def create_user(
    *,
    username: str,
    password: str,
    name: str,
    email: str,
    role: str,
    department: str = "",
    designation: str = "",
    rank_code: str = "",
    agency_code: str = "",
    unit: str = "",
    district: str = "",
    supervisor_id: str = "",
    employee_id: str = "",
    badge_number: str = "",
    actor_id: str = "",
    actor_username: str = "",
    ip: str = "",
    skip_password_policy: bool = False,
) -> dict[str, Any]:
    session = get_session()
    if not session:
        raise RuntimeError("Database unavailable")
    try:
        from services.enterprise.db import _MODELS
        from services.enterprise.rbac import all_roles, normalize_role, resolve_rank

        User = _MODELS["User"]
        uname = username.strip().lower()
        normalized_role = normalize_role(role)
        if normalized_role not in all_roles():
            raise ValueError(f"Invalid role: {role}")
        if not skip_password_policy:
            assert_strong_password(password, username=uname)
        if session.query(User).filter_by(username=uname).first():
            raise ValueError("Username already exists")
        if session.query(User).filter_by(email=email.strip().lower()).first():
            raise ValueError("Email already exists")
        preview = preview_next_user_ids()
        emp = employee_id.strip() or preview["employee_id"]
        badge = badge_number.strip() or preview["badge_number"]
        emp, badge = _ensure_unique_ids(session, User, employee_id=emp, badge_number=badge)
        rank = rank_code.strip() or resolve_rank(normalized_role)
        row = User(
            user_id=new_id(),
            username=uname,
            password_hash=hash_password(password),
            name=name.strip(),
            email=email.strip().lower(),
            role=normalized_role,
            department=department,
            designation=designation,
            rank_code=rank,
            agency_code=agency_code.strip(),
            unit=unit.strip(),
            district=district.strip(),
            supervisor_id=supervisor_id.strip(),
            employee_id=emp,
            badge_number=badge,
            active=True,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        log_audit(
            user_id=actor_id,
            username=actor_username,
            action="create_user",
            entity=row.username,
            ip=ip,
            details={"role": role, "employee_id": emp, "badge_number": badge},
        )
        return _user_public(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_user(
    *,
    user_id: str,
    actor_id: str = "",
    actor_username: str = "",
    actor_role: str = "",
    ip: str = "",
    name: str | None = None,
    email: str | None = None,
    role: str | None = None,
    department: str | None = None,
    designation: str | None = None,
    rank_code: str | None = None,
    agency_code: str | None = None,
    unit: str | None = None,
    district: str | None = None,
    supervisor_id: str | None = None,
    active: bool | None = None,
) -> dict[str, Any] | None:
    session = get_session()
    if not session:
        raise RuntimeError("Database unavailable")
    try:
        from services.enterprise.db import _MODELS
        from services.enterprise.rbac import all_roles, normalize_role, resolve_rank

        User = _MODELS["User"]
        row = session.query(User).filter_by(user_id=user_id).first()
        if not row:
            return None
        prev_role = row.role
        changes: dict[str, Any] = {}
        if name is not None:
            changes["name"] = row.name
            row.name = name.strip()
        if email is not None:
            email_norm = email.strip().lower()
            existing = session.query(User).filter_by(email=email_norm).first()
            if existing and existing.user_id != user_id:
                raise ValueError("Email already exists")
            changes["email"] = row.email
            row.email = email_norm
        if role is not None:
            normalized_role = normalize_role(role)
            if normalized_role not in all_roles():
                raise ValueError(f"Invalid role: {role}")
            changes["role"] = row.role
            row.role = normalized_role
            if rank_code is None:
                row.rank_code = resolve_rank(normalized_role)
        if department is not None:
            changes["department"] = row.department
            row.department = department
        if designation is not None:
            changes["designation"] = row.designation
            row.designation = designation
        if rank_code is not None:
            changes["rank_code"] = row.rank_code
            row.rank_code = rank_code.strip()
        if agency_code is not None:
            changes["agency_code"] = row.agency_code
            row.agency_code = agency_code.strip()
        if unit is not None:
            changes["unit"] = row.unit
            row.unit = unit.strip()
        if district is not None:
            changes["district"] = row.district
            row.district = district.strip()
        if supervisor_id is not None:
            changes["supervisor_id"] = row.supervisor_id
            row.supervisor_id = supervisor_id.strip()
        if active is not None:
            changes["active"] = row.active
            row.active = bool(active)
        if not changes:
            return _user_public(row)
        session.commit()
        session.refresh(row)
        new_snapshot = {k: getattr(row, k if k != "active" else "active") for k in changes}
        for k in list(new_snapshot.keys()):
            if k == "name":
                new_snapshot[k] = row.name
            elif k == "email":
                new_snapshot[k] = row.email
            elif k == "role":
                new_snapshot[k] = row.role
            elif k == "department":
                new_snapshot[k] = row.department
            elif k == "designation":
                new_snapshot[k] = row.designation
            elif k == "active":
                new_snapshot[k] = row.active
        log_audit(
            user_id=actor_id,
            username=actor_username,
            role=actor_role,
            action="update_user",
            entity=row.username,
            entity_type="user",
            entity_id=row.user_id,
            ip=ip,
            previous_value=str(changes),
            new_value=str(new_snapshot),
            risk_level="high" if "role" in changes else "medium",
            details={"changes": changes, "target_user_id": user_id},
        )
        return _user_public(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_users(*, limit: int = 100) -> list[dict[str, Any]]:
    session = get_session()
    if not session:
        return []
    try:
        from services.enterprise.db import _MODELS

        rows = session.query(_MODELS["User"]).order_by(_MODELS["User"].created_at.asc()).limit(limit).all()
        return [_user_public(r) for r in rows]
    finally:
        session.close()


def change_password(
    *,
    user_id: str,
    current_password: str,
    new_password: str,
    ip: str = "",
) -> bool:
    session = get_session()
    if not session:
        return False
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        user = session.query(User).filter_by(user_id=user_id, active=True).first()
        if not user or not verify_password(current_password, user.password_hash):
            return False
        assert_strong_password(new_password, username=user.username)
        user.password_hash = hash_password(new_password)
        if hasattr(user, "must_change_password"):
            user.must_change_password = False
        session.commit()
        log_audit(user_id=user.user_id, username=user.username, role=user.role, action="password_change", entity="auth", entity_type="user", ip=ip)
        return True
    except ValueError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def seed_admin_user() -> None:
    session = get_session()
    if not session:
        return
    import os

    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        username = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
        password = os.getenv("ADMIN_PASSWORD", "Socmint@Admin2026!")
        existing = session.query(User).filter_by(username=username).first()
        ok, _ = validate_password(password, username=username)
        if not ok:
            # Avoid passwords containing username (e.g. Socmint@Admin2026! for user admin)
            password = "Socmint@CID2026!Admin"
        if existing:
            if not verify_password(password, existing.password_hash):
                existing.password_hash = hash_password(password)
            existing.failed_logins = {"count": 0}
            existing.locked_until = None
            session.commit()
            return
        session.add(
            User(
                user_id=new_id(),
                username=username,
                password_hash=hash_password(password),
                name=os.getenv("ADMIN_NAME", "System Administrator"),
                email=os.getenv("ADMIN_EMAIL", f"{username}@socmint.local"),
                role="SUPER_ADMIN",
                department=os.getenv("ADMIN_DEPARTMENT", "Headquarters"),
                designation="Super Administrator",
                active=True,
            )
        )
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def migrate_legacy_user_roles() -> int:
    """Migrate users with legacy role names to rank-based roles."""
    from services.enterprise.rbac import legacy_role_map, normalize_role, resolve_rank

    session = get_session()
    if not session:
        return 0
    updated = 0
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        legacy = legacy_role_map()
        for row in session.query(User).all():
            new_role = normalize_role(row.role or "")
            new_rank = row.rank_code or resolve_rank(new_role)
            if row.role in legacy or row.role != new_role or (not row.rank_code and new_rank):
                row.role = new_role
                row.rank_code = new_rank
                updated += 1
        if updated:
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
    return updated


def purge_legacy_demo_users() -> list[str]:
    """Remove legacy demo accounts listed in config/demo_users.json."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "config" / "demo_users.json"
    if not path.exists():
        return []
    with open(path) as f:
        cfg = json.load(f)
    usernames = {str(u).strip().lower() for u in cfg.get("purge_legacy_usernames", [])}
    if not usernames:
        return []
    session = get_session()
    if not session:
        return []
    removed: list[str] = []
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        admin_name = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
        for row in session.query(User).filter(User.username.in_(usernames)).all():
            if row.username == admin_name:
                continue
            removed.append(row.username)
            session.delete(row)
        if removed:
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
    return removed


def _demo_password_for_rank(rank: str, cfg: dict) -> str:
    template = os.getenv(
        "DEMO_USER_PASSWORD",
        os.getenv("DEMO_USER_PASSWORD_TEMPLATE", cfg.get("password_template", "Socmint@CID2026!Admin")),
    )
    if "{rank}" in template:
        return template.replace("{rank}", rank)
    return template


def seed_demo_users() -> list[str]:
    """Seed one account per organizational rank; purge legacy demo users first."""
    import json
    import os
    from pathlib import Path

    if os.getenv("SEED_DEMO_USERS", "true").lower() not in {"1", "true", "yes"}:
        return []

    migrate_legacy_user_roles()
    purge_legacy_demo_users()

    path = Path(__file__).resolve().parents[2] / "config" / "demo_users.json"
    if not path.exists():
        return []
    with open(path) as f:
        cfg = json.load(f)
    created: list[str] = []
    for spec in cfg.get("users", []):
        username = str(spec.get("username", "")).strip().lower()
        role = str(spec.get("role", "")).strip()
        if not username or not role:
            continue
        password = _demo_password_for_rank(role, cfg)
        existing = get_user_by_username(username)
        if existing:
            session = get_session()
            if session:
                try:
                    from services.enterprise.db import _MODELS

                    row = session.query(_MODELS["User"]).filter_by(username=username).first()
                    if row:
                        row.role = role
                        row.rank_code = str(spec.get("rank_code", role))
                        row.password_hash = hash_password(password)
                        row.name = str(spec.get("name", username))
                        row.email = str(spec.get("email", f"{username}@agency.local"))
                        row.department = str(spec.get("department", ""))
                        row.designation = str(spec.get("designation", ""))
                        row.agency_code = str(spec.get("agency_code", ""))
                        session.commit()
                except Exception:
                    session.rollback()
                finally:
                    session.close()
            continue
        try:
            create_user(
                username=username,
                password=password,
                name=str(spec.get("name", username)),
                email=str(spec.get("email", f"{username}@agency.local")),
                role=role,
                department=str(spec.get("department", "")),
                designation=str(spec.get("designation", "")),
                rank_code=str(spec.get("rank_code", role)),
                agency_code=str(spec.get("agency_code", "")),
                skip_password_policy=True,
            )
            created.append(username)
        except Exception:
            continue
    return created


_AVATAR_DIR = None
_AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _avatar_dir():
    global _AVATAR_DIR
    if _AVATAR_DIR is None:
        from pathlib import Path

        _AVATAR_DIR = Path(__file__).resolve().parents[2] / "data" / "profile_avatars"
        _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    return _AVATAR_DIR


def save_user_avatar(*, user_id: str, content: bytes, content_type: str, ip: str = "") -> dict | None:
    ext = _AVATAR_TYPES.get((content_type or "").lower())
    if not ext or len(content) > 2_500_000:
        return None
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        User = _MODELS["User"]
        row = session.query(User).filter_by(user_id=user_id).first()
        if not row:
            return None
        dest = _avatar_dir() / f"{user_id}{ext}"
        for old in _avatar_dir().glob(f"{user_id}.*"):
            if old != dest:
                old.unlink(missing_ok=True)
        dest.write_bytes(content)
        row.profile_avatar = str(dest)
        session.commit()
        session.refresh(row)
        log_audit(user_id=user_id, username=row.username, action="profile_avatar_update", entity="user", ip=ip)
        return _user_public(row)
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


def resolve_user_avatar_path(user_id: str) -> str | None:
    session = get_session()
    if not session:
        return None
    try:
        from services.enterprise.db import _MODELS

        row = session.query(_MODELS["User"]).filter_by(user_id=user_id).first()
        if not row:
            return None
        path = getattr(row, "profile_avatar", "") or ""
        if path:
            from pathlib import Path

            p = Path(path)
            if p.is_file():
                return str(p)
        return None
    finally:
        session.close()
