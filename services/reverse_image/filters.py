"""Quality filters for reverse image matches — reject generic SERP noise."""

from __future__ import annotations

import asyncio
import io
import re
from urllib.parse import urlparse

import httpx

from services.google_dorking.filters import handle_from_profile_url
from services.image_intelligence.path_utils import is_local_path, is_public_url
from services.reverse_image.extractors import extract_profile_urls

JUNK_DOMAINS: frozenset[str] = frozenset({
    "bing.com", "google.com", "duckduckgo.com", "yandex.com", "startpage.com",
    "gravatar.com", "pfpmaker.com", "pixabay.com", "freepik.com", "pngtree.com",
    "pngall.com", "vecteezy.com", "flaticon.com", "unsplash.com", "postimages.org",
    "imgur.com", "imageprompt.org", "crowdgen.com", "community.make.com",
    "learn.microsoft.com", "stablediffusionweb.com", "imgcdn.stablediffusionweb.com",
    "comicvine.gamespot.com", "zillow.com", "zillowstatic.com", "thispersondoesnotexist.com",
    "generated.photos", "randomuser.me", "uifaces.co",
})

JUNK_PATH_SEGMENTS: frozenset[str] = frozenset({
    "search", "hashtag", "explore", "docs", "topics", "trending", "organizations",
    "features", "en", "i", "p", "watch", "shorts",
})

JUNK_HOST_FRAGMENTS: tuple[str, ...] = (
    "/tutorials/",
    "/visualsearch",
    "/images/?",
    "/images/details/{",
    "/free-icons/",
    "/free-png/",
    "/free-vector/",
    "/free-photos-vectors/",
    "/images/search/",
    "yandex.com/images/search",
    "yandex.ru/images/search",
    "/blog/all-about",
    "sandbox:/mnt/data",
    "stablediffusion",
    "/profileimage.jpeg",
)

GENERIC_TITLE_WORDS: frozenset[str] = frozenset({
    "profile", "avatar", "visual search", "bing images", "search images",
    "your free avatar", "free download", "transparent images", "profile picture",
    "try visual search", "microsoft bing", "link in bio", "gravatar create",
    "professional man", "id photo", "stable diffusion", "real estate agent",
})

MIN_HASH_SIMILARITY = 0.82
MIN_HASH_PERSON = 0.86
MIN_HASH_BROWSER_SIMILAR = 0.48
MIN_FACE_SIMILARITY = 0.52
MIN_CONFIDENCE = 0.60
MIN_CONFIDENCE_PERSON = 0.62


def is_junk_url(url: str) -> bool:
    if not url or is_local_path(url) or not is_public_url(url):
        return True
    low = url.lower()
    if any(frag in low for frag in JUNK_HOST_FRAGMENTS):
        return True
    host = urlparse(url).netloc.lower().replace("www.", "")
    if host in JUNK_DOMAINS:
        return True
    if host.endswith(".bing.com") or host.endswith(".google.com"):
        return True
    return False


def is_real_profile_url(url: str) -> bool:
    """Profile page by URL structure — no hardcoded platform list."""
    if is_junk_url(url):
        return False
    parsed = urlparse(url if "://" in url else f"https://{url}")
    path = parsed.path.strip("/")
    if not path:
        return False
    handle = handle_from_profile_url(url)
    if handle and len(handle) >= 2 and handle.lower() not in JUNK_PATH_SEGMENTS:
        return True
    first = path.split("/")[0].split("?")[0].lower()
    return len(first) >= 2 and first not in JUNK_PATH_SEGMENTS


def is_generic_title(title: str) -> bool:
    low = title.strip().lower()
    if not low or len(low) < 4:
        return True
    return any(g in low for g in GENERIC_TITLE_WORDS)


def confidence_from_hash(hash_similarity: float) -> float:
    if hash_similarity >= 0.95:
        return round(min(0.98, 0.88 + (hash_similarity - 0.95) * 2.0), 4)
    if hash_similarity >= MIN_HASH_SIMILARITY:
        return round(0.55 + (hash_similarity - MIN_HASH_SIMILARITY) * 1.5, 4)
    return 0.0


async def _download_image(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.content:
                return resp.content
    except Exception:
        return None
    return None


def _hash_similarity(seed_path: str, candidate_bytes: bytes) -> float:
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return 0.0
    try:
        seed = Image.open(seed_path)
        cand = Image.open(io.BytesIO(candidate_bytes))
        scores = []
        for fn in (imagehash.average_hash, imagehash.phash, imagehash.dhash):
            dist = fn(seed) - fn(cand)
            scores.append(max(0.0, 1.0 - dist / 64.0))
        return max(scores) if scores else 0.0
    except Exception:
        return 0.0


def _face_similarity(seed_path: str, candidate_bytes: bytes) -> float:
    try:
        from services.correlation.image_similarity import _face_embedding_similarity
    except ImportError:
        return 0.0
    try:
        with open(seed_path, "rb") as f:
            seed_bytes = f.read()
        score, _ = _face_embedding_similarity(seed_bytes, candidate_bytes)
        return float(score)
    except Exception:
        return 0.0


async def verify_match_hash(seed_path: str, match_url: str) -> float:
    if not is_public_url(match_url):
        return 0.0
    data = await _download_image(match_url)
    if not data:
        return 0.0
    return _hash_similarity(seed_path, data)


async def verify_match_face(seed_path: str, match_url: str) -> float:
    if not is_public_url(match_url):
        return 0.0
    data = await _download_image(match_url)
    if not data:
        return 0.0
    return _face_similarity(seed_path, data)


async def verify_and_filter_matches(
    seed_path: str,
    matches: list,
    *,
    face_count: int = 0,
    image_category: str = "",
    face_crop_path: str | None = None,
) -> list:
    """Keep only public, visually verified matches — never local paths."""
    from schemas.reverse_image import ReverseImageMatch

    is_person = face_count > 0 and image_category not in ("logo", "company logo", "product packaging")
    min_hash = MIN_HASH_PERSON if is_person else MIN_HASH_SIMILARITY
    min_conf = MIN_CONFIDENCE_PERSON if is_person else MIN_CONFIDENCE
    compare_path = face_crop_path if face_crop_path and not is_local_path(face_crop_path) else seed_path
    verified: list[ReverseImageMatch] = []

    async def _check(match: ReverseImageMatch) -> ReverseImageMatch | None:
        if is_local_path(match.match_url) or not is_public_url(match.match_url):
            return None
        if match.page_url and (is_local_path(match.page_url) or not is_public_url(match.page_url)):
            match = match.model_copy(update={"page_url": match.match_url})

        if is_junk_url(match.match_url):
            return None
        if match.page_url and is_junk_url(match.page_url):
            return None

        image_url = match.match_url
        if not image_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
            if match.page_url and str(match.page_url).lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
                image_url = str(match.page_url)
            else:
                return None

        hash_sim = float(match.provenance.get("hash_similarity") or 0.0)
        if hash_sim < min_hash:
            hash_sim = await verify_match_hash(compare_path, image_url)

        face_sim = 0.0
        if is_person:
            face_sim = await verify_match_face(compare_path, image_url)

        real_profiles = [u for u in extract_profile_urls(match.page_url or match.match_url, match.title or "", match.snippet or "") if is_real_profile_url(u)]
        match = match.model_copy(update={"profile_urls": real_profiles})

        preset_conf: float | None = None
        if is_person:
            if real_profiles and face_sim >= MIN_FACE_SIMILARITY:
                pass
            elif real_profiles and match.source in ("google_lens", "bing_upload", "yandex_upload"):
                pass
            elif match.provenance.get("browser_reverse") and hash_sim >= MIN_HASH_BROWSER_SIMILAR:
                preset_conf = round(min(0.68, 0.45 + hash_sim * 0.3), 4)
                if face_sim >= MIN_FACE_SIMILARITY:
                    preset_conf = round(min(0.95, preset_conf * 0.5 + face_sim * 0.5), 4)
            elif hash_sim >= 0.92 and face_sim >= 0.40:
                pass
            else:
                return None
        elif hash_sim < min_hash:
            return None

        if (
            is_generic_title(match.title or "")
            and not real_profiles
            and not match.provenance.get("browser_reverse")
            and not match.provenance.get("hash_verified")
        ):
            return None

        conf = preset_conf if preset_conf is not None else confidence_from_hash(hash_sim)
        if preset_conf is None and is_person and face_sim >= MIN_FACE_SIMILARITY:
            conf = round(min(0.98, conf * 0.6 + face_sim * 0.4), 4)

        if conf < (0.50 if match.provenance.get("browser_reverse") else min_conf):
            return None

        match_type = match.match_type
        if hash_sim >= 0.95:
            match_type = "identical"
        elif hash_sim >= 0.88:
            match_type = "cropped"

        clean_path = [p for p in match.evidence_path if p and is_public_url(p) and not is_local_path(p)]
        if not clean_path:
            clean_path = [match.source, image_url]

        return match.model_copy(update={
            "confidence": conf,
            "match_type": match_type,
            "match_url": image_url,
            "evidence_path": clean_path,
            "organizations": [],
            "provenance": {
                **match.provenance,
                "hash_similarity": hash_sim,
                "face_similarity": face_sim,
                "hash_verified": hash_sim >= min_hash,
                "face_verified": face_sim >= MIN_FACE_SIMILARITY,
            },
        })

    results = await asyncio.gather(*[_check(m) for m in matches])
    for item in results:
        if item:
            verified.append(item)
    verified.sort(key=lambda m: -m.confidence)
    return verified
