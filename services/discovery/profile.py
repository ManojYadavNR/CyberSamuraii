"""Build rich profile intelligence objects from fused entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from schemas.fusion import Entity
from services.discovery.validators import (
    extract_emails_from_text,
    extract_urls_from_text,
    is_image_url,
    is_plausible_handle,
    is_url,
    normalize_domain,
)


@dataclass
class ProfileIntelligence:
    entity_id: str
    entity_type: str
    platform: str = ""
    handle: str = ""
    profile_url: str | None = None
    display_name: str | None = None
    bio: str | None = None
    location: str | None = None
    website: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    organizations: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    website_domains: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


def _first_str(meta: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _list_str(meta: dict[str, Any], *keys: str) -> list[str]:
    out: list[str] = []
    for key in keys:
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            out.append(val.strip())
        elif isinstance(val, list):
            out.extend(str(v).strip() for v in val if isinstance(v, str) and v.strip())
    return out


def _extract_handle_from_entity(entity: Entity, meta: dict[str, Any]) -> str | None:
    explicit = _first_str(meta, "username", "handle")
    if explicit and is_plausible_handle(explicit):
        return explicit.lower()

    value = entity.value or ""
    if ":" in value and not value.startswith("http"):
        handle = value.split(":", 1)[1].strip().lower()
        if is_plausible_handle(handle):
            return handle
    return None


def build_profile_intelligence(entity: Entity) -> ProfileIntelligence:
    meta = dict(entity.metadata or {})
    extracted = meta.get("extracted_intelligence")
    if isinstance(extracted, dict):
        for key in (
            "display_name", "bio", "location", "website", "email", "avatar_url",
            "handle", "organizations", "aliases", "usernames", "public_links",
        ):
            if extracted.get(key) and not meta.get(key):
                meta[key] = extracted[key]
        if extracted.get("organizations") and not meta.get("organization"):
            orgs = extracted["organizations"]
            if isinstance(orgs, list) and orgs:
                meta["organization"] = orgs[0]

    platform = str(meta.get("platform") or entity.type)
    if platform.startswith("_"):
        platform = entity.type

    profile = ProfileIntelligence(
        entity_id=entity.entity_id,
        entity_type=entity.type,
        platform=platform,
        handle=_extract_handle_from_entity(entity, meta) or "",
        profile_url=_first_str(meta, "url", "profile_url") or (entity.value if is_url(entity.value) else None),
        display_name=_first_str(meta, "display_name", "name", "full_name"),
        bio=_first_str(meta, "bio", "about", "aboutMe", "description", "details"),
        location=_first_str(meta, "location", "currentLocation", "country"),
        website=_first_str(meta, "website", "homepage", "blog"),
        email=_first_str(meta, "email"),
        avatar_url=_first_str(meta, "avatar_url", "profile_image", "image"),
        organizations=_list_str(meta, "organization", "organizations", "company", "employer"),
        aliases=_list_str(meta, "aliases", "aka"),
        provenance={
            "source_entity_id": entity.entity_id,
            "source_entity_type": entity.type,
            "source_value": entity.value,
            "sources": list(entity.sources),
            "fusion_score": entity.fusion_score,
        },
    )

    text_blob = " ".join(
        part for part in (profile.bio, profile.display_name, str(meta.get("profile_metadata", ""))) if part
    )
    for email in extract_emails_from_text(text_blob):
        if not profile.email:
            profile.email = email
    for url in extract_urls_from_text(text_blob):
        if is_image_url(url):
            profile.image_urls.append(url)
        else:
            domain = normalize_domain(url)
            if domain:
                profile.website_domains.append(domain)

    if profile.website:
        domain = normalize_domain(profile.website)
        if domain:
            profile.website_domains.append(domain)

    if profile.avatar_url and is_image_url(profile.avatar_url):
        profile.image_urls.append(profile.avatar_url)

    profile.aliases = [
        alias.lower()
        for alias in profile.aliases
        if is_plausible_handle(alias) and alias.lower() != profile.handle
    ]
    profile.website_domains = sorted(set(profile.website_domains))
    profile.image_urls = sorted(set(profile.image_urls))
    profile.organizations = sorted(set(profile.organizations))
    return profile
