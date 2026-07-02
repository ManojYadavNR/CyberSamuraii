"""Password strength rules for user creation and password reset."""

from __future__ import annotations

import os
import re

MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "12"))

_COMMON = {
    "password", "password123", "password1", "123456", "12345678", "123456789",
    "qwerty", "abc123", "admin", "admin123", "letmein", "welcome", "monkey",
    "dragon", "master", "socmint", "socmint123", "changeme", "testpass123",
}


def validate_password(password: str, *, username: str = "") -> tuple[bool, list[str]]:
    """Return (ok, list of human-readable rule failures)."""
    errors: list[str] = []
    if len(password) < MIN_LENGTH:
        errors.append(f"Password must be at least {MIN_LENGTH} characters long")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must include at least one uppercase letter (A-Z)")
    if not re.search(r"[a-z]", password):
        errors.append("Password must include at least one lowercase letter (a-z)")
    if not re.search(r"\d", password):
        errors.append("Password must include at least one number (0-9)")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password):
        errors.append("Password must include at least one special character (!@#$%...)")
    if password.lower() in _COMMON:
        errors.append("Password is too common — choose something harder to guess")
    if username and username.strip().lower() in password.lower():
        errors.append("Password cannot contain your username")
    if re.fullmatch(r"(.)\1{5,}", password):
        errors.append("Password cannot be mostly repeated characters")
    return (len(errors) == 0, errors)


def assert_strong_password(password: str, *, username: str = "") -> None:
    ok, errors = validate_password(password, username=username)
    if not ok:
        raise ValueError("; ".join(errors))
