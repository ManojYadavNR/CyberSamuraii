"""Thin bridge to the bundled Samurai tool — pass input in, return native JSON out."""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from concurrent.futures import TimeoutError as FuturesTimeoutError
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


def _reset_samurai_modules() -> None:
    global _MAIN, _API
    _MAIN = None
    _API = None
    for name in ("samurai_tool_main", "samurai_tool_api"):
        sys.modules.pop(name, None)


def _safe_workers(default: int = 3) -> int:
    """Bounded concurrency — prevents OOM from nested thread pools."""
    try:
        return max(2, min(4, int(os.getenv("SAMURAI_SAFE_WORKERS", str(default)))))
    except ValueError:
        return default


def _probe_facebook_candidates(
    api: Any,
    candidates: list[str],
    *,
    username: str,
    max_workers: int | None = None,
) -> tuple[dict | None, str | None, Exception | None]:
    """Try Facebook slugs in parallel; return first successful full profile."""
    if not candidates:
        return None, None, None

    last_exc: Exception | None = None
    workers = min(max_workers or _safe_workers(), len(candidates))

    def _try(candidate: str) -> tuple[str, dict | Exception]:
        try:
            profile = api._facebook_profile(
                candidate, light=True, fast=False, seed_username=username
            )
            return candidate, profile
        except Exception as exc:
            return candidate, exc

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_try, c) for c in candidates]
        for fut in as_completed(futures):
            candidate, result = fut.result()
            if isinstance(result, dict):
                return result, candidate, None
            last_exc = result
    return None, None, last_exc


def scrape_samurai(
    query: str,
    *,
    fast: bool | None = None,
    on_progress: Any | None = None,
    deadline: float | None = None,
) -> dict[str, Any]:
    """Run Samurai and return full native JSON payloads within a hard deadline.

    Full data fields are always attempted (posts, reels, comments, Facebook,
    similar profiles). Each phase has a time budget so one hung HTTP call cannot
    block past ~3 minutes — partial results are returned instead of hanging.
    """
    _ = fast
    # Full Facebook (about / photos / "Others named…") needs ~80s; run IG in parallel.
    wall = float(os.getenv("SAMURAI_WALL_SEC", "120"))
    if deadline is None:
        deadline = time.monotonic() + max(25.0, wall - 3.0)

    def _progress(detail: str) -> None:
        if on_progress:
            try:
                on_progress(detail)
            except Exception:
                pass

    def _remaining() -> float:
        return deadline - time.monotonic()

    def _run_budgeted(fn, *, budget: float, label: str):
        """Run fn in a worker with a hard timeout; return None on timeout.

        Important: shutdown(wait=False) so a hung HTTP thread cannot block the
        whole investigation past the phase budget.
        """
        rem = _remaining()
        if rem < 2.0:
            out["partial"] = True
            _progress(f"{label} skipped — time budget reached")
            return None
        timeout = min(budget, rem)
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="samurai-phase")
        try:
            fut = pool.submit(fn)
            try:
                return fut.result(timeout=timeout)
            except FuturesTimeoutError:
                out["partial"] = True
                _progress(f"{label} timed out — continuing with data collected so far")
                return None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

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
        "parallel": True,
        "safe_mode": True,
        "partial": False,
    }

    ig_profile: dict[str, Any] | None = None
    fb_profile: dict[str, Any] | None = None
    fb_slug: str | None = None
    fb_resolution: str | None = None
    last_fb_exc: Exception | None = None
    cross: dict | None = None

    # Parallel IG + FB budgets (seconds). Full FB about/photos/similar needs ~80s.
    similar_budget = float(os.getenv("SAMURAI_SIMILAR_BUDGET_SEC", "12"))
    parallel_budget = max(30.0, _remaining() - similar_budget - 2.0)
    ig_budget = float(os.getenv("SAMURAI_IG_BUDGET_SEC", str(parallel_budget)))
    fb_budget = float(os.getenv("SAMURAI_FB_BUDGET_SEC", str(parallel_budget)))
    ig_budget = min(ig_budget, parallel_budget)
    fb_budget = min(fb_budget, parallel_budget)

    def _guess_facebook_slug(ig: dict | None = None) -> str | None:
        """Best-effort public Facebook slug from username / Instagram name."""
        for c in main._facebook_priority_slugs(username):
            if main._is_valid_facebook_slug_candidate(c):
                return c
        for v in main.generate_facebook_slug_variations(username, ig, limit=4):
            if main._is_valid_facebook_slug_candidate(v):
                return v
        dotted = username.strip().lstrip("@").replace("_", ".")
        if main._is_valid_facebook_slug_candidate(dotted):
            return dotted
        clean = username.strip().lstrip("@")
        if main._is_valid_facebook_slug_candidate(clean):
            return clean
        return None

    def _attach_facebook(profile: dict, slug: str, resolution: str) -> None:
        profile = dict(profile)
        profile.pop("raw_pages", None)  # huge HTML — not needed in API/UI payload
        profile["seed_username"] = username
        payload = main.build_facebook_json_payload(profile)
        payload["searched_username"] = username
        out["facebook"] = payload
        out["facebook_slug"] = slug
        out["facebook_resolution"] = resolution

    def _clean_display_name(raw: str | None, slug: str) -> str:
        name = (raw or "").strip()
        # Reject mojibake / garbage Instagram names (e.g. "¶°m×a×n×u×~").
        if name and not any(ch in name for ch in ("¶", "×", "°")) and sum(c.isalpha() for c in name) >= 2:
            return name
        guessed = main._guess_full_names_from_username(username)
        if guessed:
            return guessed[0]
        parts = [p for p in slug.replace(".", " ").replace("_", " ").replace("-", " ").split() if p and not p.isdigit()]
        if parts:
            return " ".join(p[:1].upper() + p[1:] for p in parts)
        return slug

    def _attach_facebook_stub(slug: str | None = None, *, resolution: str = "samurai_username_guess") -> None:
        """Fallback embed-only card when the full scrape cannot finish."""
        if out.get("facebook") and not out["facebook"].get("embed_only"):
            return
        target = slug or fb_slug or _guess_facebook_slug(ig_profile)
        if not target:
            out["facebook_error"] = out.get("facebook_error") or "No Facebook slug candidates"
            return
        ig_name = (ig_profile or {}).get("full_name") if ig_profile else None
        full_name = _clean_display_name(str(ig_name) if ig_name else None, target)
        stub = main.build_minimal_facebook_profile(
            target,
            seed_username=username,
            full_name=full_name,
        )
        _attach_facebook(stub, target, resolution)
        out["partial"] = True

    def _ig_phase():
        return api._instagram_profile(username, fast=False)

    def _fb_phase():
        """Full public Facebook scrape: about, photos, 'Others named…' similar accounts."""
        # Resolve slug instantly (no HTTP) — e.g. manojyadav_.27 → manoj.yadav27
        slug = _guess_facebook_slug(None)
        if not slug:
            raise RuntimeError("No Facebook slug candidates from username")

        # light=True skips wayback; fast=False keeps full embeds + similar profiles.
        profile = api._facebook_profile(
            slug, light=True, fast=False, seed_username=username
        )
        return profile, slug, "samurai_username_slug"

    # ── Phase 1: Instagram + Facebook in parallel (both get the full wall) ──
    _progress("Collecting Instagram & Facebook (about, photos, similar accounts)…")

    ig_exc: Exception | None = None
    fb_exc: Exception | None = None
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="samurai-ig-fb")
    try:
        ig_fut = pool.submit(_ig_phase)
        fb_fut = pool.submit(_fb_phase)
        timeout = max(5.0, min(parallel_budget, _remaining()))
        done, _pending = wait([ig_fut, fb_fut], timeout=timeout)

        if ig_fut in done:
            try:
                ig_profile = ig_fut.result(timeout=0)
            except Exception as exc:
                ig_exc = exc
                ig_profile = None
        else:
            out["partial"] = True
            out["instagram_error"] = "Instagram phase exceeded time budget"
            _progress("Instagram timed out — continuing with data collected so far")
            ig_profile = None

        if fb_fut in done:
            try:
                fb_result = fb_fut.result(timeout=0)
                if isinstance(fb_result, tuple) and len(fb_result) == 3:
                    fb_profile, fb_slug, fb_resolution = fb_result
            except Exception as exc:
                fb_exc = exc
                last_fb_exc = exc
        else:
            out["partial"] = True
            out["facebook_error"] = "Facebook phase exceeded time budget"
            _progress("Facebook timed out — attaching partial profile if available")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    if ig_profile:
        try:
            out["instagram"] = main.build_instagram_json_payload(ig_profile, include_similar=False)
            if not ig_session and out["instagram"]:
                notes = out["instagram"].setdefault("notes", {})
                notes.setdefault(
                    "session_help",
                    "Optional: add IG_SESSIONID to .env for comment text and API fields.",
                )
        except Exception as exc:
            out["instagram_error"] = str(exc)
            ig_profile = None
    elif ig_exc:
        out["instagram_error"] = str(ig_exc)

    if fb_profile and fb_slug:
        try:
            _attach_facebook(fb_profile, fb_slug, fb_resolution or "samurai_username_slug")
        except Exception as exc:
            out["facebook_error"] = str(exc)
            _attach_facebook_stub(fb_slug, resolution=fb_resolution or "samurai_username_guess")
    else:
        if last_fb_exc or fb_exc:
            out["facebook_error"] = str(last_fb_exc or fb_exc)
        _attach_facebook_stub(fb_slug, resolution=fb_resolution or "samurai_username_guess")

    # ── Phase 2: Instagram similar profiles (if time remains) ──
    if out.get("instagram") and _remaining() >= 2.0:
        _progress("Collecting similar Instagram profiles…")

        def _similar_phase():
            return main.build_similar_username_profiles(
                username,
                platform="instagram",
                fast=False,
                limit=6,
                exclude=username,
                verify_exists=True,
                enrich=True,
            )

        similar = _run_budgeted(_similar_phase, budget=similar_budget, label="Similar profiles")
        out["instagram"]["similar_profiles"] = similar if isinstance(similar, list) else []
    elif out.get("instagram"):
        out["instagram"].setdefault("similar_profiles", [])
        out["partial"] = True

    if not out.get("instagram") and not out.get("facebook"):
        errors = [e for e in (out["instagram_error"], out["facebook_error"]) if e]
        raise RuntimeError(errors[0] if errors else "Samurai returned no Instagram or Facebook data")

    _progress("Samurai collection complete")
    return out
