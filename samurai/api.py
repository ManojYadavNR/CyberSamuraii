"""HTTP JSON API for Postman — separate Facebook and Instagram endpoints."""

from __future__ import annotations

import os

from flask import Flask, jsonify, request

from main import (
    build_facebook_json_payload,
    build_instagram_json_payload,
    collect_facebook_profile,
    collect_profile,
    download_media,
    enrich_facebook_with_session,
    fetch_facebook_profile,
    fetch_wayback_intel,
    build_investigation_intel,
    find_facebook_from_instagram,
    make_facebook_session,
    parse_facebook_slug,
    parse_username,
)

app = Flask(__name__)

API_DOCS = {
    "service": "samurai-scraper",
    "version": "1.0",
    "endpoints": {
        "health": {
            "method": "GET",
            "url": "/health",
            "description": "Server health check",
        },
        "facebook_get": {
            "method": "GET",
            "url": "/api/facebook/<username>",
            "query_params": {"download": "true|false — download photos/videos to disk"},
            "example": "GET /api/facebook/bhuvan.bhuvii",
        },
        "facebook_post": {
            "method": "POST",
            "url": "/api/facebook",
            "body": {"username": "bhuvan.bhuvii", "download": False},
        },
        "instagram_get": {
            "method": "GET",
            "url": "/api/instagram/<username>",
            "query_params": {"download": "true|false — download post media to disk"},
            "example": "GET /api/instagram/instagram",
        },
        "instagram_post": {
            "method": "POST",
            "url": "/api/instagram",
            "body": {"username": "instagram", "download": False},
        },
        "instagram_to_facebook": {
            "method": "GET",
            "url": "/api/cross-platform/instagram/<username>/facebook",
            "description": "Find likely Facebook account from Instagram username",
            "example": "GET /api/cross-platform/instagram/bhuvanbhuvii/facebook",
        },
    },
    "auth_env_vars": {
        "facebook": ["FB_C_USER", "FB_XS", "FB_COOKIES_FILE"],
        "instagram": ["IG_SESSIONID"],
    },
}


def _bool_param(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _facebook_profile(slug: str, download: bool = False, *, light: bool = False, fast: bool = False, seed_username: str | None = None) -> dict:
    if download:
        return collect_facebook_profile(slug)

    profile = fetch_facebook_profile(slug, fast=fast, seed_username=seed_username)
    profile.setdefault("friends", [])
    profile.setdefault("photos", [])
    profile.setdefault("videos", [])
    profile.setdefault("reels", [])
    profile.setdefault("personal_details", {})
    profile["authenticated"] = False
    profile["investigation"] = build_investigation_intel(profile)
    if not light:
        profile["wayback"] = fetch_wayback_intel(
            profile.get("profile_url") or f"https://www.facebook.com/{slug}"
        )
        session = make_facebook_session()
        if session:
            try:
                profile = enrich_facebook_with_session(profile, session)
            except Exception:
                pass
    return profile


def _instagram_profile(username: str, download: bool = False, *, fast: bool = False) -> dict:
    profile = collect_profile(username, fast=fast)
    profile["platform"] = "instagram"
    profile["seed_username"] = username
    profile["fast"] = fast
    if download:
        profile["download_summary"] = download_media(profile, profile.get("username") or username)
    return profile


def _error_response(message: str, status: int):
    return jsonify({"success": False, "error": message}), status


@app.get("/")
def index():
    return jsonify(API_DOCS)


@app.get("/health")
def health():
    return jsonify({"success": True, "status": "ok", "service": "samurai-scraper"})


# ---------------------------------------------------------------------------
# Facebook API
# ---------------------------------------------------------------------------

@app.get("/api/facebook/<path:username>")
def facebook_get(username: str):
    slug = parse_facebook_slug(username)
    if not slug:
        return _error_response("Invalid Facebook username or profile link.", 400)
    download = _bool_param(request.args.get("download"))
    try:
        profile = _facebook_profile(slug, download=download)
    except ValueError as error:
        return _error_response(str(error), 404)
    except Exception as error:
        return _error_response(f"Facebook fetch failed: {error}", 502)

    payload = build_facebook_json_payload(profile)
    payload["success"] = True
    return jsonify(payload)


@app.post("/api/facebook")
def facebook_post():
    body = request.get_json(silent=True) or {}
    raw = (body.get("username") or body.get("slug") or "").strip()
    if not raw:
        return _error_response(
            "Missing username. Example: {\"username\": \"bhuvan.bhuvii\", \"download\": false}",
            400,
        )
    slug = parse_facebook_slug(raw)
    if not slug:
        return _error_response("Invalid Facebook username or profile link.", 400)
    download = _bool_param(
        str(body.get("download")) if body.get("download") is not None else None,
        default=False,
    )
    try:
        profile = _facebook_profile(slug, download=download)
    except ValueError as error:
        return _error_response(str(error), 404)
    except Exception as error:
        return _error_response(f"Facebook fetch failed: {error}", 502)

    payload = build_facebook_json_payload(profile)
    payload["success"] = True
    return jsonify(payload)


# ---------------------------------------------------------------------------
# Instagram API
# ---------------------------------------------------------------------------

@app.get("/api/instagram/<username>")
def instagram_get(username: str):
    parsed = parse_username(username)
    if not parsed:
        return _error_response("Invalid Instagram username.", 400)
    download = _bool_param(request.args.get("download"))
    try:
        profile = _instagram_profile(parsed, download=download)
    except ValueError as error:
        return _error_response(str(error), 404)
    except Exception as error:
        return _error_response(f"Instagram fetch failed: {error}", 502)

    payload = build_instagram_json_payload(profile)
    payload["success"] = True
    return jsonify(payload)


@app.post("/api/instagram")
def instagram_post():
    body = request.get_json(silent=True) or {}
    raw = (body.get("username") or "").strip()
    if not raw:
        return _error_response(
            "Missing username. Example: {\"username\": \"instagram\", \"download\": false}",
            400,
        )
    parsed = parse_username(raw)
    if not parsed:
        return _error_response("Invalid Instagram username.", 400)
    download = _bool_param(
        str(body.get("download")) if body.get("download") is not None else None,
        default=False,
    )
    try:
        profile = _instagram_profile(parsed, download=download)
    except ValueError as error:
        return _error_response(str(error), 404)
    except Exception as error:
        return _error_response(f"Instagram fetch failed: {error}", 502)

    payload = build_instagram_json_payload(profile)
    payload["success"] = True
    return jsonify(payload)


@app.get("/api/cross-platform/instagram/<username>/facebook")
def instagram_to_facebook(username: str):
    parsed = parse_username(username)
    if not parsed:
        return _error_response("Invalid Instagram username.", 400)
    try:
        result = find_facebook_from_instagram(parsed)
    except ValueError as error:
        return _error_response(str(error), 404)
    except Exception as error:
        return _error_response(f"Cross-platform lookup failed: {error}", 502)
    result["success"] = True
    return jsonify(result)


# ---------------------------------------------------------------------------
# Legacy combined endpoint (optional)
# ---------------------------------------------------------------------------

@app.post("/api/scrape")
def scrape_legacy():
    body = request.get_json(silent=True) or {}
    platform = (body.get("platform") or "").strip().lower()
    username = (body.get("username") or body.get("slug") or "").strip()
    download = _bool_param(
        str(body.get("download")) if body.get("download") is not None else None,
        default=False,
    )

    if platform in ("facebook", "fb"):
        slug = parse_facebook_slug(username)
        if not slug:
            return _error_response("Invalid Facebook username.", 400)
        try:
            profile = _facebook_profile(slug, download=download)
            payload = build_facebook_json_payload(profile)
        except ValueError as error:
            return _error_response(str(error), 404)
        except Exception as error:
            return _error_response(str(error), 502)
        payload["success"] = True
        return jsonify(payload)

    if platform in ("instagram", "ig", "insta"):
        parsed = parse_username(username)
        if not parsed:
            return _error_response("Invalid Instagram username.", 400)
        try:
            profile = _instagram_profile(parsed, download=download)
            payload = build_instagram_json_payload(profile)
        except Exception as error:
            return _error_response(str(error), 502)
        payload["success"] = True
        return jsonify(payload)

    return _error_response(
        "Use /api/facebook or /api/instagram. Legacy /api/scrape needs platform + username.",
        400,
    )


def run_api_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    print(f"Samurai API running at http://{host}:{port}")
    print(f"  Facebook: GET http://{host}:{port}/api/facebook/<username>")
    print(f"  Instagram: GET http://{host}:{port}/api/instagram/<username>")
    print(f"  IG->FB:    GET http://{host}:{port}/api/cross-platform/instagram/<username>/facebook")
    print(f"  Docs:     GET http://{host}:{port}/")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_api_server(
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8080")),
    )
