"""Face analysis — InsightFace, DeepFace, FaceNet, OpenCV (parallel, face-only identity)."""

from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Any

from schemas.image_intelligence import ImageFinding
from services.image_intelligence.models import facenet_models, insightface_app, opencv_face_cascade
from services.image_intelligence.runtime import run_in_ml_thread
from services.face_crops import save_face_crop


def _embedding_signature(vec: Any) -> str:
    import numpy as np

    arr = np.asarray(vec, dtype=np.float32).flatten()
    digest = hashlib.sha256(arr.tobytes()).hexdigest()[:24]
    return f"emb:{digest}"


def _embedding_vector(vec: Any) -> list[float]:
    import numpy as np

    return np.asarray(vec, dtype=np.float32).flatten().tolist()


def _crop_face(path: str, bbox: list[float], index: int, *, tool: str = "face") -> str:
    return save_face_crop(path, bbox, tool=tool, index=index)


async def analyze_opencv_face(path: str, url: str | None) -> list[ImageFinding]:
    def _run() -> list[ImageFinding]:
        import cv2

        cascade = opencv_face_cascade()
        mat = cv2.imread(path)
        if mat is None:
            raise RuntimeError(f"opencv failed to read image: {path}")
        gray = cv2.cvtColor(mat, cv2.COLOR_BGR2GRAY)
        boxes = cascade.detectMultiScale(gray, 1.1, 4)
        findings: list[ImageFinding] = []
        for i, (x, y, w, h) in enumerate(boxes[:5]):
            crop_path = _crop_face(path, [x, y, x + w, y + h], i, tool="opencv")
            findings.append(ImageFinding(
                category="face",
                field="face_detection",
                value=f"opencv_face_{i}",
                source_tool="opencv_face",
                extraction_strategy="opencv_haar_cascade",
                confidence=0.72,
                evidence={
                    "bbox": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                    "face_index": i,
                    "crop_path": crop_path,
                    "file": path,
                    "url": url,
                    "identity_signal": "face_bbox_only",
                },
            ))
        return findings

    return await run_in_ml_thread(_run)


async def analyze_insightface(path: str, url: str | None) -> list[ImageFinding]:
    def _run() -> list[ImageFinding]:
        import cv2

        app = insightface_app()
        mat = cv2.imread(path)
        if mat is None:
            raise RuntimeError(f"insightface failed to read image: {path}")
        faces = app.get(mat)
        findings: list[ImageFinding] = []
        for i, face in enumerate(faces[:5]):
            bbox = face.bbox.tolist() if hasattr(face.bbox, "tolist") else list(face.bbox)
            quality = float(getattr(face, "det_score", 0.0))
            crop_path = _crop_face(path, bbox, 100 + i, tool="insightface")
            emb = getattr(face, "embedding", None)
            emb_sig = _embedding_signature(emb)
            findings.append(ImageFinding(
                category="face",
                field="face_embedding",
                value=emb_sig,
                source_tool="insightface",
                extraction_strategy="insightface_embedding",
                confidence=min(0.95, 0.6 + quality * 0.35),
                evidence={
                    "bbox": bbox,
                    "face_quality_score": round(quality, 4),
                    "face_index": i,
                    "embedding_signature": emb_sig,
                    "embedding_vector": _embedding_vector(emb) if emb is not None else None,
                    "age": float(getattr(face, "age", 0)) if hasattr(face, "age") else None,
                    "gender": int(getattr(face, "gender", -1)) if hasattr(face, "gender") else None,
                    "crop_path": crop_path,
                    "file": path,
                    "url": url,
                    "identity_signal": "face_embedding",
                },
            ))
        return findings

    return await run_in_ml_thread(_run)


async def analyze_deepface(path: str, url: str | None) -> list[ImageFinding]:
    def _run() -> list[ImageFinding]:
        from deepface import DeepFace

        reps = DeepFace.represent(
            img_path=path,
            model_name="Facenet",
            enforce_detection=False,
            detector_backend="opencv",
        )
        if not isinstance(reps, list):
            reps = [reps]
        findings: list[ImageFinding] = []
        for i, rep in enumerate(reps[:5]):
            emb = rep.get("embedding")
            emb_sig = _embedding_signature(emb) if emb is not None else f"deepface_{i}"
            findings.append(ImageFinding(
                category="face",
                field="face_embedding",
                value=emb_sig,
                source_tool="deepface",
                extraction_strategy="deepface_represent",
                confidence=0.82,
                evidence={
                    "face_index": i,
                    "embedding_signature": emb_sig,
                    "embedding_vector": _embedding_vector(emb) if emb is not None else None,
                    "facial_area": rep.get("facial_area"),
                    "file": path,
                    "url": url,
                    "identity_signal": "face_embedding",
                },
            ))
        return findings

    return await run_in_ml_thread(_run)


async def analyze_facenet(path: str, url: str | None) -> list[ImageFinding]:
    def _run() -> list[ImageFinding]:
        import torch
        from PIL import Image

        mtcnn, resnet, device = facenet_models()
        img = Image.open(path).convert("RGB")
        faces = mtcnn(img)
        if faces is None:
            return []

        findings: list[ImageFinding] = []
        if faces.dim() == 3:
            faces = faces.unsqueeze(0)
        boxes, _ = mtcnn.detect(img)
        for i in range(min(faces.shape[0], 5)):
            face_tensor = faces[i].unsqueeze(0).to(device)
            with torch.no_grad():
                embedding = resnet(face_tensor).cpu().numpy().flatten()
            emb_sig = _embedding_signature(embedding)
            bbox = None
            if boxes is not None and len(boxes) > i and boxes[i] is not None:
                x1, y1, x2, y2 = boxes[i]
                bbox = [float(x1), float(y1), float(x2), float(y2)]
                crop_path = _crop_face(path, bbox, 200 + i, tool="facenet")
            else:
                crop_path = None
            findings.append(ImageFinding(
                category="face",
                field="face_embedding",
                value=emb_sig,
                source_tool="facenet",
                extraction_strategy="facenet_vggface2",
                confidence=0.84,
                evidence={
                    "face_index": i,
                    "embedding_signature": emb_sig,
                    "embedding_vector": _embedding_vector(embedding),
                    "bbox": bbox,
                    "crop_path": crop_path,
                    "file": path,
                    "url": url,
                    "identity_signal": "face_embedding",
                },
            ))
        return findings

    return await run_in_ml_thread(_run)


async def _safe_face_analyzer(analyzer, path: str, url: str | None) -> list[ImageFinding]:
    try:
        return await analyzer(path, url)
    except Exception:
        return []


async def analyze_faces(path: str, url: str | None) -> tuple[list[ImageFinding], int]:
    """Run all face backends in parallel — identity matching is face-based only."""
    analyzers = (analyze_insightface, analyze_deepface, analyze_facenet, analyze_opencv_face)
    results = await asyncio.gather(*[_safe_face_analyzer(a, path, url) for a in analyzers])

    findings: list[ImageFinding] = []
    max_faces = 0
    for result in results:
        findings.extend(result)
        for f in result:
            if f.field in ("face_detection", "face_embedding"):
                max_faces = max(max_faces, int(f.evidence.get("face_index", 0)) + 1)

    if max_faces:
        findings.insert(0, ImageFinding(
            category="face",
            field="face_count",
            value=str(max_faces),
            source_tool="image_intelligence_engine",
            extraction_strategy="face_count_aggregate",
            confidence=0.88,
            evidence={"face_count": max_faces, "file": path, "url": url},
        ))

    try:
        from services.face_intelligence.kb import store_findings_in_kb
        store_findings_in_kb(findings, seed_image=path)
    except Exception:
        pass

    return findings, max_faces
