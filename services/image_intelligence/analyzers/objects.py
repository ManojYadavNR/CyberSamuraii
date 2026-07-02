"""Object intelligence — YOLO, GroundingDINO, CLIP."""

from __future__ import annotations

from schemas.image_intelligence import ImageFinding
from services.image_intelligence.models import (
    CLIP_LABELS,
    GROUNDING_DINO_LABELS,
    clip_model,
    grounding_dino,
    yolo_model,
)
from services.image_intelligence.runtime import run_in_ml_thread

OBJECT_CATEGORIES = {
    "car": "vehicle",
    "truck": "vehicle",
    "bus": "vehicle",
    "motorcycle": "vehicle",
    "bicycle": "vehicle",
    "train": "vehicle",
    "boat": "vehicle",
    "airplane": "vehicle",
    "person": "person",
    "tie": "uniform",
    "sports ball": "product",
    "bottle": "product",
    "cup": "product",
    "laptop": "product",
    "cell phone": "product",
    "book": "product",
    "clock": "product",
    "chair": "product",
    "tv": "product",
    "logo": "logo",
    "uniform": "uniform",
    "vehicle": "vehicle",
    "building": "building",
    "badge": "badge",
    "product": "product",
    "event banner": "event_banner",
    "landmark": "landmark",
}


def _categorize(label: str) -> str:
    low = label.lower()
    if low in OBJECT_CATEGORIES:
        return OBJECT_CATEGORIES[low]
    if "banner" in low or "sign" in low or "poster" in low:
        return "event_banner"
    if "logo" in low:
        return "logo"
    if "uniform" in low or "badge" in low:
        return "uniform" if "uniform" in low else "badge"
    if "vehicle" in low or "car" in low or "truck" in low:
        return "vehicle"
    if "building" in low or "landmark" in low:
        return "landmark" if "landmark" in low else "building"
    return low


async def analyze_yolo(path: str, url: str | None) -> list[ImageFinding]:
    def _run() -> list[ImageFinding]:
        model = yolo_model()
        results = model.predict(path, verbose=False, conf=0.35)
        findings: list[ImageFinding] = []
        for result in results:
            names = result.names or {}
            for box in result.boxes:
                cls_id = int(box.cls[0])
                label = str(names.get(cls_id, "object"))
                conf = float(box.conf[0])
                category = _categorize(label)
                xyxy = box.xyxy[0].tolist() if hasattr(box.xyxy[0], "tolist") else list(box.xyxy[0])
                findings.append(ImageFinding(
                    category="object",
                    field=category,
                    value=label,
                    source_tool="yolo",
                    extraction_strategy="yolo_detection",
                    confidence=round(min(conf, 0.95), 4),
                    evidence={"label": label, "bbox": xyxy, "category": category, "file": path, "url": url},
                ))
        return findings

    return await run_in_ml_thread(_run)


async def analyze_grounding_dino(path: str, url: str | None) -> list[ImageFinding]:
    def _run() -> list[ImageFinding]:
        import torch
        from PIL import Image

        processor, model, device = grounding_dino()
        image = Image.open(path).convert("RGB")
        text = ". ".join(GROUNDING_DINO_LABELS)
        inputs = processor(images=image, text=text, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        target_sizes = torch.tensor([image.size[::-1]])
        results = processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, box_threshold=0.3, text_threshold=0.25, target_sizes=target_sizes
        )[0]

        findings: list[ImageFinding] = []
        for score, label, box in zip(
            results["scores"].tolist(),
            results["labels"],
            results["boxes"].tolist(),
        ):
            category = _categorize(str(label))
            findings.append(ImageFinding(
                category="object",
                field=category,
                value=str(label),
                source_tool="grounding_dino",
                extraction_strategy="grounding_dino_zero_shot",
                confidence=round(min(float(score), 0.95), 4),
                evidence={"label": str(label), "bbox": box, "category": category, "file": path, "url": url},
            ))
        return findings

    return await run_in_ml_thread(_run)


async def analyze_clip(path: str, url: str | None) -> list[ImageFinding]:
    def _run() -> list[ImageFinding]:
        from PIL import Image

        processor, model, device = clip_model()
        image = Image.open(path).convert("RGB")
        inputs = processor(text=CLIP_LABELS, images=image, return_tensors="pt", padding=True).to(device)
        with __import__("torch").no_grad():
            out = model(**inputs)
            probs = out.logits_per_image.softmax(dim=1).cpu().numpy()[0]
        ranked = sorted(zip(CLIP_LABELS, probs), key=lambda x: x[1], reverse=True)[:5]

        findings: list[ImageFinding] = []
        for label, prob in ranked:
            if prob < 0.08:
                continue
            category = _categorize(label)
            findings.append(ImageFinding(
                category="object",
                field=category,
                value=label,
                source_tool="clip",
                extraction_strategy="clip_zero_shot",
                confidence=round(min(float(prob), 0.95), 4),
                evidence={"label": label, "category": category, "file": path, "url": url},
            ))
        return findings

    return await run_in_ml_thread(_run)


async def analyze_objects(path: str, url: str | None) -> list[ImageFinding]:
    import asyncio

    results = await asyncio.gather(
        analyze_yolo(path, url),
        analyze_grounding_dino(path, url),
        analyze_clip(path, url),
        return_exceptions=True,
    )
    findings: list[ImageFinding] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        findings.extend(result)
    return findings
