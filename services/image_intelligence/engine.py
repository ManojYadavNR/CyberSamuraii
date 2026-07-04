"""Image Intelligence Engine — parallel module execution and fusion integration."""

from __future__ import annotations

import asyncio
from typing import Any

from adapters.image_common import resolve_image_source
from schemas.common import ToolResult
from schemas.fusion import Entity, FusionOutput
from schemas.image_intelligence import ImageFinding, ImageIntelligenceOutput
from services.fusion_engine import (
    _apply_scores,
    _collect_signals,
    apply_account_corroboration,
    deduplicate_entities,
)
from services.image_intelligence.analyzers.face import analyze_faces
from services.image_intelligence.analyzers.fingerprint import analyze_fingerprint
from services.image_intelligence.analyzers.metadata import analyze_metadata
from services.image_intelligence.analyzers.objects import analyze_objects
from services.image_intelligence.analyzers.ocr import analyze_ocr
from services.image_intelligence.context import build_image_search_context
from services.image_intelligence.entity_builder import build_entities

MODULES = ("face", "metadata", "ocr", "object", "fingerprint")

TOOL_TO_MODULE: dict[str, str] = {
    "insightface": "face",
    "deepface": "face",
    "facenet": "face",
    "opencv_face": "face",
    "pillow": "metadata",
    "exiftool": "metadata",
    "hachoir": "metadata",
    "tesseract": "ocr",
    "easyocr": "ocr",
    "paddleocr": "ocr",
    "yolo": "object",
    "grounding_dino": "object",
    "clip": "object",
    "imagehash": "fingerprint",
    "opencv": "fingerprint",
}


class ImageIntelligenceEngine:
    """Runs all image intelligence modules in parallel and produces fusion-ready entities."""

    async def analyze(
        self,
        image_source: str,
        *,
        tool_results: list[ToolResult] | None = None,
        fast: bool = False,
    ) -> ImageIntelligenceOutput:
        path, url, err = await resolve_image_source(image_source)
        if err or not path:
            return ImageIntelligenceOutput(
                image_source=image_source,
                modules_failed=["resolve_image"],
            )

        modules_run: list[str] = []
        modules_failed: list[str] = []
        findings: list[ImageFinding] = []
        face_count = 0
        perceptual_hashes: dict[str, str] = {}
        similarity_signature: str | None = None

        completed_modules: set[str] = set()
        attempted_modules: set[str] = set()
        for tr in tool_results or []:
            mod = TOOL_TO_MODULE.get(tr.tool)
            if not mod:
                continue
            attempted_modules.add(mod)
            if tr.success:
                completed_modules.add(mod)

        async def _run_face() -> None:
            nonlocal face_count
            try:
                face_findings, count = await analyze_faces(path, url)
                findings.extend(face_findings)
                face_count = count
                modules_run.append("face")
            except Exception as exc:
                modules_failed.append(f"face:{type(exc).__name__}")

        async def _run_metadata() -> None:
            try:
                findings.extend(await analyze_metadata(path, url))
                modules_run.append("metadata")
            except Exception as exc:
                modules_failed.append(f"metadata:{type(exc).__name__}")

        async def _run_ocr() -> None:
            try:
                findings.extend(await analyze_ocr(path, url))
                modules_run.append("ocr")
            except Exception as exc:
                modules_failed.append(f"ocr:{type(exc).__name__}")

        async def _run_objects() -> None:
            try:
                findings.extend(await analyze_objects(path, url))
                modules_run.append("object")
            except Exception as exc:
                modules_failed.append(f"object:{type(exc).__name__}")

        async def _run_fingerprint() -> None:
            nonlocal perceptual_hashes, similarity_signature
            try:
                fp_findings, hashes, sig = await analyze_fingerprint(path, url)
                findings.extend(fp_findings)
                perceptual_hashes = hashes
                similarity_signature = sig
                modules_run.append("fingerprint")
            except Exception as exc:
                modules_failed.append(f"fingerprint:{type(exc).__name__}")

        # When adapters already attempted a module, do not re-run heavy ML
        # (timeouts leave the shared executor busy and look like a hang).
        async with asyncio.TaskGroup() as tg:
            if "fingerprint" not in completed_modules and "fingerprint" not in attempted_modules:
                tg.create_task(_run_fingerprint())
            if not fast:
                if "face" not in completed_modules and "face" not in attempted_modules:
                    tg.create_task(_run_face())
                if "metadata" not in completed_modules and "metadata" not in attempted_modules:
                    tg.create_task(_run_metadata())
                if "ocr" not in completed_modules and "ocr" not in attempted_modules:
                    tg.create_task(_run_ocr())
                if "object" not in completed_modules and "object" not in attempted_modules:
                    tg.create_task(_run_objects())

        findings.extend(self._findings_from_tool_results(tool_results or [], path, url))

        if not perceptual_hashes:
            for tr in tool_results or []:
                if not tr.data:
                    continue
                for item in tr.data:
                    if not isinstance(item, dict):
                        continue
                    hashes = item.get("perceptual_hashes") or item.get("hashes")
                    if isinstance(hashes, dict):
                        perceptual_hashes.update({str(k): str(v) for k, v in hashes.items()})
                    for key in ("phash", "ahash", "dhash", "whash"):
                        if item.get(key):
                            perceptual_hashes[key] = str(item[key])

        entities = build_entities(
            findings,
            image_source=image_source,
            image_path=path,
            image_url=url,
            perceptual_hashes=perceptual_hashes,
            similarity_signature=similarity_signature,
        )

        ctx = build_image_search_context(tool_results)
        content_type = ctx.get("image_category") or None
        for finding in findings:
            if finding.source_tool == "clip" and finding.confidence >= 0.15:
                content_type = finding.value.lower()
                break
        ocr_text = ctx.get("ocr_text") or None
        if not face_count:
            face_count = sum(
                1 for f in findings if f.category == "face" and f.field in ("face_embedding", "face_detection")
            )
            if any(f.field == "face_count" for f in findings):
                for f in findings:
                    if f.field == "face_count":
                        try:
                            face_count = max(face_count, int(f.value))
                        except ValueError:
                            pass

        return ImageIntelligenceOutput(
            image_source=image_source,
            image_path=path,
            image_url=url,
            face_count=face_count,
            findings=findings,
            entities=entities,
            modules_run=modules_run,
            modules_failed=modules_failed,
            perceptual_hashes=perceptual_hashes,
            similarity_signature=similarity_signature,
            content_type=content_type,
            ocr_text=ocr_text,
        )

    def _findings_from_tool_results(
        self,
        tool_results: list[ToolResult],
        path: str,
        url: str | None,
    ) -> list[ImageFinding]:
        """Lift structured rows from parallel adapter outputs into unified findings."""
        findings: list[ImageFinding] = []
        for tr in tool_results:
            if not tr.data:
                continue
            for item in tr.data:
                if not isinstance(item, dict):
                    continue
                platform = str(item.get("platform", ""))
                extra = {k: v for k, v in item.items() if k not in ("platform", "source_tool", "url")}
                if extra.get("status") in ("unavailable", "placeholder"):
                    continue
                if platform == "ocr_text" and extra.get("text"):
                    from services.image_intelligence.text_parser import parse_ocr_entities

                    for field, values in parse_ocr_entities(str(extra["text"])).items():
                        for val in values:
                            findings.append(ImageFinding(
                                category="ocr",
                                field=field,
                                value=val,
                                source_tool=tr.tool,
                                extraction_strategy=f"{tr.tool}_adapter_ocr",
                                confidence=0.75,
                                evidence={"file": path, "url": url},
                            ))
                elif extra.get("category") == "face" or extra.get("field") in (
                    "face_embedding", "face_detection", "face_count",
                ):
                    findings.append(ImageFinding(
                        category="face",
                        field=str(extra.get("field") or "face_embedding"),
                        value=str(extra.get("value") or "face"),
                        source_tool=tr.tool,
                        extraction_strategy=str(extra.get("extraction_strategy") or f"{tr.tool}_adapter_face"),
                        confidence=float(extra.get("confidence") or 0.8),
                        evidence={**extra, "file": path, "url": url},
                    ))
                elif extra.get("faces_detected") is not None:
                    findings.append(ImageFinding(
                        category="face",
                        field="face_count",
                        value=str(extra["faces_detected"]),
                        source_tool=tr.tool,
                        extraction_strategy=f"{tr.tool}_adapter_faces",
                        confidence=0.8,
                        evidence={**extra, "file": path, "url": url},
                    ))
                elif extra.get("exif") or platform in ("metadata_extraction", "exiftool_metadata"):
                    findings.append(ImageFinding(
                        category="metadata",
                        field="adapter_metadata",
                        value=path,
                        source_tool=tr.tool,
                        extraction_strategy=f"{tr.tool}_adapter_metadata",
                        confidence=0.78,
                        evidence={**extra, "file": path, "url": url},
                    ))
        return findings

    def merge_into_fusion(self, fusion: FusionOutput, intel: ImageIntelligenceOutput) -> FusionOutput:
        """Merge engine entities into an existing fusion output and re-score."""
        if not intel.entities:
            return fusion

        combined = list(fusion.entities or []) + list(intel.entities)
        deduped = deduplicate_entities(apply_account_corroboration(combined))
        scored = _apply_scores(deduped)

        evidence_map: dict[str, Any] = dict(fusion.evidence_map or {})
        for entity in scored:
            key = f"{entity.type}:{entity.canonical_value or entity.value}"
            evidence_map[key] = {
                "sources": entity.sources,
                "signals": _collect_signals(entity),
                "reliability_score": entity.reliability_score,
                "fusion_score": entity.fusion_score,
                "evidence_count": len(entity.evidence),
            }

        fusion_score = 0.0
        if scored:
            fusion_score = round(sum(e.fusion_score for e in scored) / len(scored), 4)

        return fusion.model_copy(update={
            "entities": combined,
            "deduplicated_entities": scored,
            "fusion_score": fusion_score,
            "evidence_map": evidence_map,
        })


image_intelligence_engine = ImageIntelligenceEngine()
