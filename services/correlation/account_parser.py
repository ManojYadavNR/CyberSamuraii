"""Extract account profiles from fusion entities for correlation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from schemas.fusion import Entity
from services.correlation.activity_data import (
    build_behavior_corpus,
    collect_post_snippets,
    collect_timestamps,
    collect_topic_labels,
    extract_hashtags,
    infer_activity_windows,
)
from services.correlation.handle_quality import is_correlatable_handle, is_plausible_handle_for_correlation, normalize_profile_handle
from services.discovery.validators import verify_blocks_account_confirmation


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
    behavior_corpus: str = ""
    posting_times: list[str] = field(default_factory=list)
    activity_windows: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    fusion_score: float = 0.0
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    verified: bool = False


def _extract_handle(value: str, platform: str, meta: dict[str, Any]) -> str:
    return normalize_profile_handle(value, platform, meta)


def _collect_bio_text(meta: dict[str, Any]) -> str:
    """Bio / about fields only — used for text similarity, not behavior."""
    parts: list[str] = []
    for key in ("bio", "about", "aboutMe", "description", "summary"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
        elif isinstance(val, dict):
            for sub_key in ("bio", "about", "description"):
                sub = val.get(sub_key)
                if isinstance(sub, str) and sub.strip():
                    parts.append(sub.strip())
    extracted = meta.get("extracted_intelligence")
    if isinstance(extracted, dict) and extracted.get("bio") and not parts:
        parts.append(str(extracted["bio"]).strip())
    return " ".join(dict.fromkeys(parts))


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
    extracted = meta.get("extracted_intelligence")
    if isinstance(extracted, dict) and isinstance(extracted.get("location"), str):
        return extracted["location"]
    return None


def _merge_extracted_intelligence(meta: dict[str, Any]) -> dict[str, Any]:
    extracted = meta.get("extracted_intelligence") or {}
    if not isinstance(extracted, dict):
        return meta
    for key in (
        "display_name", "bio", "location", "email", "avatar_url", "website",
        "recent_posts", "highlights", "projects", "schools", "organizations",
        "achievements", "public_metadata",
    ):
        if not meta.get(key) and extracted.get(key):
            meta[key] = extracted[key]
    if not meta.get("organization") and extracted.get("organizations"):
        orgs = extracted["organizations"]
        if isinstance(orgs, list) and orgs:
            meta["organization"] = orgs[0]
            meta.setdefault("organizations", orgs)
    return meta


def entity_to_profile(entity: Entity) -> AccountProfile | None:
    if entity.type not in ("account", "email", "image"):
        return None

    meta = dict(entity.metadata or {})
    meta = _merge_extracted_intelligence(meta)

    platform = str(meta.get("platform") or entity.type)
    if platform.startswith("_"):
        return None

    if meta.get("investigation_lead") or meta.get("status") == "rate_limited":
        return None
    if verify_blocks_account_confirmation(meta):
        return None
    if meta.get("status") == "unavailable":
        return None
    if entity.type == "account" and not (meta.get("verified") or meta.get("registered")):
        return None
    if meta.get("corroboration_status") == "probe":
        return None
    if meta.get("check_type") == "dataset_lookup" and not meta.get("verified"):
        return None
    if meta.get("status") == "placeholder":
        return None

    handle = _extract_handle(entity.value, platform, meta)
    url = meta.get("url")
    if not url and entity.type == "account" and ("." in entity.value):
        url = entity.value if entity.value.startswith("http") else f"https://{entity.value}"

    if not is_plausible_handle_for_correlation(handle):
        return None

    email = meta.get("email")
    if isinstance(email, str):
        email = email.lower()

    bio = _collect_bio_text(meta)
    topics = collect_topic_labels(meta)
    text_corpus = bio or ""
    if topics:
        text_corpus = " ".join(dict.fromkeys([p for p in [text_corpus, *topics[:6]] if p])).strip()
    location = _collect_location(meta)

    avatar = (
        meta.get("avatar_url")
        or meta.get("profile_image")
        or meta.get("picture")
        or meta.get("profile_pic_url")
    )
    if not avatar:
        from services.evidence.maigret_parser import parse_maigret_payload
        avatar = parse_maigret_payload(meta).get("avatar_url")
    image_path = meta.get("file") if entity.type == "image" else None

    posts = collect_post_snippets(meta)
    posting_times = collect_timestamps(meta, posts)
    hashtags = extract_hashtags(posts)
    activity_windows = infer_activity_windows(posting_times)
    behavior_corpus = build_behavior_corpus(posts, hashtags)

    organizations: list[str] = []
    for key in ("organization", "organizations"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            organizations.append(val.strip())
        elif isinstance(val, list):
            organizations.extend(str(v).strip() for v in val if v)

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
        text_corpus=text_corpus or bio or "",
        behavior_corpus=behavior_corpus,
        posting_times=posting_times,
        activity_windows=activity_windows,
        hashtags=hashtags,
        organizations=list(dict.fromkeys(organizations)),
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
        if seed and not is_correlatable_handle(profile.handle, seed_query, profile.url):
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
