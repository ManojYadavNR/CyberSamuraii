"""Parallel execution groups and concurrency limits."""

from __future__ import annotations

import os

IMAGE_TOOL_GROUPS: dict[str, list[str]] = {
    "face_analysis": ["insightface", "deepface", "facenet", "opencv_face"],
    "reverse_image_search": ["google_lens", "bing_visual", "yandex_images", "tineye"],
    "ocr": ["tesseract", "easyocr", "paddleocr"],
    "object_detection": ["yolo", "grounding_dino", "clip"],
    "metadata": ["exiftool", "pillow", "hachoir"],
}

# Heavy CPU/GPU ML tools — run one at a time (shared model executor).
ML_IMAGE_TOOLS: frozenset[str] = frozenset({
    "insightface", "deepface", "facenet", "opencv_face",
    "yolo", "grounding_dino", "clip",
    "tesseract", "easyocr", "paddleocr",
})

# Keep legacy image_intel adapter; parallel modules run alongside it.
IMAGE_PARALLEL_TOOLS: list[str] = [
    "image_intel",
    *[tool for group in IMAGE_TOOL_GROUPS.values() for tool in group],
]


def max_image_tool_concurrency() -> int:
    """Legacy single semaphore — prefer IO/ML split below."""
    return max(1, int(os.getenv("IMAGE_TOOL_CONCURRENCY", "4")))


def max_io_tool_concurrency() -> int:
    """Light / network tools (reverse search, metadata) in parallel."""
    return max(1, int(os.getenv("IMAGE_IO_CONCURRENCY", "6")))


def max_ml_tool_concurrency() -> int:
    """Heavy ML models — keep at 1 to avoid RAM spikes and import races."""
    return max(1, int(os.getenv("IMAGE_ML_CONCURRENCY", "1")))


def is_ml_image_tool(tool: str) -> bool:
    return tool in ML_IMAGE_TOOLS


# Fast path — multiple techniques without the heaviest models (deepface/paddle/dino).
IMAGE_FAST_TOOLS: list[str] = [
    "image_intel",
    "pillow",
    "exiftool",
    "hachoir",
    "opencv_face",
    "insightface",
    "facenet",
    "tesseract",
    "easyocr",
    "yolo",
    "clip",
    "google_lens",
    "bing_visual",
    "yandex_images",
    "tineye",
]

# Fast reverse sources — prefer DDGS/API over headless browser uploads.
IMAGE_FAST_REVERSE_SOURCES: list[str] = [
    "public_search",
    "google_lens_ddgs",
    "bing_visual_ddgs",
    "yandex_images",
    "tineye",
    "saucenao",
    "investigation_hashes",
    "face_kb",
]

IMAGE_HOP_TOOLS: list[str] = ["pillow", "exiftool", "opencv_face", "insightface", "tesseract"]
IMAGE_HOP_REVERSE_SOURCES: list[str] = [
    "public_search",
    "google_lens_ddgs",
    "face_kb",
    "investigation_hashes",
]

# Parallel expansion — multiple leads investigated concurrently.
EXPANSION_CONCURRENCY: int = max(1, int(os.getenv("EXPANSION_CONCURRENCY", "8")))

# Per-feature caps within a single expansion batch (platform-grouped parallelism).
FEATURE_EXPANSION_LIMITS: dict[str, int] = {
    "domain_intel": max(2, int(os.getenv("DOMAIN_EXPANSION_PARALLEL", "4"))),
    "username_search": max(2, int(os.getenv("USERNAME_EXPANSION_PARALLEL", "3"))),
    "image_intel": 1,
    "email_intel": 2,
    "infra_intel": 2,
}

# Concurrent tool runners per feature (domain/username hops search platforms in parallel).
FEATURE_TOOL_CONCURRENCY: dict[str, int] = {
    "domain_intel": max(2, int(os.getenv("DOMAIN_TOOL_CONCURRENCY", "8"))),
    "username_search": max(2, int(os.getenv("USERNAME_TOOL_CONCURRENCY", "10"))),
    "email_intel": max(2, int(os.getenv("EMAIL_TOOL_CONCURRENCY", "10"))),
    "infra_intel": max(2, int(os.getenv("INFRA_TOOL_CONCURRENCY", "4"))),
    # IO tools parallel; ML tools are further limited by IMAGE_ML_CONCURRENCY.
    "image_intel": max(2, int(os.getenv("IMAGE_TOOL_CONCURRENCY", "6"))),
}

# Fast domain tools for discovery hops — registry-driven.
def hop_username_tools() -> list[str]:
    from services.osint_registry.router import tools_for_feature
    return tools_for_feature("username_search", hop=True)


def hop_domain_tools() -> list[str]:
    from services.osint_registry.router import tools_for_feature
    return tools_for_feature("domain_intel", hop=True)


HOP_USERNAME_TOOLS: list[str] = hop_username_tools()
HOP_DOMAIN_TOOLS: list[str] = hop_domain_tools()
BROWSER_REVERSE_SOURCES: frozenset[str] = frozenset({"google_lens", "bing_upload", "yandex_upload"})
SKIP_BROWSER_MIN_MATCHES: int = max(0, int(os.getenv("REVERSE_SKIP_BROWSER_MIN_MATCHES", "1")))

# Hard wall clocks (seconds) — per-tool budget once running; batch cap scales with queue depth.
INVESTIGATION_WALL_SECONDS: float = float(os.getenv("INVESTIGATION_WALL_SECONDS", "120"))
USERNAME_WALL_SEC: float = float(os.getenv("USERNAME_WALL_SEC", "90"))
EMAIL_WALL_SEC: float = float(os.getenv("EMAIL_WALL_SEC", "90"))
MAX_USERNAME_BATCH_SEC: float = float(os.getenv("MAX_USERNAME_BATCH_SEC", "540"))
DUAL_MAX_USERNAME_BATCH_SEC: float = float(os.getenv("DUAL_MAX_USERNAME_BATCH_SEC", "300"))
MAX_EMAIL_BATCH_SEC: float = float(os.getenv("MAX_EMAIL_BATCH_SEC", "480"))
DUAL_MAX_EMAIL_BATCH_SEC: float = float(os.getenv("DUAL_MAX_EMAIL_BATCH_SEC", "240"))
FAST_USERNAME_WALL_SEC: float = float(os.getenv("FAST_USERNAME_WALL_SEC", "90"))
FAST_EMAIL_WALL_SEC: float = float(os.getenv("FAST_EMAIL_WALL_SEC", "60"))
DOMAIN_WALL_SEC: float = float(os.getenv("DOMAIN_WALL_SEC", "120"))
INFRA_WALL_SEC: float = float(os.getenv("INFRA_WALL_SEC", "300"))
PHONE_WALL_SEC: float = float(os.getenv("PHONE_WALL_SEC", "120"))
PHONE_SOCIAL_INTEL_WALL_SEC: float = float(os.getenv("PHONE_SOCIAL_INTEL_WALL_SEC", "120"))
PHONEINFOGA_WALL_SEC: float = float(os.getenv("PHONEINFOGA_WALL_SEC", "120"))
IMAGE_WALL_SECONDS: float = float(os.getenv("IMAGE_WALL_SECONDS", "90"))
IMAGE_STAGE_WALL_SECONDS: float = float(os.getenv("IMAGE_STAGE_WALL_SECONDS", "240"))
IMAGE_ML_TOOL_WALL_SEC: float = float(os.getenv("IMAGE_ML_TOOL_WALL_SEC", "90"))
IMAGE_IO_TOOL_WALL_SEC: float = float(os.getenv("IMAGE_IO_TOOL_WALL_SEC", "40"))
DISCOVERY_WALL_SECONDS: float = float(os.getenv("DISCOVERY_WALL_SECONDS", "170"))
HOP_IMAGE_WALL_SECONDS: float = float(os.getenv("HOP_IMAGE_WALL_SECONDS", "25"))


def feature_wall_seconds(feature: str) -> float:
    """Per-tool run budget (starts when the tool leaves the queue)."""
    mapping = {
        "username_search": USERNAME_WALL_SEC,
        "email_intel": EMAIL_WALL_SEC,
        "domain_intel": DOMAIN_WALL_SEC,
        "infra_intel": INFRA_WALL_SEC,
        "image_intel": IMAGE_WALL_SECONDS,
    }
    return mapping.get(feature, INVESTIGATION_WALL_SECONDS)


def effective_wall_seconds(feature: str) -> float:
    """Lower per-tool budgets in username+email dual mode."""
    try:
        from services.resource_guard import (
            DUAL_EMAIL_WALL_SEC,
            DUAL_USERNAME_WALL_SEC,
            get_investigation_mode,
            is_dual_identity_scan,
            is_full_scan_mode,
        )

        if get_investigation_mode() == "samurai":
            if feature == "username_search":
                # Hard cap so Samurai never blocks the investigation past ~1.5 min.
                return float(os.getenv("SAMURAI_WALL_SEC", "120"))
        if get_investigation_mode() == "fast":
            if feature == "username_search":
                return FAST_USERNAME_WALL_SEC
            if feature == "email_intel":
                return FAST_EMAIL_WALL_SEC
        if is_dual_identity_scan() and not is_full_scan_mode():
            if feature == "username_search":
                return DUAL_USERNAME_WALL_SEC
            if feature == "email_intel":
                return DUAL_EMAIL_WALL_SEC
    except ImportError:
        pass
    return feature_wall_seconds(feature)


def batch_wall_seconds(feature: str, tool_count: int, concurrency: int) -> float:
    """Total batch cap — long enough for queued tools to each get a run slot."""
    per_tool = effective_wall_seconds(feature)
    limit = max(1, concurrency)
    slots = max(1, (max(1, tool_count) + limit - 1) // limit)
    raw = per_tool * slots
    try:
        from services.resource_guard import is_dual_identity_scan, is_full_scan_mode
        dual = is_dual_identity_scan() and not is_full_scan_mode()
    except ImportError:
        dual = False
    if feature == "username_search":
        cap = DUAL_MAX_USERNAME_BATCH_SEC if dual else MAX_USERNAME_BATCH_SEC
        return min(raw, cap)
    if feature == "email_intel":
        cap = DUAL_MAX_EMAIL_BATCH_SEC if dual else MAX_EMAIL_BATCH_SEC
        # Email tools run in parallel waves — never starve queued tools.
        return min(max(raw, per_tool + 45.0), cap)
    if feature == "image_intel":
        # ML tools serialize; allow enough slots without hanging the investigation.
        return min(max(raw, per_tool * 2), IMAGE_STAGE_WALL_SECONDS)
    return min(raw, INVESTIGATION_WALL_SECONDS)

# Full deep scan — use only when Deep mode enabled in UI.
IMAGE_FULL_TOOLS: list[str] = IMAGE_PARALLEL_TOOLS


def image_tools_for_profile(profile: str) -> list[str]:
    if profile == "deep":
        return IMAGE_FULL_TOOLS
    if profile == "hop":
        return IMAGE_HOP_TOOLS
    return IMAGE_FAST_TOOLS


def reverse_sources_for_profile(profile: str) -> list[str] | None:
    if profile == "deep":
        return None
    if profile == "hop":
        return IMAGE_HOP_REVERSE_SOURCES
    return IMAGE_FAST_REVERSE_SOURCES


def image_tools_for_hop() -> list[str]:
    return IMAGE_HOP_TOOLS


def feature_tool_concurrency(feature: str) -> int | None:
    """Max parallel adapters for a feature hop (domain/username/email)."""
    return FEATURE_TOOL_CONCURRENCY.get(feature)


