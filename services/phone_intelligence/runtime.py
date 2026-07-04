"""Phone OSINT runtime — load env keys and auto-start PhoneInfoga API when needed."""

from __future__ import annotations

import atexit
import logging
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

_log = logging.getLogger(__name__)

_proc: subprocess.Popen | None = None
_ready = False


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def find_phoneinfoga_binary() -> Path | None:
    root = _project_root()
    candidates = [
        root / "external_tools" / "bin" / "phoneinfoga.exe",
        root / "external_tools" / "bin" / "phoneinfoga",
        root / "phoneNumber" / "phoneinfoga" / "bin" / "phoneinfoga.exe",
        root / "phoneNumber" / "phoneinfoga" / "bin" / "phoneinfoga",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _api_port() -> int:
    base = os.environ.get("PHONEINFOGA_BASE", "http://127.0.0.1:5000/api")
    return int(urlparse(base).port or 5000)


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _api_healthy() -> bool:
    port = _api_port()
    if not _port_open("127.0.0.1", port, timeout=0.8):
        return False
    try:
        from services.phone_intelligence.scan_all import post_json

        status, _ = post_json(
            f"http://127.0.0.1:{port}/api/v2/numbers",
            {"number": "10000000000"},
            timeout=3,
        )
        return status in (200, 400, 422)
    except Exception:
        return _port_open("127.0.0.1", port, timeout=0.5)


def stop_phoneinfoga_server() -> None:
    global _proc
    if _proc is None:
        return
    try:
        _proc.terminate()
        _proc.wait(timeout=5)
    except Exception:
        try:
            _proc.kill()
        except Exception:
            pass
    _proc = None


def ensure_phoneinfoga_server(*, wait_sec: float = 20.0) -> bool:
    """Start bundled PhoneInfoga API if not already listening."""
    global _proc
    if os.getenv("PHONEINFOGA_AUTOSTART", "true").lower() in ("0", "false", "no"):
        return _api_healthy()

    if _api_healthy():
        return True

    binary = find_phoneinfoga_binary()
    if binary is None:
        _log.info("PhoneInfoga binary not found — using phonenumbers + DDGS fallback only")
        return False

    port = _api_port()
    if _proc is None or _proc.poll() is not None:
        try:
            _proc = subprocess.Popen(
                [str(binary), "serve", "-p", str(port), "--no-client"],
                cwd=str(binary.parent.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            atexit.register(stop_phoneinfoga_server)
            _log.info("Started PhoneInfoga API on port %s (pid %s)", port, _proc.pid)
        except Exception as exc:
            _log.warning("Could not start PhoneInfoga API: %s", exc)
            return False

    deadline = time.monotonic() + max(3.0, wait_sec)
    while time.monotonic() < deadline:
        if _api_healthy():
            return True
        if _proc and _proc.poll() is not None:
            err_tail = ""
            if _proc.stderr:
                try:
                    err_tail = (_proc.stderr.read() or b"").decode(errors="replace")[-400:]
                except Exception:
                    pass
            _log.warning(
                "PhoneInfoga API exited early (code %s)%s",
                _proc.returncode,
                f": {err_tail}" if err_tail else "",
            )
            return False
        time.sleep(0.4)
    return _api_healthy()


def ensure_phone_stack(*, start_api: bool = True) -> None:
    """Load phone API keys from .env files and ensure PhoneInfoga is reachable."""
    from services.phone_intelligence.scan_all import apply_phone_env

    apply_phone_env()
    if start_api:
        ensure_phoneinfoga_server()


def warmup_phone_stack() -> None:
    """Called once on backend startup — no user action required."""
    global _ready
    if _ready:
        return
    try:
        ensure_phone_stack(start_api=True)
    except Exception as exc:
        _log.warning("Phone stack warmup skipped: %s", exc)
    _ready = True
