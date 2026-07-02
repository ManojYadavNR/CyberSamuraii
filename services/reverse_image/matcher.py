"""Classify reverse image match types using hashes and metadata."""

from __future__ import annotations

from schemas.reverse_image import MatchType


def classify_match_type(
    *,
    url_a: str,
    url_b: str,
    hash_similarity: float = 0.0,
    face_similarity: float = 0.0,
    mirrored_similarity: float = 0.0,
    title: str = "",
    snippet: str = "",
    platform: str = "",
) -> MatchType:
    if face_similarity >= 0.75:
        return "profile_photo"
    if url_a and url_b and url_a.rstrip("/") == url_b.rstrip("/"):
        return "identical"
    if hash_similarity >= 0.98:
        return "identical"
    if mirrored_similarity >= 0.9:
        return "mirrored"
    if hash_similarity >= 0.92:
        return "cropped"
    if hash_similarity >= 0.85:
        return "edited"
    if hash_similarity >= 0.75:
        return "resized"
    low = f"{title} {snippet} {platform}".lower()
    if any(k in low for k in ("screenshot", "screen capture", "screengrab")):
        return "screenshot"
    if any(k in low for k in ("avatar", "profile photo", "profile picture", "headshot", "portrait")):
        return "profile_photo"
    if platform and hash_similarity >= 0.65:
        return "cross_platform_reuse"
    return "similar"
