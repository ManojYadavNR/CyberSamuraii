"""Image fingerprinting — perceptual hashes and OpenCV feature signatures."""

from __future__ import annotations

from services.image_intelligence.runtime import run_in_ml_thread

from schemas.image_intelligence import ImageFinding


def _fingerprint_sync(path: str, url: str | None) -> tuple[list[ImageFinding], dict[str, str], str | None]:
    findings: list[ImageFinding] = []
    hashes: dict[str, str] = {}
    similarity_signature: str | None = None

    try:
        import imagehash
        from PIL import Image

        img = Image.open(path)
        for name, func in (
            ("ahash", imagehash.average_hash),
            ("phash", imagehash.phash),
            ("dhash", imagehash.dhash),
            ("whash", imagehash.whash),
        ):
            h = str(func(img))
            hashes[name] = h
            findings.append(ImageFinding(
                category="fingerprint",
                field=f"perceptual_hash_{name}",
                value=h,
                source_tool="imagehash",
                extraction_strategy="perceptual_hash",
                confidence=0.94,
                evidence={"hash_type": name, "file": path, "url": url},
            ))
    except Exception:
        pass

    try:
        import cv2
        import numpy as np

        mat = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if mat is not None:
            orb = cv2.ORB_create(500)
            keypoints, descriptors = orb.detectAndCompute(mat, None)
            if descriptors is not None and len(descriptors) > 0:
                digest = hashlib.sha256(descriptors.tobytes()).hexdigest()[:32]
                similarity_signature = f"orb:{len(keypoints)}:{digest}"
                findings.append(ImageFinding(
                    category="fingerprint",
                    field="opencv_orb_signature",
                    value=similarity_signature,
                    source_tool="opencv",
                    extraction_strategy="opencv_orb_fingerprint",
                    confidence=0.86,
                    evidence={
                        "keypoint_count": len(keypoints),
                        "descriptor_rows": len(descriptors),
                        "file": path,
                        "url": url,
                    },
                ))
    except Exception:
        pass

    return findings, hashes, similarity_signature


async def analyze_fingerprint(path: str, url: str | None) -> tuple[list[ImageFinding], dict[str, str], str | None]:
    return await run_in_ml_thread(_fingerprint_sync, path, url)
