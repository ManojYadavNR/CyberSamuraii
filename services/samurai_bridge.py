"""Thin bridge to the bundled Samurai tool — pass input in, return native JSON out."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from services.multi_input import parse_investigation_input

SAMURAI_ROOT = Path(__file__).resolve().parents[1] / "samurai"
_MAIN: Any | None = None
_API: Any | None = None
_ENV_LOADED = False


def _ensure_samurai_env() -> None:
    """Load .env from project root and samurai/ so IG_SESSIONID matches CLI usage."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    root = SAMURAI_ROOT.parent
    load_dotenv(root / ".env", override=False)
    load_dotenv(SAMURAI_ROOT / ".env", override=False)
    load_dotenv(SAMURAI_ROOT / ".env.local", override=False)
    _ENV_LOADED = True


def _load_samurai_main():
    global _MAIN
    _ensure_samurai_env()
    if _MAIN is not None:
        return _MAIN

    main_path = SAMURAI_ROOT / "main.py"
    if not main_path.exists():
        raise FileNotFoundError(f"Samurai tool not found at {main_path}")

    spec = importlib.util.spec_from_file_location("samurai_tool_main", main_path)
    if spec is None or spec.loader is None:
        raise ImportError("Failed to load Samurai module spec")

    module = importlib.util.module_from_spec(spec)
    sys.modules["samurai_tool_main"] = module
    spec.loader.exec_module(module)
    _MAIN = module
    return module


def _load_samurai_api():
    global _API
    if _API is not None:
        return _API

    api_path = SAMURAI_ROOT / "api.py"
    if not api_path.exists():
        raise FileNotFoundError(f"Samurai API not found at {api_path}")

    main = _load_samurai_main()
    # api.py does `from main import ...` — point that at Samurai's main module.
    sys.modules["main"] = main

    spec = importlib.util.spec_from_file_location("samurai_tool_api", api_path)
    if spec is None or spec.loader is None:
        raise ImportError("Failed to load Samurai API spec")

    module = importlib.util.module_from_spec(spec)
    sys.modules["samurai_tool_api"] = module
    spec.loader.exec_module(module)
    _API = module
    return module


def samurai_available() -> bool:
    return (SAMURAI_ROOT / "main.py").exists() and (SAMURAI_ROOT / "api.py").exists()


def instagram_session_configured() -> bool:
    _ensure_samurai_env()
    main = _load_samurai_main()
    return bool(main.instagram_sessionid())


def _username_from_query(query: str) -> str:
    parsed = parse_investigation_input(query)
    raw = (parsed.username or parsed.raw).strip().lstrip("@")
    if not raw:
        raise ValueError("Username is required for Samurai")
    main = _load_samurai_main()
    username = main.parse_username(raw)
    if not username:
        raise ValueError("Username is required for Samurai")
    if " " in username and "instagram.com" not in raw.lower():
        username = username.replace(" ", "").lower()
    return username.lower()


# Clear cached Samurai modules so code updates apply without full process restart.
def _reset_samurai_modules() -> None:
    global _MAIN, _API
    _MAIN = None
    _API = None
    for name in ("samurai_tool_main", "samurai_tool_api"):
        sys.modules.pop(name, None)


def scrape_samurai(query: str) -> dict[str, Any]:
    """Run Samurai's own API helpers and return its native JSON payloads."""
    main = _load_samurai_main()
    api = _load_samurai_api()
    username = _username_from_query(query)
    ig_session = main.instagram_sessionid()

    out: dict[str, Any] = {
        "username": username,
        "seed_query": query.strip(),
        "instagram": None,
        "facebook": None,
        "cross_platform": None,
        "facebook_slug": None,
        "facebook_resolution": None,
        "instagram_error": None,
        "facebook_error": None,
        "instagram_session_configured": bool(ig_session),
    }

    ig_profile: dict[str, Any] | None = None
    try:
        ig_profile = api._instagram_profile(username)
        out["instagram"] = main.build_instagram_json_payload(ig_profile)
        if not ig_session and out["instagram"]:
            notes = out["instagram"].setdefault("notes", {})
            notes.setdefault(
                "session_help",
                "Add IG_SESSIONID to .env (or samurai/cookies.txt) and restart the backend for bio + comment text.",
            )
    except Exception as exc:
        out["instagram_error"] = str(exc)

    try:
        if ig_profile:
            cross = main.find_facebook_from_instagram_profile(ig_profile)
        else:
            cross = main.find_facebook_from_instagram(username)
        out["cross_platform"] = cross
        best = cross.get("best_match") if isinstance(cross, dict) else None
        slug = (best or {}).get("facebook_username")
        if slug:
            fb_profile = api._facebook_profile(slug, light=True)
            out["facebook"] = main.build_facebook_json_payload(fb_profile)
            out["facebook_slug"] = slug
            out["facebook_resolution"] = "samurai_cross_platform"
        elif isinstance(cross, dict) and cross.get("note"):
            out["facebook_error"] = str(cross["note"])
    except Exception as exc:
        out["facebook_error"] = str(exc)

    if not out["instagram"] and not out["facebook"]:
        errors = [e for e in (out["instagram_error"], out["facebook_error"]) if e]
        raise RuntimeError(errors[0] if errors else "Samurai returned no Instagram or Facebook data")

    return out
