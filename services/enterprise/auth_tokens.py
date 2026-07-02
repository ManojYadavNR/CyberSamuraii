"""JWT, password hashing, authentication."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-socmint-jwt-secret")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("JWT_ACCESS_MINUTES", "60"))
REFRESH_TOKEN_DAYS = int(os.getenv("JWT_REFRESH_DAYS", "7"))
MAX_FAILED_LOGINS = int(os.getenv("MAX_FAILED_LOGINS", "5"))
LOCKOUT_MINUTES = int(os.getenv("ACCOUNT_LOCKOUT_MINUTES", "15"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(payload: dict[str, Any]) -> tuple[str, int]:
    from jose import jwt

    expires = _now() + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    data = {**payload, "exp": expires, "type": "access"}
    token = jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, ACCESS_TOKEN_MINUTES * 60


def create_refresh_token_value() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def decode_access_token(token: str) -> dict[str, Any] | None:
    from jose import jwt

    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if data.get("type") != "access":
            return None
        return data
    except Exception:
        return None


def refresh_expiry() -> datetime:
    return _now() + timedelta(days=REFRESH_TOKEN_DAYS)


def reset_token_expiry() -> datetime:
    return _now() + timedelta(hours=1)
