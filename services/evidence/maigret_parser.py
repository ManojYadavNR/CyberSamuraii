"""Parse Maigret tool payloads into normalized profile fields."""

from __future__ import annotations

from typing import Any

from services.discovery.validators import is_plausible_profile_photo


def parse_maigret_payload(meta: dict[str, Any]) -> dict[str, str]:
    """Extract profile intelligence from Maigret's nested JSON structure."""
    out: dict[str, str] = {}

    ids = meta.get("ids") or {}
    if isinstance(ids, dict):
        for key in ("FullName", "full_name", "name", "fullname"):
            val = ids.get(key)
            if isinstance(val, str) and val.strip():
                out["display_name"] = val.strip()
                break
        for key in ("bio", "about", "description", "summary"):
            val = ids.get(key)
            if isinstance(val, str) and val.strip():
                out["bio"] = val.strip()
                break
        for key in ("location", "country", "city"):
            val = ids.get(key)
            if isinstance(val, str) and val.strip():
                out["location"] = val.strip()
                break
        for key in ("website", "blog", "homepage"):
            val = ids.get(key)
            if isinstance(val, str) and val.strip():
                out["website"] = val.strip()
                break
        for key in ("email", "mail"):
            val = ids.get(key)
            if isinstance(val, str) and val.strip():
                out["email"] = val.strip().lower()
                break
        for key in ("company", "organization", "employer"):
            val = ids.get(key)
            if isinstance(val, str) and val.strip():
                out["organization"] = val.strip()
                break
        for key in ("image", "avatar", "picture", "photo"):
            val = ids.get(key)
            if isinstance(val, str) and val.strip() and is_plausible_profile_photo(val.strip()):
                out["avatar_url"] = val.strip()
                break

    ids_user = meta.get("ids_user") or {}
    if isinstance(ids_user, dict):
        for key in ("username", "uid", "id"):
            val = ids_user.get(key)
            if isinstance(val, str) and val.strip() and "username" not in out:
                out["username"] = val.strip().lower()

    status = meta.get("status") or {}
    if isinstance(status, dict):
        tags = status.get("tags")
        if isinstance(tags, list):
            tag_str = ", ".join(str(t) for t in tags if t)
            if tag_str and "bio" not in out:
                out.setdefault("bio", tag_str)

    return out
