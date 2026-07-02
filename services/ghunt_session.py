"""GHunt Google session availability."""

from __future__ import annotations

from pathlib import Path


def ghunt_creds_path() -> Path:
    return Path.home() / ".malfrats" / "ghunt" / "creds.m"


def ghunt_session_available() -> bool:
    """True when GHunt has stored Google credentials from `ghunt login`."""
    path = ghunt_creds_path()
    return path.is_file() and path.stat().st_size > 0
