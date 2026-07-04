"""Universal Evidence Extraction Engine — extract all intelligence from discovered data."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from schemas.evidence import EvidenceExtractionOutput, FieldProvenance, PlatformProfile, UnifiedPersonProfile
from schemas.fusion import Entity, FusionOutput
from services.account_confirmation import account_confirmed
from services.discovery.validators import (
    extract_emails_from_text,
    extract_urls_from_text,
    is_branding_image_url,
    is_displayable_media_url,
    is_email,
    is_generic_platform_bio,
    is_image_url,
    is_plausible_display_name,
    is_plausible_handle,
    is_plausible_phone,
    is_plausible_profile_photo,
    normalize_domain,
)
from services.discovery.attribution import account_handle_matches_seed, extract_phones_from_text
from services.evidence.document_parser import parse_dork_document
from services.evidence.maigret_parser import parse_maigret_payload
from services.evidence.profile_enricher import enrich_account_profiles
from services.evidence.dork_preview import enrich_dork_document_previews
from services.evidence.google_search_intel import (
    build_google_search_intel,
    merge_search_intel_onto_accounts,
    person_fields_from_google_intel,
)
from services.evidence.samurai_intel import build_samurai_social_intel
from services.google_dorking.filters import dork_hit_displayable
from services.lead_visual.engine import build_lead_visuals
from services.page_screenshot import reset_screenshot_budget
from services.evidence.search_intelligence import extract_all_search_findings
from services.json_utils import is_empty_value

TEXT_KEYS = ("bio", "about", "aboutMe", "description", "details", "profile_metadata")
NAME_KEYS = ("display_name", "name", "full_name", "FullName", "real_name")
LOCATION_KEYS = ("location", "currentLocation", "country", "city")
WEBSITE_KEYS = ("website", "homepage", "blog", "url_user")
IMAGE_KEYS = ("avatar_url", "profile_image", "image", "picture")
ORG_KEYS = ("organization", "organizations", "company", "employer")
PROJECT_KEYS = ("projects", "repos", "repositories")
SCHOOL_KEYS = ("school", "schools", "education")
POST_KEYS = ("recent_posts", "post_captions", "captions")
VIDEO_KEYS = ("videos", "media_video", "video", "video_url")
IMAGE_LIST_KEYS = ("profile_images", "post_images", "images")
USERNAME_KEYS = ("username", "handle", "ids_user")

def _platform_shows_person_intel(meta: dict[str, Any], platform: str, *, field: str = "") -> bool:
    """Show merged person intel only on accounts that actually received it."""
    if not meta.get("correlation_intel_merged"):
        return False
    if field == "school":
        return bool(meta.get("schools"))
    if field == "achievement":
        return bool(meta.get("achievements"))
    return False


def _first_str(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            for sub in val.values():
                if isinstance(sub, str) and sub.strip():
                    return sub.strip()
    return None


def _list_str(data: dict[str, Any], *keys: str) -> list[str]:
    out: list[str] = []
    for key in keys:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            out.append(val.strip())
        elif isinstance(val, list):
            for v in val:
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
                elif isinstance(v, dict):
                    for sub in ("text", "caption", "content", "title", "snippet"):
                        sub_val = v.get(sub)
                        if isinstance(sub_val, str) and sub_val.strip():
                            out.append(sub_val.strip())
                            break
        elif isinstance(val, dict):
            out.extend(str(v).strip() for v in val.values() if isinstance(v, str) and v.strip())
    return out


def _extract_handle(entity: Entity, meta: dict[str, Any]) -> str:
    from services.correlation.handle_quality import normalize_profile_handle

    platform = str(meta.get("platform") or "unknown").lower()
    url = str(meta.get("url") or (entity.value if entity.value.startswith("http") else ""))
    handle = normalize_profile_handle(url or entity.value, platform, meta)
    if handle:
        return handle
    if ":" in entity.value and not entity.value.startswith("http"):
        return entity.value.split(":", 1)[1].lower().strip()
    return platform


def _resolve_seed_email(seed_query: str, seed_email: str | None) -> str | None:
    if seed_email:
        return seed_email.strip()
    if seed_query and "@" in seed_query:
        return seed_query.strip()
    return None


def _is_verified_account(
    entity: Entity,
    *,
    seed_query: str = "",
    seed_email: str | None = None,
) -> bool:
    meta = entity.metadata or {}
    if meta.get("investigation_lead") or meta.get("status") == "rate_limited":
        return False
    if meta.get("check_type") == "dataset_lookup" and not meta.get("verified"):
        return False
    effective_email = _resolve_seed_email(seed_query, seed_email)
    sources = set(entity.sources)
    from services.account_confirmation import is_holehe_email_registration

    if is_holehe_email_registration(meta, sources) and effective_email:
        reg_email = str(meta.get("email") or "").lower().strip()
        if reg_email == effective_email.lower():
            return account_confirmed(meta, sources, seed_email=effective_email)
    if seed_query:
        from services.multi_input import attribution_seed_from_raw

        attr_seed = attribution_seed_from_raw(seed_query) if "|" in seed_query else seed_query.strip()
        if attr_seed and "@" not in attr_seed:
            from services.correlation.handle_quality import is_correlatable_handle, normalize_profile_handle

            url = str(meta.get("url") or entity.value if entity.value.startswith("http") else "")
            platform = str(meta.get("platform") or "")
            handle = normalize_profile_handle(url or entity.value, platform, meta)
            if handle and not is_correlatable_handle(handle, attr_seed, url or None):
                return False
    if meta.get("content_seed_verified") is False:
        return False
    return account_confirmed(meta, sources, seed_email=effective_email)


def _provenance(
    *,
    field: str,
    value: str,
    entity: Entity,
    platform: str,
    strategy: str,
    confidence: float = 0.7,
) -> FieldProvenance:
    source_tool = entity.sources[0] if entity.sources else None
    return FieldProvenance(
        field=field,
        value=value,
        source_entity_id=entity.entity_id,
        source_entity_type=entity.type,
        source_platform=platform,
        source_tool=source_tool,
        source_ref=str(entity.metadata.get("url") or entity.value),
        extraction_strategy=strategy,
        confidence=confidence,
    )


def _collect_text_blob(meta: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in TEXT_KEYS:
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
        elif isinstance(val, dict):
            for sub_key in ("FullName", "bio", "about", "description", "text"):
                sub = val.get(sub_key)
                if isinstance(sub, str) and sub.strip():
                    parts.append(sub.strip())
    return " ".join(parts)


def extract_account_intelligence(entity: Entity, *, seed_query: str = "") -> PlatformProfile | None:
    """Extract all profile intelligence from a discovered account entity."""
    if entity.type != "account":
        return None

    meta = dict(entity.metadata or {})
    platform = str(meta.get("platform") or "unknown").lower()
    if platform.startswith("_"):
        return None

    handle = _extract_handle(entity, meta)
    url = meta.get("url") or (entity.value if entity.value.startswith("http") else None)
    verified = _is_verified_account(entity, seed_query=seed_query)

    # Parse Maigret raw payload if present
    maigret_fields = parse_maigret_payload(meta)
    for key, val in maigret_fields.items():
        if val and key not in meta:
            meta[key] = val

    extracted: list[FieldProvenance] = []
    strategies: set[str] = {"account_profile_extraction"}

    def add_field(field: str, value: str | None, strategy: str, confidence: float = 0.75) -> None:
        if not value or not str(value).strip():
            return
        val = str(value).strip()
        extracted.append(
            _provenance(field=field, value=val, entity=entity, platform=platform, strategy=strategy, confidence=confidence)
        )

    display_name = _first_str(meta, *NAME_KEYS) or maigret_fields.get("display_name")
    bio = _first_str(meta, *TEXT_KEYS) or maigret_fields.get("bio")
    if bio and is_generic_platform_bio(bio):
        bio = None
    location = _first_str(meta, *LOCATION_KEYS) or maigret_fields.get("location")
    website = _first_str(meta, *WEBSITE_KEYS) or maigret_fields.get("website")
    email = _first_str(meta, "email") or maigret_fields.get("email")
    avatar = _first_str(meta, *IMAGE_KEYS) or maigret_fields.get("avatar_url")
    if avatar and not is_plausible_profile_photo(avatar):
        avatar = None

    extra_emails = _list_str(meta, "emails")
    for em in extra_emails:
        if is_email(em):
            add_field("email", em.lower(), "account_email_list", confidence=0.82)

    public_meta = meta.get("public_metadata") if isinstance(meta.get("public_metadata"), dict) else {}
    for stat_key in ("followers", "following", "posts", "videos", "subscribers", "public_repos", "repos"):
        val = public_meta.get(stat_key)
        if val is not None and str(val).strip():
            add_field("profile_stat", f"{stat_key}: {val}", "account_public_stat", confidence=0.76)

    highlights = meta.get("highlights")
    if isinstance(highlights, list):
        for h in highlights[:5]:
            if isinstance(h, str) and h.strip():
                add_field("recent_post", h.strip(), "account_highlight", confidence=0.74)

    add_field("display_name", display_name, "account_display_name")
    add_field("bio", bio, "account_bio")
    add_field("location", location, "account_location")
    add_field("website", website, "account_website")
    add_field("email", email, "account_email", confidence=0.85)
    add_field("avatar_url", avatar, "account_profile_image")

    organizations = _list_str(meta, *ORG_KEYS)
    if maigret_fields.get("organization"):
        organizations.append(maigret_fields["organization"])
    for org in sorted(set(organizations)):
        add_field("organization", org, "account_organization")

    projects = _list_str(meta, *PROJECT_KEYS)
    for project in sorted(set(projects)):
        add_field("project", project, "account_project")

    schools = _list_str(meta, *SCHOOL_KEYS)
    if _platform_shows_person_intel(meta, platform, field="school"):
        for school in sorted(set(schools)):
            add_field("school", school, "account_education")

    achievement = _first_str(meta, "achievement")
    if achievement and _platform_shows_person_intel(meta, platform, field="achievement"):
        add_field("achievement", achievement, "account_achievement", confidence=0.8)

    for post in _list_str(meta, *POST_KEYS)[:5]:
        add_field("recent_post", post, "account_recent_post", confidence=0.72)

    for ts in _list_str(meta, "posting_times", "post_times")[:12]:
        add_field("posting_time", ts, "account_posting_time", confidence=0.7)

    if _platform_shows_person_intel(meta, platform, field="achievement"):
        for item in _list_str(meta, "achievements")[:6]:
            add_field("achievement", item, "account_achievement", confidence=0.78)

    for vid in _list_str(meta, *VIDEO_KEYS)[:8]:
        add_field("video", vid, "account_video", confidence=0.76)
        title = display_name or handle or platform
        add_field("media_video", f"{title}|{vid}", "account_media_video", confidence=0.75)

    for img in _list_str(meta, *IMAGE_LIST_KEYS)[:10]:
        if not img.startswith("http"):
            continue
        if is_plausible_profile_photo(img):
            add_field("avatar_url", img, "account_profile_image", confidence=0.78)
        elif is_displayable_media_url(img):
            add_field("image", img, "account_gallery_image", confidence=0.72)

    visual_assets = meta.get("visual_assets")
    if isinstance(visual_assets, list):
        for asset in visual_assets[:12]:
            if not isinstance(asset, dict):
                continue
            kind = str(asset.get("type") or "image")
            url = str(asset.get("url") or "")
            thumb = str(asset.get("thumbnail_url") or url)
            title = str(asset.get("title") or kind)
            if not url.startswith("http"):
                continue
            if kind == "video":
                add_field("media_video", f"{title}|{url}", "account_visual_video", confidence=0.76)
                if thumb.startswith("http") and thumb != url:
                    add_field("thumbnail_url", thumb, "account_video_thumbnail", confidence=0.74)
            elif kind == "avatar" and is_plausible_profile_photo(thumb):
                add_field("avatar_url", thumb, "account_visual_avatar", confidence=0.8)
            elif kind == "screenshot" and thumb.startswith(("/api/", "http")):
                add_field("image", thumb, "account_page_screenshot", confidence=0.74)
            elif is_displayable_media_url(thumb):
                add_field("image", thumb, "account_visual_image", confidence=0.75)

    post_images = meta.get("post_images")
    if isinstance(post_images, list):
        for img in post_images[:8]:
            if isinstance(img, str) and img.startswith("http"):
                if is_plausible_profile_photo(img):
                    add_field("avatar_url", img, "account_post_image", confidence=0.7)
                elif is_image_url(img) and not is_branding_image_url(img):
                    add_field("image", img, "account_post_image", confidence=0.68)

    aliases = _list_str(meta, "aliases", "aka")
    usernames = _list_str(meta, *USERNAME_KEYS)
    if is_plausible_handle(handle):
        usernames.append(handle)
    for alias in sorted(set(aliases)):
        if is_plausible_handle(alias):
            add_field("alias", alias, "account_alias")
    for uname in sorted(set(usernames)):
        if is_plausible_handle(uname):
            add_field("username", uname, "account_username")

    public_links: list[str] = []
    if url:
        public_links.append(str(url))
    for link in extract_urls_from_text(_collect_text_blob(meta)):
        public_links.append(link)
    for link in sorted(set(public_links)):
        add_field("public_link", link, "account_public_link")

    text_blob = _collect_text_blob(meta)
    for found_email in extract_emails_from_text(text_blob):
        add_field("email", found_email, "account_bio_email", confidence=0.8)
    for found_phone in extract_phones_from_text(text_blob):
        if is_plausible_phone(found_phone):
            add_field("phone", found_phone, "account_bio_phone", confidence=0.78)
    for found_url in extract_urls_from_text(text_blob):
        if is_plausible_profile_photo(found_url):
            add_field("avatar_url", found_url, "account_bio_image")
        else:
            domain = normalize_domain(found_url)
            if domain:
                add_field("website", domain, "account_bio_website")

    if meta.get("registered") and "holehe" in (entity.sources or []):
        reg_email = str(meta.get("email") or "").lower().strip()
        if reg_email and is_email(reg_email):
            add_field("email", reg_email, "holehe_registration", confidence=0.88)
            add_field(
                "registration",
                f"Email registered on {platform}",
                "holehe_registration",
                confidence=0.88,
            )

    public_metadata = {
        k: v for k, v in meta.items()
        if k not in ("source_details",) and not is_empty_value(v)
    }

    return PlatformProfile(
        entity_id=entity.entity_id,
        platform=platform,
        handle=handle,
        url=str(url) if url else None,
        verified=verified,
        sources=list(entity.sources),
        fusion_score=entity.fusion_score,
        display_name=display_name,
        bio=bio,
        location=location,
        website=website,
        email=email.lower() if email and is_email(email) else email,
        avatar_url=avatar,
        organizations=sorted(set(organizations)),
        aliases=[a for a in aliases if is_plausible_handle(a)],
        usernames=sorted({u for u in usernames if is_plausible_handle(u)}),
        public_links=sorted(set(public_links)),
        public_metadata=public_metadata,
        extracted_fields=extracted,
    )


def extract_website_intelligence(entity: Entity) -> list[FieldProvenance]:
    if entity.type != "domain":
        return []
    meta = dict(entity.metadata or {})
    platform = str(meta.get("platform") or entity.value).lower()
    extracted: list[FieldProvenance] = []
    domain = normalize_domain(entity.value) or entity.value

    def add(field: str, value: str, strategy: str) -> None:
        extracted.append(
            _provenance(field=field, value=value, entity=entity, platform=platform, strategy=strategy)
        )

    add("domain", domain, "website_domain")
    text = _collect_text_blob(meta)
    for email in extract_emails_from_text(text):
        add("email", email, "website_email_extraction")
    for url in extract_urls_from_text(text):
        if "contact" in url.lower() or "about" in url.lower():
            add("public_link", url, "website_contact_page")
        else:
            add("public_link", url, "website_social_link")
    for org in _list_str(meta, *ORG_KEYS):
        add("organization", org, "website_organization")
    return extracted


def extract_image_intelligence(entity: Entity) -> list[FieldProvenance]:
    if entity.type != "image":
        return []
    meta = dict(entity.metadata or {})
    platform = str(meta.get("platform") or "image").lower()
    extracted: list[FieldProvenance] = []
    image_val = str(meta.get("source") or meta.get("file") or entity.value)

    def add(field: str, value: str, strategy: str, confidence: float = 0.7) -> None:
        extracted.append(
            _provenance(
                field=field,
                value=value,
                entity=entity,
                platform=platform,
                strategy=strategy,
                confidence=confidence,
            )
        )

    add("image_url", image_val, "image_source_reference")

    if meta.get("gps_coordinates") or meta.get("latitude"):
        gps = meta.get("gps_coordinates") or f"{meta.get('latitude')},{meta.get('longitude')}"
        add("location", str(gps), "image_gps_extraction", 0.9)
    if meta.get("face_count") is not None:
        add("face_count", str(meta["face_count"]), "image_face_count", 0.88)
    if meta.get("face_quality_score") is not None:
        add("face_quality_score", str(meta["face_quality_score"]), "image_face_quality", 0.85)
    if meta.get("embedding_signature"):
        add("face_embedding", str(meta["embedding_signature"]), "image_face_embedding", 0.82)
    if meta.get("perceptual_hashes"):
        for name, hval in meta["perceptual_hashes"].items():
            add(f"perceptual_hash_{name}", str(hval), "image_fingerprint", 0.92)
    if meta.get("similarity_signature"):
        add("similarity_signature", str(meta["similarity_signature"]), "image_orb_fingerprint", 0.86)
    if meta.get("crop_path") or meta.get("face_crop"):
        add("face_crop", str(meta.get("crop_path") or image_val), "image_face_crop", 0.8)

    for key in ("similarity_matches", "linked_profiles", "matches"):
        val = meta.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    add("linked_profile", item, "image_linked_profile")
                elif isinstance(item, dict):
                    ref = item.get("url") or item.get("profile") or item.get("username")
                    if ref:
                        add("linked_profile", str(ref), "image_similarity_match")

    exif = meta.get("exif") or meta.get("metadata", {}).get("exif") or {}
    if isinstance(exif, dict):
        for tag in ("DateTimeOriginal", "DateTime", "Make", "Model", "Software"):
            if exif.get(tag):
                add(f"image_metadata_{tag.lower()}", str(exif[tag]), "image_metadata_extraction", 0.84)
        for tag, val in exif.items():
            if val and tag not in ("DateTimeOriginal", "DateTime", "Make", "Model", "Software"):
                add(f"image_metadata_{tag}", str(val), "image_metadata_extraction")
    return extracted


def extract_email_intelligence(entity: Entity) -> list[FieldProvenance]:
    if entity.type != "email":
        return []
    meta = dict(entity.metadata or {})
    extracted: list[FieldProvenance] = []
    email = entity.value.lower()
    platform = str(meta.get("platform") or "email")

    def add(field: str, value: str, strategy: str) -> None:
        extracted.append(
            _provenance(field=field, value=value, entity=entity, platform=platform, strategy=strategy, confidence=0.85)
        )

    strategy = "image_ocr_extraction" if meta.get("intel_engine") == "image_intelligence" else (
        "username_attributed_discovery" if meta.get("username_attributed") else "email_discovery"
    )
    add("email", email, strategy)
    if meta.get("gravatar_url"):
        add("avatar_url", str(meta["gravatar_url"]), "email_gravatar_lookup")
    if meta.get("display_name"):
        add("display_name", str(meta["display_name"]), "email_gravatar_name")
    return extracted


def extract_phone_intelligence(entity: Entity) -> list[FieldProvenance]:
    if entity.type != "phone":
        return []
    meta = dict(entity.metadata or {})
    extracted: list[FieldProvenance] = []
    platform = str(meta.get("platform") or "phone")

    def add(field: str, value: str, strategy: str) -> None:
        extracted.append(
            _provenance(field=field, value=value, entity=entity, platform=platform, strategy=strategy, confidence=0.8)
        )

    strategy = "image_ocr_extraction" if meta.get("intel_engine") == "image_intelligence" else "username_attributed_discovery"
    add("phone", entity.value.strip(), strategy)
    return extracted


def _extract_enriched_profile_fields(entity: Entity) -> list[FieldProvenance]:
    """Fields from deep platform scrape merged into entity metadata."""
    meta = dict(entity.metadata or {})
    if not meta.get("enrichment_source"):
        return []
    platform = str(meta.get("platform") or "web").lower()
    extracted: list[FieldProvenance] = []

    def add(field: str, value: str, strategy: str, confidence: float = 0.78) -> None:
        extracted.append(
            _provenance(field=field, value=value, entity=entity, platform=platform, strategy=strategy, confidence=confidence)
        )

    for field, strategy, confidence in (
        ("display_name", "deep_display_name", 0.8),
        ("bio", "deep_bio", 0.78),
        ("location", "deep_location", 0.76),
        ("organization", "deep_organization", 0.76),
        ("website", "deep_website", 0.74),
        ("email", "deep_email", 0.85),
        ("avatar_url", "deep_avatar", 0.8),
        ("achievement", "deep_achievement", 0.78),
        ("username", "deep_username", 0.82),
    ):
        val = meta.get(field)
        if isinstance(val, str) and val.strip():
            add(field if field != "avatar_url" else "avatar_url", val.strip(), strategy, confidence)

    for em in _list_str(meta, "emails"):
        if is_email(em):
            add("email", em.lower(), "deep_email_list", 0.84)

    pm = meta.get("public_metadata") if isinstance(meta.get("public_metadata"), dict) else {}
    for stat_key in ("followers", "following", "posts", "videos", "subscribers", "public_repos"):
        if pm.get(stat_key) is not None:
            add("profile_stat", f"{stat_key}:{pm[stat_key]}", "deep_public_stat", 0.72)

    for school in _list_str(meta, *SCHOOL_KEYS):
        add("school", school, "deep_education")
    for project in _list_str(meta, *PROJECT_KEYS):
        add("project", project, "deep_project")
    for achievement in _list_str(meta, "achievements"):
        add("achievement", achievement, "deep_achievement", 0.78)
    for post in _list_str(meta, *POST_KEYS)[:8]:
        add("recent_post", post, "deep_recent_post", confidence=0.72)
    for highlight in _list_str(meta, "highlights")[:5]:
        add("recent_post", highlight, "deep_highlight", confidence=0.74)
    for vid in _list_str(meta, *VIDEO_KEYS)[:6]:
        add("video", vid, "deep_video", confidence=0.76)
        add("media_video", f"Video|{vid}", "deep_media_video", confidence=0.75)
    for img in _list_str(meta, *IMAGE_LIST_KEYS)[:8]:
        if is_plausible_profile_photo(img):
            add("avatar_url", img, "deep_gallery_avatar", confidence=0.76)
        elif is_image_url(img) and not is_branding_image_url(img):
            add("image", img, "deep_gallery_image", confidence=0.72)
    shot = meta.get("page_screenshot_url")
    if isinstance(shot, str) and shot.strip():
        add("image", shot.strip(), "deep_page_screenshot", confidence=0.74)
    preview = meta.get("preview_image_url")
    if isinstance(preview, str) and preview.strip():
        add("image", preview.strip(), "deep_page_preview", confidence=0.76)
    post_images = meta.get("post_images")
    if isinstance(post_images, list):
        for img in post_images[:6]:
            if isinstance(img, str) and img.startswith("http"):
                if is_plausible_profile_photo(img):
                    add("avatar_url", img, "deep_post_image", confidence=0.7)
                elif is_image_url(img) and not is_branding_image_url(img):
                    add("image", img, "deep_post_image", confidence=0.68)
    return extracted


def extract_document_intelligence(entity: Entity, *, seed_query: str = "") -> list[FieldProvenance]:
    meta = dict(entity.metadata or {})
    if meta.get("reverse_image_match") and not meta.get("hash_verified"):
        return []
    text = _collect_text_blob(meta) or str(meta.get("content") or meta.get("text") or "")
    title = str(meta.get("title") or "")
    snippet = str(meta.get("snippet") or "")
    if not text.strip() and not title and not snippet:
        return []
    platform = str(meta.get("platform") or entity.type)
    extracted: list[FieldProvenance] = []

    def add(field: str, value: str, strategy: str, confidence: float = 0.7) -> None:
        extracted.append(
            _provenance(field=field, value=value, entity=entity, platform=platform, strategy=strategy, confidence=confidence)
        )

    full_text = f"{title} {snippet} {text}".strip()

    if meta.get("check_type") == "google_dork" and seed_query:
        for field, value, strategy, confidence in parse_dork_document(meta, entity_value=entity.value, seed_query=seed_query):
            add(field, value, strategy, confidence)

    page_url = str(meta.get("url") or entity.value or "")
    preview = meta.get("preview_image_url")
    shot = meta.get("page_screenshot_url")
    if isinstance(preview, str) and preview.strip():
        add("image", preview.strip(), "dork_page_preview", 0.76)
    elif isinstance(shot, str) and shot.strip():
        add("image", shot.strip(), "dork_page_screenshot", 0.74)
    if isinstance(shot, str) and shot.strip() and page_url.startswith("http"):
        title = title or "Web page"
        add("search_hit", f"{title}|{page_url}", "dork_screenshot_source", 0.72)

    for name in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", full_text):
        if meta.get("reverse_image_match") and not meta.get("hash_verified"):
            continue
        add("name", name, "document_name_extraction")
    for org in _list_str(meta, *ORG_KEYS):
        add("organization", org, "document_organization")
    for url in extract_urls_from_text(full_text):
        add("public_link", url, "document_reference")
        
    if meta.get("is_comment"):
        add("comment", text, "social_media_comment", 0.95)
        if meta.get("postUrl"):
            add("public_link", meta.get("postUrl"), "commented_post")
            
    return extracted


def _dedupe_provenance(items: list[FieldProvenance]) -> list[FieldProvenance]:
    seen: set[tuple[str, str, str]] = set()
    out: list[FieldProvenance] = []
    for item in sorted(items, key=lambda p: -p.confidence):
        key = (item.field, item.value.lower(), item.source_platform or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_unified_person_profile(
    platform_profiles: list[PlatformProfile],
    *,
    seed_query: str,
    extra_fields: list[FieldProvenance] | None = None,
    seed_email: str | None = None,
) -> UnifiedPersonProfile:
    """Merge multi-platform evidence into one person-centric profile."""
    verified = [p for p in platform_profiles if p.verified]
    all_profiles = platform_profiles
    primary_profiles = verified or all_profiles

    def collect(field: str, *, source_profiles: list[PlatformProfile] | None = None) -> list[FieldProvenance]:
        profiles = source_profiles or all_profiles
        items: list[FieldProvenance] = []
        for profile in profiles:
            for fp in profile.extracted_fields:
                if fp.field == field or (field == "name" and fp.field == "display_name"):
                    items.append(fp)
        if extra_fields:
            items.extend(fp for fp in extra_fields if fp.field == field)
        if field == "bio":
            items = [fp for fp in items if not is_generic_platform_bio(fp.value)]
        if field in ("display_name", "name"):
            items = [fp for fp in items if is_plausible_display_name(fp.value)]
        if field == "avatar_url":
            items = [fp for fp in items if is_plausible_profile_photo(fp.value)]
        return _dedupe_provenance(items)

    names = collect("display_name", source_profiles=primary_profiles)
    if not names:
        names = collect("name", source_profiles=primary_profiles)
    if seed_query:
        seed_names = [
            n for n in names
            if any(
                account_handle_matches_seed(pp.handle, seed_query, pp.url)
                for pp in primary_profiles
                if any(fp.value == n.value and fp.source_entity_id == pp.entity_id for fp in pp.extracted_fields)
            )
        ]
        if seed_names:
            names = _dedupe_provenance(seed_names + [n for n in names if n not in seed_names])

    profile = UnifiedPersonProfile(
        seed_query=seed_query,
        platform_count=len(all_profiles),
        verified_platform_count=len(verified),
        names=names,
        aliases=collect("alias", source_profiles=primary_profiles),
        usernames=collect("username", source_profiles=primary_profiles),
        bios=collect("bio", source_profiles=primary_profiles),
        locations=collect("location", source_profiles=primary_profiles),
        emails=collect("email", source_profiles=primary_profiles),
        websites=collect("website", source_profiles=primary_profiles),
        organizations=collect("organization", source_profiles=primary_profiles),
        images=_dedupe_provenance(
            [fp for fp in collect("avatar_url") if is_plausible_profile_photo(fp.value)]
            + [
                fp for fp in collect("image")
                if is_image_url(fp.value) and not is_branding_image_url(fp.value)
            ]
            + [
                fp for fp in collect("image_url")
                if is_image_url(fp.value) and not is_branding_image_url(fp.value)
            ]
        ),
        public_links=collect("public_link"),
        search_findings=_dedupe_provenance(
            collect("search_hit") + collect("search_snippet") + [
                fp for fp in (extra_fields or [])
                if fp.field in (
                    "search_hit", "search_snippet", "search_category",
                    "repository", "blog", "forum", "document", "video", "image", "archived", "mention",
                    "news", "article", "publication", "event", "achievement", "email",
                )
            ]
        ),
        comments=_dedupe_provenance(collect("comment")),
        platform_profiles=sorted(
            [
                p for p in verified
                if account_confirmed(
                    {
                        **(p.public_metadata or {}),
                        "platform": p.platform,
                        "url": p.url,
                        "handle": p.handle,
                        "username": p.handle,
                        "verified": p.verified,
                        "email": p.email or seed_email,
                    },
                    set(p.sources or []),
                    seed_email=seed_email,
                )
            ],
            key=lambda p: (-len(p.extracted_fields), -(p.fusion_score or 0), p.platform),
        ),
    )

    if profile.names:
        profile.primary_display_name = profile.names[0].value
    if profile.bios:
        profile.primary_bio = profile.bios[0].value
    if profile.locations:
        profile.primary_location = profile.locations[0].value
    if profile.images:
        verified_images = collect("avatar_url", source_profiles=primary_profiles)
        profile.primary_avatar = (verified_images[0].value if verified_images else profile.images[0].value)

    return profile


def enrich_entity_metadata(entity: Entity, platform_profile: PlatformProfile | None) -> Entity:
    """Write extracted intelligence back onto the entity for downstream correlation."""
    if not platform_profile:
        return entity

    meta = dict(entity.metadata or {})
    field_map = {
        "display_name": platform_profile.display_name,
        "bio": platform_profile.bio,
        "location": platform_profile.location,
        "website": platform_profile.website,
        "email": platform_profile.email,
        "avatar_url": platform_profile.avatar_url,
        "username": platform_profile.handle,
        "organizations": platform_profile.organizations,
        "aliases": platform_profile.aliases,
    }
    for key, val in field_map.items():
        if val and not meta.get(key):
            meta[key] = val

    meta["extracted_intelligence"] = platform_profile.model_dump()
    meta["intelligence_field_count"] = len(platform_profile.extracted_fields)
    entity.metadata = meta
    return entity


class UniversalEvidenceExtractionEngine:
    """Extract all useful intelligence from every discovered entity."""

    async def extract(
        self,
        fusion: FusionOutput,
        *,
        seed_query: str,
        seed_email: str | None = None,
        enrich_public_profiles: bool = True,
        tool_results: list | None = None,
        run_linguistic: bool = True,
    ) -> tuple[FusionOutput, EvidenceExtractionOutput]:
        entities = list(fusion.deduplicated_entities or [])
        platform_profiles: list[PlatformProfile] = []
        extra_fields: list[FieldProvenance] = []
        strategies: set[str] = set()
        fields_extracted = 0
        effective_email = _resolve_seed_email(seed_query, seed_email)

        reset_screenshot_budget()

        if effective_email:
            extra_fields.append(
                FieldProvenance(
                    field="email",
                    value=effective_email.lower(),
                    source_tool="user_input",
                    extraction_strategy="investigation_seed",
                    confidence=0.95,
                )
            )

        from services.evidence.google_search_intel import promote_attributed_profile_documents

        if seed_query and promote_attributed_profile_documents(entities, seed_query=seed_query):
            strategies.add("dork_profile_promotion")

        account_entities = [
            e for e in entities
            if e.type == "account" and _is_verified_account(e, seed_query=seed_query, seed_email=effective_email)
        ]

        if enrich_public_profiles:
            enriched_meta = await enrich_account_profiles(entities, seed_query=seed_query)
            for entity in entities:
                if entity.entity_id not in enriched_meta:
                    continue
                payload = enriched_meta[entity.entity_id]
                entity.metadata = {**(entity.metadata or {}), **payload}
                strategies.add("parallel_profile_enrichment")

        search_findings = extract_all_search_findings(entities, seed_query=seed_query)
        extra_fields.extend(search_findings)
        fields_extracted += len(search_findings)
        if search_findings:
            strategies.add("search_intelligence")

        dork_previews = await enrich_dork_document_previews(entities, seed_query=seed_query)
        if dork_previews:
            strategies.add("dork_page_preview")

        for entity in entities:
            if entity.type == "account":
                if not _is_verified_account(entity, seed_query=seed_query, seed_email=effective_email):
                    continue
                pp = extract_account_intelligence(entity, seed_query=seed_query)
                if pp:
                    platform_profiles.append(pp)
                    fields_extracted += len(pp.extracted_fields)
                    strategies.update(fp.extraction_strategy for fp in pp.extracted_fields)
                    enrich_entity_metadata(entity, pp)
            elif entity.type == "domain":
                fields = extract_website_intelligence(entity)
                extra_fields.extend(fields)
                fields_extracted += len(fields)
                strategies.update(f.extraction_strategy for f in fields)
            elif entity.type == "image":
                fields = extract_image_intelligence(entity)
                extra_fields.extend(fields)
                fields_extracted += len(fields)
                strategies.update(f.extraction_strategy for f in fields)
            elif entity.type == "phone":
                meta = entity.metadata or {}
                if not meta.get("username_attributed") and meta.get("intel_engine") != "image_intelligence":
                    continue
                fields = extract_phone_intelligence(entity)
                extra_fields.extend(fields)
                fields_extracted += len(fields)
                strategies.update(f.extraction_strategy for f in fields)
            elif entity.type == "email":
                meta = entity.metadata or {}
                if "holehe" in (entity.sources or []) and not meta.get("username_attributed"):
                    if (
                        meta.get("intel_engine") != "image_intelligence"
                        and meta.get("category") != "ocr"
                        and not (
                            effective_email
                            and entity.value.lower() == effective_email.lower()
                        )
                    ):
                        continue
                fields = extract_email_intelligence(entity)
                extra_fields.extend(fields)
                fields_extracted += len(fields)
                strategies.update(f.extraction_strategy for f in fields)
            else:
                fields = extract_document_intelligence(entity, seed_query=seed_query)
                meta = entity.metadata or {}
                if meta.get("enrichment_source"):
                    fields.extend(_extract_enriched_profile_fields(entity))
                if fields:
                    extra_fields.extend(fields)
                    fields_extracted += len(fields)
                    strategies.update(f.extraction_strategy for f in fields)

        lead_output = await build_lead_visuals(
            entities,
            seed_query=seed_query,
            platform_profiles=platform_profiles,
        )
        lead_visual_payload: list[dict[str, Any]] = []
        if lead_output.leads:
            strategies.add("lead_visual_engine")
            strategies.update(lead_output.strategies)
            lead_field_start = len(extra_fields)
            for lead in lead_output.leads:
                if lead.lead_type != "profile" and seed_query and not dork_hit_displayable(
                    url=lead.url,
                    title=lead.title,
                    snippet=lead.snippet,
                    seed_query=seed_query,
                    dork_query="",
                ):
                    continue
                lead_visual_payload.append(lead.model_dump())
                if lead.image_url:
                    extra_fields.append(FieldProvenance(
                        field="image",
                        value=lead.image_url,
                        source_platform=lead.source_domain,
                        source_tool="lead_visual_engine",
                        source_ref=lead.url,
                        extraction_strategy=lead.visual_source or "lead_visual",
                        confidence=lead.confidence,
                    ))
                extra_fields.append(FieldProvenance(
                    field="search_hit",
                    value=f"{lead.title}|{lead.url}",
                    source_platform=lead.source_domain,
                    source_tool="lead_visual_engine",
                    source_ref=lead.url,
                    extraction_strategy=f"lead_{lead.lead_type}",
                    confidence=lead.confidence,
                ))
                if lead.snippet:
                    extra_fields.append(FieldProvenance(
                        field="search_snippet",
                        value=lead.snippet[:1200],
                        source_platform=lead.source_domain,
                        source_tool="lead_visual_engine",
                        source_ref=lead.url,
                        extraction_strategy=f"lead_{lead.lead_type}_snippet",
                        confidence=lead.confidence,
                    ))
                if lead.lead_type in ("hackathon", "event", "achievement"):
                    extra_fields.append(FieldProvenance(
                        field="event",
                        value=f"{lead.title}|{lead.url}",
                        source_platform=lead.source_domain,
                        source_tool="lead_visual_engine",
                        source_ref=lead.url,
                        extraction_strategy="lead_event_card",
                        confidence=lead.confidence,
                    ))
                elif lead.lead_type in ("news", "article", "college"):
                    extra_fields.append(FieldProvenance(
                        field="article",
                        value=f"{lead.title}|{lead.url}",
                        source_platform=lead.source_domain,
                        source_tool="lead_visual_engine",
                        source_ref=lead.url,
                        extraction_strategy="lead_article_card",
                        confidence=lead.confidence,
                    ))
            fields_extracted += len(extra_fields) - lead_field_start

        unified = build_unified_person_profile(
            platform_profiles,
            seed_query=seed_query,
            extra_fields=extra_fields,
            seed_email=effective_email,
        )

        discovery_meta = None
        for entity in entities:
            meta = entity.metadata or {}
            if meta.get("check_type") == "google_search_discovery":
                discovery_meta = meta.get("google_search_discovery")
                break

        google_intel = build_google_search_intel(
            entities,
            seed_query=seed_query,
            discovery_meta=discovery_meta if isinstance(discovery_meta, dict) else None,
        )
        from services.evidence.college_enrichment import enrich_google_search_intel_colleges

        google_intel = await enrich_google_search_intel_colleges(google_intel, seed_query=seed_query)

        from services.evidence.confirmed_expansion import expand_from_confirmed_anchors

        expansion = await expand_from_confirmed_anchors(
            entities,
            google_intel,
            seed_query=seed_query,
            budget_sec=55.0,
        )
        if expansion.deep_profiles:
            from services.evidence.confirmed_expansion import apply_deep_profiles_to_intel

            google_intel = apply_deep_profiles_to_intel(google_intel, expansion.deep_profiles)
        if expansion.new_entities:
            entities.extend(expansion.new_entities)
            strategies.update(expansion.strategies)
            google_intel = build_google_search_intel(
                entities,
                seed_query=seed_query,
                discovery_meta=discovery_meta if isinstance(discovery_meta, dict) else None,
            )
            google_intel = await enrich_google_search_intel_colleges(google_intel, seed_query=seed_query)
            for entity in expansion.new_entities:
                if entity.type != "document":
                    continue
                fields = extract_document_intelligence(entity, seed_query=seed_query)
                if fields:
                    extra_fields.extend(fields)
                    fields_extracted += len(fields)
                    strategies.update(f.extraction_strategy for f in fields)

        intel_fields = person_fields_from_google_intel(google_intel, seed_query=seed_query)
        if intel_fields:
            extra_fields.extend(intel_fields)
            fields_extracted += len(intel_fields)

        if (
            intel_fields
            or google_intel.get("highlights")
            or google_intel.get("discovered_keywords")
            or google_intel.get("social_posts")
            or google_intel.get("hackathon_wins")
            or google_intel.get("colleges")
        ):
            strategies.add("google_search_intel")

        merged_accounts = merge_search_intel_onto_accounts(
            entities,
            google_intel,
            seed_query=seed_query,
        )
        if merged_accounts:
            strategies.add("correlation_intel_merge")
            refreshed: set[str] = set()
            for entity in entities:
                if entity.type != "account" or not _is_verified_account(
                    entity, seed_query=seed_query, seed_email=effective_email
                ):
                    continue
                meta = entity.metadata or {}
                if not meta.get("correlation_intel_merged"):
                    continue
                pp = extract_account_intelligence(entity, seed_query=seed_query)
                if not pp:
                    continue
                enrich_entity_metadata(entity, pp)
                if pp.entity_id in refreshed:
                    platform_profiles = [p if p.entity_id != pp.entity_id else pp for p in platform_profiles]
                else:
                    platform_profiles.append(pp)
                    refreshed.add(pp.entity_id)
                fields_extracted += len(pp.extracted_fields)

            unified = build_unified_person_profile(
                platform_profiles,
                seed_query=seed_query,
                extra_fields=extra_fields,
                seed_email=effective_email,
            )

        updated = fusion.model_copy(update={"deduplicated_entities": entities})
        if build_samurai_social_intel(tool_results):
            strategies.add("samurai_social_intel")

        output = EvidenceExtractionOutput(
            entities_enriched=len(platform_profiles) + (1 if extra_fields else 0),
            fields_extracted=fields_extracted,
            platforms_analyzed=len(platform_profiles),
            extraction_strategies=sorted(strategies),
            unified_profile=unified,
            lead_visuals=lead_visual_payload,
            lead_screenshots_captured=lead_output.captured_screenshots,
            google_search_intel=google_intel,
            samurai_social_intel=build_samurai_social_intel(tool_results),
        )
        from services.linguistic.bridge import apply_linguistic_analysis

        if run_linguistic:
            output = apply_linguistic_analysis(
                output,
                seed_query=seed_query,
                tool_results=tool_results,
            )
        return updated, output


evidence_engine = UniversalEvidenceExtractionEngine()
