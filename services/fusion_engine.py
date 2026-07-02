"""
SOCMINT Data Fusion Engine.

Unifies multi-tool OSINT outputs into a single intelligence dataset.
NOT identity matching — only dedupe, normalize, merge, and score evidence.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from schemas.common import ToolResult
from schemas.fusion import Entity, EvidenceRecord, FusionOutput
from services.evidence.maigret_parser import parse_maigret_payload
from services.account_confirmation import USERNAME_TOOLS, account_confirmed
from services.discovery.validators import is_plausible_handle, extract_emails_from_text, normalize_domain, verify_blocks_account_confirmation
from services.json_utils import is_empty_value, to_json_safe

# Reliability tiers: official > api > scraper > heuristic
TIER_BASE: dict[str, float] = {
    "official": 1.0,
    "api": 0.88,
    "scraper": 0.68,
    "heuristic": 0.22,
}

TOOL_RELIABILITY: dict[str, tuple[str, float]] = {
    "sherlock": ("scraper", 0.86),
    "maigret": ("scraper", 0.86),
    "social_analyzer": ("scraper", 0.82),
    "holehe": ("api", 0.91),
    "gravatar": ("api", 0.96),
    "shodan": ("api", 0.94),
    "theharvester": ("scraper", 0.72),
    "spiderfoot": ("api", 0.76),
    "recon_ng": ("scraper", 0.71),
    "image_intel": ("scraper", 0.58),
    "google_dorking": ("api", 0.78),
    "platform_probe": ("scraper", 0.92),
    "samurai": ("scraper", 0.9),
    # Parallel image tools
    "pillow": ("api", 0.82),
    "exiftool": ("api", 0.88),
    "hachoir": ("api", 0.75),
    "insightface": ("api", 0.92),
    "deepface": ("api", 0.88),
    "facenet": ("api", 0.85),
    "opencv_face": ("api", 0.78),
    "google_lens": ("api", 0.80),
    "bing_visual": ("api", 0.80),
    "yandex_images": ("api", 0.76),
    "tineye": ("api", 0.84),
    "tesseract": ("api", 0.86),
    "easyocr": ("api", 0.84),
    "paddleocr": ("api", 0.84),
    "yolo": ("api", 0.82),
    "grounding_dino": ("api", 0.80),
    "clip": ("api", 0.78),
    "image_intelligence_engine": ("api", 0.9),
    "imagehash": ("api", 0.92),
    "opencv": ("api", 0.86),
}

USERNAME_TOOLS = USERNAME_TOOLS  # re-export for tests and callers
IMAGE_TOOLS = frozenset({
    "image_intel", "image_intelligence_engine", "imagehash", "opencv",
    "pillow", "exiftool", "hachoir",
    "insightface", "deepface", "facenet", "opencv_face",
    "google_lens", "bing_visual", "yandex_images", "tineye",
    "tesseract", "easyocr", "paddleocr",
    "yolo", "grounding_dino", "clip",
})
EMAIL_DOMAIN_TOOLS = frozenset({"theharvester", "spiderfoot", "holehe", "recon_ng"})

CROSS_TOOL_BOOSTS: list[tuple[frozenset[str], float, str]] = [
    (frozenset({"sherlock", "maigret"}), 1.18, "username_cross_validation"),
    (frozenset({"sherlock", "maigret", "social_analyzer"}), 1.28, "username_triangulation"),
    (frozenset({"sherlock", "social_analyzer"}), 1.15, "username_cross_validation"),
    (frozenset({"maigret", "social_analyzer"}), 1.15, "username_cross_validation"),
    (frozenset({"theharvester", "spiderfoot"}), 1.22, "email_domain_enrichment"),
    (frozenset({"holehe", "gravatar"}), 1.12, "email_profile_corroboration"),
    (frozenset({"recon_ng", "theharvester"}), 1.15, "domain_enrichment"),
    (frozenset({"recon_ng", "spiderfoot"}), 1.15, "domain_enrichment"),
]

SKIP_PLATFORMS = frozenset({"_scan_summary", "unknown", "samurai_intel"})
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", re.IGNORECASE)

PLATFORM_RELIABILITY: dict[str, float] = {
    # Flat baseline — report depth follows evidence richness, not platform brand.
    "default": 0.85,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_entity_value(entity_type: str, value: str) -> str:
    if entity_type == "email":
        return value.strip().lower()
    if entity_type == "phone":
        return normalize_phone(value)
    if entity_type == "domain":
        return value.strip().lower().split(":")[0]
    if entity_type == "account":
        return normalize_url(value) if (value.startswith("http") or "." in value) else value.strip().lower()
    return value.strip().lower()


def _canonical_value(entity_type: str, value: str, metadata: dict[str, Any] | None = None) -> str:
    meta = metadata or {}
    if entity_type == "account":
        platform = normalize_platform(str(meta.get("platform", "")), meta.get("url"))
        handle = meta.get("username") or meta.get("handle")
        if platform and handle:
            return f"{platform}:{str(handle).lower()}"
        return _normalize_entity_value(entity_type, value)
    return _normalize_entity_value(entity_type, value)


def normalize_url(url: str) -> str:
    raw = url.strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.netloc or parsed.path.split("/")[0]).lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/").lower()
    return f"{host}{path}" if path else host


def normalize_platform(platform: str, url: str | None = None) -> str:
    if url:
        host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            return host
    name = platform.strip().lower()
    name = re.sub(r"^https?://", "", name)
    name = name.split("/")[0]
    if name.startswith("www."):
        name = name[4:]
    return name or "unknown"


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"[^\d+]", "", phone.strip())
    return digits or phone.strip()


def entity_key(entity_type: str, value: str) -> str:
    return f"{entity_type}:{value}"


def _tool_weight(source: str) -> float:
    tier, weight = TOOL_RELIABILITY.get(source, ("heuristic", 0.25))
    return min(TIER_BASE.get(tier, 0.25) * weight, 1.0)


def _is_internal_item(item: dict[str, Any]) -> bool:
    platform = str(item.get("platform", ""))
    return platform.startswith("_") or platform in SKIP_PLATFORMS


def _flat_metadata(item: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for key, value in item.items():
        if key in ("platform", "source_tool", "url"):
            continue
        if value is not None:
            meta[key] = to_json_safe(value)
    return meta


def _make_entity(
    entity_type: str,
    value: str,
    source: str,
    metadata: dict[str, Any] | None = None,
    *,
    raw_payload: dict[str, Any] | None = None,
    raw_source_ref: str | None = None,
) -> Entity:
    if not value:
        raise ValueError("entity value required")
    meta = to_json_safe({**(metadata or {}), "contributing_source": source})
    normalized = _normalize_entity_value(entity_type, value)
    canonical = _canonical_value(entity_type, value, meta)
    tier, tool_conf = TOOL_RELIABILITY.get(source, ("heuristic", 0.25))
    platform = str(meta.get("platform", "")).lower()
    platform_conf = PLATFORM_RELIABILITY.get(platform, PLATFORM_RELIABILITY["default"])
    verified = meta.get("verified") is True or meta.get("registered") is True
    source_confidence = round(min(_tool_weight(source) * (1.1 if verified else 1.0) * platform_conf, 1.0), 4)

    evidence = EvidenceRecord(
        tool=source,
        timestamp=_utc_now(),
        raw_source_ref=raw_source_ref or str(meta.get("url") or value),
        source_confidence=source_confidence,
        raw_payload=raw_payload or {k: v for k, v in meta.items() if k != "source_details"},
    )

    return Entity(
        type=entity_type,
        value=value,
        canonical_value=canonical,
        normalized_value=normalized,
        aliases=[normalized] if normalized != value.lower() else [],
        sources=[source],
        metadata=meta,
        first_seen=_utc_now(),
        last_seen=_utc_now(),
        evidence=[evidence],
    )


def _extract_from_item(
    item: dict[str, Any],
    source_tool: str,
    query: str,
    feature: str,
) -> list[Entity]:
    if _is_internal_item(item):
        return []

    entities: list[Entity] = []
    platform = str(item.get("platform", "unknown"))
    url = item.get("url")
    meta = _flat_metadata(item)
    meta["platform"] = normalize_platform(platform, url)
    if url:
        meta["url"] = url

    # Promote Maigret profile intelligence into entity metadata
    maigret_fields = parse_maigret_payload(meta)
    for key, val in maigret_fields.items():
        if val and not meta.get(key):
            meta[key] = val

    handle = item.get("username") or meta.get("username") or maigret_fields.get("username")
    if handle and is_plausible_handle(str(handle)):
        meta["username"] = str(handle).lower()

    email = item.get("email") or meta.get("email")
    if email and EMAIL_RE.match(str(email).strip()):
        email_val = str(email).strip().lower()
        entities.append(_make_entity("email", email_val, source_tool, {**meta, "email": email_val}))

    phone = item.get("phone") or item.get("phone_hint") or meta.get("phone") or meta.get("phone_hint")
    if phone:
        phone_val = normalize_phone(str(phone))
        if phone_val:
            entities.append(_make_entity("phone", phone_val, source_tool, {**meta, "phone": phone_val}))

    hostname = meta.get("hostname") or meta.get("source_domain")
    if hostname and feature in ("domain_intel", "email_intel"):
        host_val = str(hostname).split(":")[0].strip().lower()
        if host_val and not EMAIL_RE.match(host_val):
            entities.append(_make_entity("domain", host_val, source_tool, {**meta, "hostname": host_val}))

    status = item.get("status") or meta.get("status")
    registered = item.get("registered") is True or status == "registered"
    check_type = item.get("check_type") or meta.get("check_type")

    if check_type == "google_dork" or source_tool == "google_dorking":
        if url:
            doc_val = normalize_url(str(url))
            doc_meta = {
                **meta,
                "verified": False,
                "check_type": "google_dork",
                "corroboration_status": "search_reference",
                "status": status or "search_reference",
                "pivotable": False,
            }
            entities.append(_make_entity("document", doc_val, source_tool, doc_meta))

            if meta.get("image_attributed") or meta.get("serp_hit_type") == "image":
                img_meta = {
                    **meta,
                    "verified": False,
                    "check_type": "google_dork",
                    "username_attributed": True,
                    "discovery_source": "username_search",
                    "intel_engine": "google_dorking",
                    "field": "images",
                }
                entities.append(_make_entity("image", str(url), source_tool, img_meta))

            if meta.get("username_attributed") and feature == "username_search":
                from services.evidence.search_intelligence import classify_search_hit

                hit_kind = str(meta.get("serp_hit_type") or classify_search_hit(
                    str(url), str(meta.get("title") or ""), str(meta.get("snippet") or ""),
                ))
                if hit_kind in ("profile", "repository", "mention", "blog", "forum", "article", "news"):
                    account_meta = {
                        **meta,
                        "verified": False,
                        "check_type": "google_dork",
                        "corroboration_status": "search_reference",
                        "status": status or "search_reference",
                        "username_attributed": True,
                        "discovery_source": "username_search",
                        "search_hit_kind": hit_kind,
                    }
                    entities.append(_make_entity("account", doc_val, source_tool, account_meta))

        if meta.get("username_attributed"):
            email_val = meta.get("email")
            if email_val and EMAIL_RE.match(str(email_val).strip()):
                email_meta = {
                    **meta,
                    "verified": False,
                    "check_type": "google_dork",
                    "username_attributed": True,
                    "discovery_source": "username_search",
                    "pivotable": True,
                    "status": status or "username_attributed",
                }
                entities.append(_make_entity("email", str(email_val).strip().lower(), source_tool, email_meta))

            phone_val = meta.get("phone_hint") or meta.get("phone")
            if phone_val:
                phone_meta = {
                    **meta,
                    "verified": False,
                    "check_type": "google_dork",
                    "username_attributed": True,
                    "discovery_source": "username_search",
                    "pivotable": True,
                    "status": status or "username_attributed",
                }
                entities.append(_make_entity("phone", normalize_phone(str(phone_val)), source_tool, phone_meta))

        return entities

    if url:
        norm = normalize_url(str(url))
        if norm:
            account_meta = {
                **meta,
                "verified": item.get("verified"),
                "check_type": item.get("check_type"),
                "status": status,
                "registered": registered,
            }
            entities.append(_make_entity("account", norm, source_tool, account_meta))
    elif registered and platform not in SKIP_PLATFORMS:
        identity = str(item.get("email") or meta.get("phone") or query).lower().strip()
        handle = str(item.get("username") or meta.get("username") or "").lower().strip()
        if handle:
            account_val = f"{normalize_platform(platform)}:{handle}"
        elif meta.get("phone") or feature == "infra_intel":
            phone_val = normalize_phone(str(meta.get("phone") or query))
            account_val = f"{normalize_platform(platform)}:{phone_val}"
        else:
            account_val = f"{normalize_platform(platform)}:{identity}"
        entities.append(
            _make_entity(
                "account",
                account_val,
                source_tool,
                {
                    **meta,
                    "registered": True,
                    "status": status or "registered",
                    "verified": item.get("verified") is not False,
                    "phone_linked": bool(meta.get("phone") or feature == "infra_intel"),
                },
            )
        )
    elif feature == "username_search" and platform not in SKIP_PLATFORMS:
        if item.get("check_type") != "dataset_lookup":
            candidate = f"{normalize_platform(platform)}:{query.lower()}"
            entities.append(_make_entity("account", candidate, source_tool, meta))

    if source_tool in IMAGE_TOOLS:
        if platform in ("metadata_extraction", "exiftool_metadata", "hachoir_metadata"):
            file_val = str(meta.get("file") or query)
            entities.append(_make_entity("image", file_val, source_tool, meta))
        elif platform in ("google_reverse_image", "bing_visual_search", "yandex_images", "tineye") or meta.get("intel_group") == "reverse_image_search":
            img_val = str(meta.get("page_url") or url or meta.get("match_url") or meta.get("source") or query)
            if img_val:
                entities.append(_make_entity("image", img_val, source_tool, meta))
            for profile in meta.get("profile_urls") or meta.get("linked_profiles") or []:
                if isinstance(profile, str) and profile.startswith("http"):
                    entities.append(_make_entity("account", profile, source_tool, {**meta, "url": profile, "reverse_image_match": True}))
        elif platform in ("face_detection", "opencv_face_detection", "deepface_analysis"):
            file_val = str(meta.get("file") or url or query)
            if file_val:
                entities.append(_make_entity("image", file_val, source_tool, meta))
        elif platform == "ocr_text" and meta.get("text"):
            entities.append(_make_entity("document", str(meta["text"])[:500], source_tool, meta))
        elif meta.get("status") not in ("placeholder", "unavailable") and meta.get("status") != "integration_ready":
            img_val = str(meta.get("source") or url or meta.get("file") or query)
            if img_val:
                entities.append(_make_entity("image", img_val, source_tool, meta))
        elif url or meta.get("file"):
            img_val = str(meta.get("file") or url or query)
            if img_val:
                entities.append(_make_entity("image", img_val, source_tool, meta))

    if feature == "infra_intel" and meta.get("ip"):
        entities.append(_make_entity("domain", str(meta["ip"]), source_tool, meta))

    return entities


def _extract_from_confirmed_finding(finding: dict[str, Any]) -> list[Entity]:
    entities: list[Entity] = []
    source = finding.get("source_tool", "unknown")
    ftype = finding.get("type", "")
    platform = finding.get("platform", "")

    if ftype == "account_registration" and platform:
        val = f"{normalize_platform(platform)}:{finding.get('email', '').lower()}"
        meta = {k: v for k, v in finding.items() if k not in ("type", "platform", "source_tool")}
        meta["verified"] = True
        meta["status"] = "registered"
        url = finding.get("url") or finding.get("profile_url")
        if url:
            meta["url"] = url
            meta["profile_url"] = url
        entities.append(_make_entity("account", val, source, meta))

    if finding.get("email"):
        email = str(finding["email"]).lower()
        entities.append(_make_entity("email", email, source, finding))

    if ftype == "linked_account" and platform:
        username = finding.get("username")
        url = finding.get("url") or finding.get("profile_url")
        if not url and username:
            from services.email_profile_resolver import build_profile_url

            url = build_profile_url(platform, str(username))
        val = f"{normalize_platform(platform)}:{str(username or '').lower()}".rstrip(":")
        meta = {k: v for k, v in finding.items() if k not in ("type", "platform")}
        if url:
            meta["url"] = url
            meta["profile_url"] = url
        entities.append(_make_entity("account", val, source, meta))

    return entities


def _extract_from_public_profile(profile: dict[str, Any]) -> list[Entity]:
    entities: list[Entity] = []
    source = profile.get("source", "gravatar")
    display = profile.get("display_name")
    avatar = profile.get("avatar_url")

    if display or avatar:
        val = profile.get("profile_url") or avatar or display or "gravatar_profile"
        entities.append(
            _make_entity(
                "account",
                normalize_url(val) if val.startswith("http") else str(val).lower(),
                source,
                profile,
            )
        )

    for acct in profile.get("accounts") or []:
        domain = acct.get("domain")
        username = acct.get("username") or acct.get("display")
        if domain:
            from services.email_profile_resolver import build_profile_url

            profile_url = acct.get("profile_url") or acct.get("url") or build_profile_url(str(domain), str(username) if username else None)
            val = f"{normalize_platform(domain)}:{str(username or '').lower()}".rstrip(":")
            entities.append(
                _make_entity(
                    "account",
                    val,
                    source,
                    {
                        **acct,
                        "verified": acct.get("verified"),
                        "profile_url": profile_url or profile.get("profile_url"),
                        "url": profile_url,
                        "linked_from_gravatar": True,
                    },
                )
            )
    return entities


def _merge_metadata(existing: dict[str, Any], incoming: dict[str, Any], source: str) -> dict[str, Any]:
    merged = to_json_safe(dict(existing))
    incoming = to_json_safe(dict(incoming))
    source_details = dict(merged.get("source_details") or {})
    source_details[source] = {k: v for k, v in incoming.items() if k != "source_details"}
    merged["source_details"] = source_details

    for key, value in incoming.items():
        if key == "source_details":
            continue
        if key not in merged or is_empty_value(merged.get(key)):
            merged[key] = value
        elif key == "check_type":
            priority = {"live_scan": 3, "google_dork_profile": 2, "username_probe": 1, "dataset_lookup": 0}
            if priority.get(str(value), 0) > priority.get(str(merged.get(key)), 0):
                merged[key] = value
        elif key == "status" and value in {"maigret_claimed", "registered"}:
            merged[key] = value
        elif key == "verified" and value is True:
            merged[key] = True
        elif key == "registered" and value is True:
            merged[key] = True
    return merged


def deduplicate_entities(entities: list[Entity]) -> list[Entity]:
    buckets: dict[str, Entity] = {}

    for entity in entities:
        key = entity_key(entity.type, entity.canonical_value or entity.normalized_value or entity.value)
        if key not in buckets:
            buckets[key] = entity.model_copy(deep=True)
            continue

        existing = buckets[key]
        for src in entity.sources:
            if src not in existing.sources:
                existing.sources.append(src)
        existing.sources.sort()
        existing.metadata = _merge_metadata(existing.metadata, entity.metadata, entity.sources[0])
        existing.last_seen = _utc_now()

        for alias in [entity.value, entity.normalized_value, entity.canonical_value, *entity.aliases]:
            if alias and alias not in existing.aliases and alias != existing.canonical_value:
                existing.aliases.append(alias)

        seen_tools = {e.tool for e in existing.evidence}
        for record in entity.evidence:
            if record.tool not in seen_tools:
                existing.evidence.append(record)
                seen_tools.add(record.tool)

    return list(buckets.values())


def is_confirmed_account(entity: Entity, *, seed_email: str | None = None) -> bool:
    """Confirm real accounts via live URL proof and/or multi-tool agreement."""
    if entity.type != "account":
        return False
    return account_confirmed(entity.metadata or {}, set(entity.sources), seed_email=seed_email)


def apply_account_corroboration(entities: list[Entity], *, seed_query: str = "") -> list[Entity]:
    """Demote username-probe hits until corroborated by another username tool."""
    from services.correlation.handle_quality import is_correlatable_handle, normalize_profile_handle

    out: list[Entity] = []
    for entity in entities:
        if entity.type != "account":
            out.append(entity)
            continue

        meta = dict(entity.metadata or {})
        url = str(meta.get("url") or meta.get("profile_url") or "")
        if not url and entity.value.startswith("http"):
            url = entity.value
        platform = str(meta.get("platform") or "")
        handle = ""
        if seed_query:
            handle = normalize_profile_handle(url or entity.value, platform, meta)
            if handle:
                meta["username"] = handle
                meta["handle"] = handle

        entity_for_confirm = entity.model_copy(update={"metadata": meta})
        sources = set(entity.sources)
        confirmed = is_confirmed_account(entity_for_confirm)
        if (
            meta.get("check_type") == "username_probe"
            and len(sources & USERNAME_TOOLS) < 2
            and meta.get("status") != "login_walled"
            and meta.get("live_verify_reason") != "login_wall"
            and meta.get("live_profile_verified") is not True
        ):
            confirmed = False
        if confirmed and seed_query and "@" not in seed_query.strip() and handle:
            if not is_correlatable_handle(handle, seed_query, url or None):
                confirmed = False
        if confirmed and meta.get("content_seed_verified") is False:
            confirmed = False

        meta["verified"] = confirmed
        if confirmed:
            meta["corroboration_status"] = "confirmed"
        elif meta.get("check_type") == "username_probe" or sources == {"sherlock"}:
            meta["corroboration_status"] = "probe"
            meta.setdefault("status", "unconfirmed")
        else:
            meta["corroboration_status"] = "unconfirmed"
            meta.setdefault("status", "unconfirmed")

        out.append(entity.model_copy(update={"metadata": meta}))
    return out


def _collect_signals(entity: Entity) -> list[str]:
    signals: list[str] = []
    meta = entity.metadata
    sources = set(entity.sources)

    if meta.get("verified") is True or meta.get("registered") is True:
        signals.append("live_verification")
    if meta.get("corroboration_status") == "confirmed":
        signals.append("confirmed_account")
    if meta.get("check_type") == "live_scan":
        signals.append("live_scan")
    if meta.get("check_type") == "username_probe":
        signals.append("username_probe")
    if meta.get("check_type") == "dataset_lookup":
        signals.append("dataset_candidate")
    if meta.get("status") == "rate_limited":
        signals.append("inconclusive_rate_limit")
    if meta.get("confidence") == "public":
        signals.append("public_source")
    if len(sources) > 1:
        signals.append("multi_source_corroboration")

    if sources & USERNAME_TOOLS and len(sources & USERNAME_TOOLS) >= 2:
        signals.append("username_tool_agreement")
    if sources & EMAIL_DOMAIN_TOOLS and len(sources & EMAIL_DOMAIN_TOOLS) >= 2:
        signals.append("email_domain_enrichment")

    for tool_set, _, label in CROSS_TOOL_BOOSTS:
        if tool_set.issubset(sources):
            signals.append(label)

    return sorted(set(signals))


def _score_entity(entity: Entity) -> tuple[float, float]:
    if not entity.sources:
        return 0.0, 0.0

    meta = entity.metadata
    sources = frozenset(entity.sources)
    platform = str(meta.get("platform", "")).lower()
    platform_rel = PLATFORM_RELIABILITY.get(platform, PLATFORM_RELIABILITY["default"])

    tool_scores = [_tool_weight(s) for s in entity.sources]
    evidence_scores = [e.source_confidence for e in entity.evidence if e.source_confidence > 0]
    base = max(tool_scores + evidence_scores or [0.0])

    if meta.get("verified") is True or meta.get("registered") is True or meta.get("corroboration_status") == "confirmed":
        base = min(base * 1.25, 1.0)
    elif meta.get("corroboration_status") == "probe":
        base = min(base * 0.45, 0.35)
    if meta.get("check_type") == "live_scan":
        base = min(base * 1.1, 1.0)
    if meta.get("check_type") == "dataset_lookup":
        base *= 0.35
    if meta.get("status") == "rate_limited":
        base *= 0.12
    if meta.get("status") == "placeholder":
        base *= 0.05

    base = min(base * platform_rel, 1.0)

    boost = 1.0
    for tool_set, multiplier, _ in CROSS_TOOL_BOOSTS:
        if tool_set.issubset(sources):
            boost = max(boost, multiplier)

    corroboration = len(entity.sources) + len(entity.evidence)
    if corroboration >= 2:
        boost *= 1.0 + min(0.10 * (corroboration - 1), 0.40)

    reliability = round(min(base, 1.0), 4)
    fusion = round(min(reliability * boost, 1.0), 4)
    return reliability, fusion


def _apply_scores(entities: list[Entity]) -> list[Entity]:
    scored: list[Entity] = []
    for entity in entities:
        reliability, fusion = _score_entity(entity)
        entity.reliability_score = reliability
        entity.fusion_score = fusion
        scored.append(entity)
    scored.sort(key=lambda e: (-e.fusion_score, -len(e.sources), e.type, e.value))
    return scored


def _build_evidence_map(entities: list[Entity]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for entity in entities:
        key = entity_key(entity.type, entity.value)
        evidence[key] = {
            "entity_id": entity.entity_id,
            "type": entity.type,
            "value": entity.value,
            "canonical_value": entity.canonical_value,
            "aliases": entity.aliases,
            "normalized_value": entity.normalized_value,
            "first_seen": entity.first_seen,
            "last_seen": entity.last_seen,
            "sources": entity.sources,
            "reliability_score": entity.reliability_score,
            "fusion_score": entity.fusion_score,
            "evidence_provenance": [e.model_dump() for e in entity.evidence],
            "signals": _collect_signals(entity),
            "metadata_summary": {
                k: entity.metadata[k]
                for k in (
                    "platform",
                    "url",
                    "verified",
                    "registered",
                    "status",
                    "check_type",
                    "email",
                    "hostname",
                )
                if k in entity.metadata
            },
        }
    return evidence


def _global_fusion_score(entities: list[Entity]) -> float:
    if not entities:
        return 0.0
    weighted = [e.fusion_score for e in entities if e.fusion_score > 0]
    if not weighted:
        return 0.0
    top = sorted(weighted, reverse=True)[:10]
    if not top:
        return 0.0
    return round(sum(top) / len(top), 4)


class DataFusionEngine:
    """Merge orchestrator tool outputs into unified intelligence."""

    def fuse(
        self,
        tool_results: list[ToolResult],
        feature: str,
        query: str,
        *,
        confirmed_findings: list[dict[str, Any]] | None = None,
        public_profile_data: list[dict[str, Any]] | None = None,
        investigation_leads: list[dict[str, Any]] | None = None,
    ) -> FusionOutput:
        raw_entities: list[Entity] = []

        for result in tool_results:
            if not result.success:
                continue
            for item in result.data:
                raw_entities.extend(_extract_from_item(item, result.tool, query, feature))

        for finding in confirmed_findings or []:
            raw_entities.extend(_extract_from_confirmed_finding(finding))

        for profile in public_profile_data or []:
            raw_entities.extend(_extract_from_public_profile(profile))

        for lead in investigation_leads or []:
            platform = lead.get("platform")
            if not platform:
                continue
            val = f"{normalize_platform(platform)}:{str(lead.get('email') or query).lower()}"
            raw_entities.append(
                _make_entity(
                    "account",
                    val,
                    lead.get("source_tool", "unknown"),
                    {
                        **lead,
                        "status": "rate_limited",
                        "verified": False,
                        "investigation_lead": True,
                        "confidence": "inconclusive",
                    },
                )
            )

        deduped = deduplicate_entities(raw_entities)
        seed_q = query.strip() if feature.startswith("username") and "@" not in query.strip() else ""
        corroborated = apply_account_corroboration(deduped, seed_query=seed_q)
        scored = _apply_scores(corroborated)
        evidence_map = _build_evidence_map(scored)
        global_score = _global_fusion_score(scored)
        raw_index = {
            entity_key(e.type, e.canonical_value or e.value): [ev.tool for ev in e.evidence]
            for e in scored
        }

        return FusionOutput(
            entities=raw_entities,
            deduplicated_entities=scored,
            fusion_score=global_score,
            evidence_map=evidence_map,
            raw_evidence_index=raw_index,
        )

    def rescore_entities(self, entities: list[Entity]) -> list[Entity]:
        return _apply_scores(entities)

    def build_evidence_map(self, entities: list[Entity]) -> dict[str, Any]:
        return _build_evidence_map(entities)

    def compute_global_fusion_score(self, entities: list[Entity]) -> float:
        return _global_fusion_score(entities)


fusion_engine = DataFusionEngine()
