"""Image similarity: perceptual hash, OpenCV ORB, optional InsightFace."""

from __future__ import annotations

import io
import tempfile
from functools import lru_cache
from typing import Any

import httpx

INSIGHTFACE_AVAILABLE: bool | None = None
_OPENCV_AVAILABLE: bool | None = None


def _check_opencv() -> bool:
    global _OPENCV_AVAILABLE
    if _OPENCV_AVAILABLE is None:
        try:
            import cv2  # noqa: F401

            _OPENCV_AVAILABLE = True
        except ImportError:
            _OPENCV_AVAILABLE = False
    return _OPENCV_AVAILABLE


def insightface_available() -> bool:
    global INSIGHTFACE_AVAILABLE
    if INSIGHTFACE_AVAILABLE is None:
        try:
            import insightface  # noqa: F401

            INSIGHTFACE_AVAILABLE = True
        except ImportError:
            INSIGHTFACE_AVAILABLE = False
    return INSIGHTFACE_AVAILABLE


def imagehash_available() -> bool:
    try:
        import imagehash  # noqa: F401

        return True
    except ImportError:
        return False


async def _load_image_bytes(source: str) -> bytes | None:
    if not source:
        return None
    try:
        if source.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(source)
                if resp.status_code == 200:
                    return resp.content
        else:
            with open(source, "rb") as f:
                return f.read()
    except Exception:
        return None
    return None


def _perceptual_hash_similarity(img_a: bytes, img_b: bytes) -> tuple[float, str]:
    from PIL import Image
    import imagehash

    a = Image.open(io.BytesIO(img_a))
    b = Image.open(io.BytesIO(img_b))

    hashes = {
        "ahash": (imagehash.average_hash(a), imagehash.average_hash(b)),
        "phash": (imagehash.phash(a), imagehash.phash(b)),
        "dhash": (imagehash.dhash(a), imagehash.dhash(b)),
    }

    scores: list[float] = []
    parts: list[str] = []
    for name, (ha, hb) in hashes.items():
        dist = ha - hb
        sim = max(0.0, 1.0 - dist / 64.0)
        scores.append(sim)
        parts.append(f"{name}={sim:.3f}")

    mirrored = imagehash.average_hash(a.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
    mirror_sim = max(0.0, 1.0 - (mirrored - hashes["ahash"][1]) / 64.0)
    if mirror_sim > 0.85:
        parts.append(f"mirrored_candidate={mirror_sim:.3f}")
        scores.append(mirror_sim * 0.95)

    return round(max(scores), 4), ", ".join(parts)


def _opencv_orb_similarity(img_a: bytes, img_b: bytes) -> tuple[float, str]:
    import cv2
    import numpy as np

    arr_a = np.frombuffer(img_a, dtype=np.uint8)
    arr_b = np.frombuffer(img_b, dtype=np.uint8)
    mat_a = cv2.imdecode(arr_a, cv2.IMREAD_GRAYSCALE)
    mat_b = cv2.imdecode(arr_b, cv2.IMREAD_GRAYSCALE)
    if mat_a is None or mat_b is None:
        return 0.0, "opencv decode failed"

    orb = cv2.ORB_create(500)
    kp1, des1 = orb.detectAndCompute(mat_a, None)
    kp2, des2 = orb.detectAndCompute(mat_b, None)
    if des1 is None or des2 is None or len(des1) < 2 or len(des2) < 2:
        return 0.0, "insufficient ORB features"

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    if not matches:
        return 0.0, "no ORB matches"

    good = [m for m in matches if m.distance < 50]
    score = min(len(good) / max(len(kp1), len(kp2), 1), 1.0)
    return round(score, 4), f"orb_matches={len(good)}/{len(matches)}"


@lru_cache(maxsize=1)
def _insightface_app():
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


def _face_embedding_similarity(img_a: bytes, img_b: bytes) -> tuple[float, str]:
    import cv2
    import numpy as np

    app = _insightface_app()
    arr_a = np.frombuffer(img_a, dtype=np.uint8)
    arr_b = np.frombuffer(img_b, dtype=np.uint8)
    mat_a = cv2.imdecode(arr_a, cv2.IMREAD_COLOR)
    mat_b = cv2.imdecode(arr_b, cv2.IMREAD_COLOR)
    if mat_a is None or mat_b is None:
        return 0.0, "insightface decode failed"

    faces_a = app.get(mat_a)
    faces_b = app.get(mat_b)
    if not faces_a or not faces_b:
        return 0.0, "no faces detected"

    emb_a = faces_a[0].embedding
    emb_b = faces_b[0].embedding
    cosine = float(np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b) + 1e-9))
    return round(max(cosine, 0.0), 4), f"insightface_cosine={cosine:.3f}"


async def image_similarity(source_a: str | None, source_b: str | None) -> tuple[float, str]:
    if not source_a or not source_b:
        return 0.0, "missing image source"

    if source_a == source_b:
        return 1.0, "same image source"

    bytes_a = await _load_image_bytes(source_a)
    bytes_b = await _load_image_bytes(source_b)
    if not bytes_a or not bytes_b:
        return 0.0, "image load failed"

    scores: list[float] = []
    details: list[str] = []

    if imagehash_available():
        try:
            s, d = _perceptual_hash_similarity(bytes_a, bytes_b)
            scores.append(s)
            details.append(f"perceptual_hash({d})")
        except Exception as exc:
            details.append(f"perceptual_hash_error={exc}")

    if _check_opencv():
        try:
            s, d = _opencv_orb_similarity(bytes_a, bytes_b)
            if s > 0:
                scores.append(s)
            details.append(f"opencv_orb({d})")
        except Exception as exc:
            details.append(f"opencv_error={exc}")

    if insightface_available():
        try:
            s, d = _face_embedding_similarity(bytes_a, bytes_b)
            if s > 0:
                scores.append(s * 1.05)
            details.append(f"insightface({d})")
        except Exception as exc:
            details.append(f"insightface_error={exc}")

    if not scores:
        return 0.0, "; ".join(details) or "no image backends available"

    return round(min(max(scores), 1.0), 4), "; ".join(details)
