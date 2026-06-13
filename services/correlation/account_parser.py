"""Extract account profiles from fusion entities for correlation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from schemas.fusion import Entity


@dataclass
class AccountProfile:
    entity_id: str
    platform: str
    handle: str
    value: str
    url: str | None = None
    email: str | None = None
    bio: str | None = None
    avatar_source: str | None = None
    image_path: str | None = None
    location: str | None = None
    text_corpus: str = ""
    posting_times: list[str] = field(default_factory=list)
    fusion_score: float = 0.0
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    verified: bool = False


def _extract_handle(value: str, platform: str, meta: dict[str, Any]) -> str:
    if meta.get("username"):
        return str(meta["username"]).lower().strip()

    if ":" in value and not value.startswith("http"):
        return value.split(":", 1)[1].lower().strip()

    parsed = urlparse(value if "://" in value else f"https://{value}")
    path = parsed.path.strip("/")
    if path:
        return path.split("/")[0].lower()
    host = (parsed.netloc or value).lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(".")[0] if host else platform


def _collect_text(meta: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("about", "aboutMe", "bio", "display_name", "profile_metadata", "details"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
        elif isinstance(val, dict):
            for sub_key in ("FullName", "bio", "about", "description"):
                sub = val.get(sub_key)
                if isinstance(sub, str) and sub.strip():
                    parts.append(sub.strip())
    return " ".join(parts)


def _collect_location(meta: dict[str, Any]) -> str | None:
    for key in ("location", "currentLocation", "gps", "country"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict) and val.get("city"):
            return str(val.get("city", "")) + ", " + str(val.get("country", ""))
    exif = meta.get("exif") or {}
    if isinstance(exif, dict):
        for tag in ("GPSInfo", "City", "Country"):
            if exif.get(tag):
                return str(exif[tag])
    return None


def entity_to_profile(entity: Entity) -> AccountProfile | None:
    if entity.type not in ("account", "email", "image"):
        return None

    meta = dict(entity.metadata or {})
    platform = str(meta.get("platform") or entity.type)
    if platform.startswith("_"):
        return None

    if meta.get("investigation_lead") or meta.get("status") == "rate_limited":
        return None
    if meta.get("check_type") == "dataset_lookup" and not meta.get("verified"):
        return None
    if meta.get("status") == "placeholder":
        return None

    handle = _extract_handle(entity.value, platform, meta)
    email = meta.get("email")
    if isinstance(email, str):
        email = email.lower()

    url = meta.get("url")
    if not url and entity.type == "account" and ("." in entity.value):
        url = entity.value if entity.value.startswith("http") else f"https://{entity.value}"

    bio = _collect_text(meta)
    location = _collect_location(meta)

    avatar = meta.get("avatar_url") or meta.get("profile_url")
    image_path = meta.get("file") if entity.type == "image" else None

    posting_times: list[str] = []
    for key in ("posting_times", "post_times", "activity_hours"):
        val = meta.get(key)
        if isinstance(val, list):
            posting_times.extend(str(v) for v in val)

    return AccountProfile(
        entity_id=entity.entity_id or f"{entity.type}:{entity.value}",
        platform=platform.lower(),
        handle=handle,
        value=entity.value,
        url=url,
        email=email,
        bio=bio or None,
        avatar_source=str(avatar) if avatar else None,
        image_path=str(image_path) if image_path else None,
        location=location,
        text_corpus=bio,
        posting_times=posting_times,
        fusion_score=entity.fusion_score,
        sources=list(entity.sources),
        metadata=meta,
        verified=bool(meta.get("verified") or meta.get("registered")),
    )


def profiles_from_entities(entities: list[Entity], seed_query: str = "") -> list[AccountProfile]:
    profiles: list[AccountProfile] = []
    seen: set[str] = set()
    seed = seed_query.lower().strip()

    for entity in entities:
        profile = entity_to_profile(entity)
        if not profile:
            continue
        if profile.entity_id in seen:
            continue
        seen.add(profile.entity_id)
        profiles.append(profile)

    if seed and "@" not in seed:
        seed_handle = re.sub(r"[^\w.-]", "", seed).lower()
        for profile in profiles:
            if not profile.handle and seed_handle:
                profile.handle = seed_handle

    return profiles
