"""Thin bridge to the bundled Samurai tool — pass input in, return native JSON out."""

from __future__ import annotations

import importlib.util
import os
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


def scrape_samurai(query: str, *, fast: bool | None = None) -> dict[str, Any]:
    """Run Samurai's own API helpers and return its native JSON payloads."""
    if fast is None:
        fast = os.getenv("SAMURAI_FAST", "false").strip().lower() in ("1", "true", "yes", "on")

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
        # Full public scrape for the searched username (posts, reels, profile pic).
        ig_profile = api._instagram_profile(username, fast=False)
        out["instagram"] = main.build_instagram_json_payload(ig_profile, include_similar=False)
        if not ig_session and out["instagram"]:
            notes = out["instagram"].setdefault("notes", {})
            notes.setdefault(
                "session_help",
                "Optional: add IG_SESSIONID to .env for comment text and API fields.",
            )
    except Exception as exc:
        out["instagram_error"] = str(exc)

    try:
        cross: dict | None = None
        fb_profile = None
        fb_slug: str | None = None
        fb_resolution: str | None = None
        last_fb_exc: Exception | None = None

        # Prefer direct slug conversion (manojyadavnr → manojYadav / manoj.yadav).
        direct_slug, direct_raw = main.find_facebook_profile_by_username(
            username, ig_profile, seed_username=username
        )
        if direct_raw and direct_slug:
            try:
                fb_profile = api._facebook_profile(
                    direct_slug, light=True, fast=False, seed_username=username
                )
                fb_slug = direct_slug
                fb_resolution = "samurai_username_slug"
            except Exception as exc:
                last_fb_exc = exc
                if direct_raw.get("embed_only"):
                    fb_profile = direct_raw
                else:
                    try:
                        fb_profile = api._facebook_profile(
                            direct_slug, light=True, fast=True, seed_username=username
                        )
                    except Exception:
                        fb_profile = direct_raw
                fb_slug = direct_slug
                fb_resolution = "samurai_username_slug"

        if not fb_profile:
            if ig_profile:
                cross = main.find_facebook_from_instagram_profile(ig_profile, fast=True)
            else:
                guessed = main._guess_full_names_from_username(username)
                stub_profile = {
                    "username": username,
                    "full_name": guessed[0] if guessed else "",
                    "biography": "",
                    "external_url": "",
                }
                cross = main.find_facebook_from_instagram_profile(stub_profile, fast=True)
            out["cross_platform"] = cross
            best = cross.get("best_match") if isinstance(cross, dict) else None
            slug = (best or {}).get("facebook_username")
            if slug:
                slug_candidates = [slug] + [
                    v
                    for v in main.generate_facebook_slug_variations(username, ig_profile, limit=8)
                    if v.lower() != slug.lower()
                ]
                for candidate in slug_candidates[:8]:
                    try:
                        fb_profile = api._facebook_profile(
                            candidate, light=True, fast=True, seed_username=username
                        )
                        fb_slug = candidate
                        fb_resolution = "samurai_cross_platform"
                        break
                    except Exception as exc:
                        last_fb_exc = exc
                        continue
        elif ig_profile:
            try:
                cross = main.find_facebook_from_instagram_profile(ig_profile, fast=True)
                out["cross_platform"] = cross
            except Exception:
                pass

        if fb_profile:
            fb_profile["seed_username"] = username
            out["facebook"] = main.build_facebook_json_payload(fb_profile)
            out["facebook_slug"] = fb_slug
            out["facebook_resolution"] = fb_resolution or "samurai_cross_platform"
            out["facebook"]["searched_username"] = username
        else:
            candidates = main.generate_facebook_slug_variations(username, ig_profile, limit=12)
            guess_slug = next(
                (c for c in main._facebook_priority_slugs(username) if main._is_valid_facebook_slug_candidate(c)),
                None,
            )
            if not guess_slug:
                for candidate in candidates:
                    if candidate.lower() != username.lower() and main._is_valid_facebook_slug_candidate(candidate):
                        guess_slug = candidate
                        break
            if guess_slug:
                try:
                    fb_profile = api._facebook_profile(
                        guess_slug, light=True, fast=False, seed_username=username
                    )
                    fb_profile["seed_username"] = username
                    out["facebook"] = main.build_facebook_json_payload(fb_profile)
                    out["facebook_slug"] = guess_slug
                    out["facebook_resolution"] = "samurai_username_guess"
                    out["facebook"]["searched_username"] = username
                except Exception:
                    stub = main.build_minimal_facebook_profile(
                        guess_slug,
                        seed_username=username,
                        full_name=main._guess_full_names_from_username(username)[0]
                        if main._guess_full_names_from_username(username)
                        else None,
                    )
                    out["facebook"] = main.build_facebook_json_payload(stub)
                    out["facebook_slug"] = guess_slug
                    out["facebook_resolution"] = "samurai_username_guess"
                    out["facebook"]["searched_username"] = username
            elif last_fb_exc:
                out["facebook_error"] = str(last_fb_exc)
            elif isinstance(cross, dict) and cross.get("note"):
                out["facebook_error"] = str(cross["note"])
    except Exception as exc:
        out["facebook_error"] = str(exc)

    # Instagram similar only — Facebook similar comes from the profile fetch (Others named).
    if out.get("instagram"):
        try:
            out["instagram"]["similar_profiles"] = main.build_similar_username_profiles(
                username,
                platform="instagram",
                fast=True,
                limit=6,
                exclude=username,
                verify_exists=True,
                enrich=True,
            )
        except Exception:
            out["instagram"].setdefault("similar_profiles", [])

    if not out.get("instagram") and not out.get("facebook"):
        errors = [e for e in (out["instagram_error"], out["facebook_error"]) if e]
        raise RuntimeError(errors[0] if errors else "Samurai returned no Instagram or Facebook data")

    return out
