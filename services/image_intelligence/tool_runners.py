"""Per-tool runners used by parallel image adapters."""

from __future__ import annotations

from adapters.image_common import resolve_image_source
from schemas.common import ToolResult
from services.image_intelligence.adapter_bridge import findings_to_tool_result
from services.image_intelligence.analyzers.face import (
    analyze_deepface,
    analyze_facenet,
    analyze_insightface,
    analyze_opencv_face,
)
from services.image_intelligence.analyzers.metadata import analyze_exiftool, analyze_hachoir, analyze_pillow
from services.image_intelligence.analyzers.ocr import analyze_easyocr, analyze_paddleocr, analyze_tesseract
from services.image_intelligence.analyzers.objects import analyze_clip, analyze_grounding_dino, analyze_yolo


async def _resolve(query: str) -> tuple[str | None, str | None, str | None]:
    return await resolve_image_source(query)


async def run_opencv_face(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="opencv_face", success=False, error=err or "no image source")
    try:
        findings = await analyze_opencv_face(path, url)
        return findings_to_tool_result("opencv_face", findings, platform="opencv_face_detection", group="face_analysis")
    except Exception as exc:
        return ToolResult(tool="opencv_face", success=False, error=str(exc))


async def run_insightface(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="insightface", success=False, error=err or "no image source")
    try:
        findings = await analyze_insightface(path, url)
        return findings_to_tool_result("insightface", findings, platform="face_detection", group="face_analysis")
    except Exception as exc:
        return ToolResult(tool="insightface", success=False, error=str(exc))


async def run_deepface(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="deepface", success=False, error=err or "no image source")
    try:
        findings = await analyze_deepface(path, url)
        return findings_to_tool_result("deepface", findings, platform="deepface_analysis", group="face_analysis")
    except Exception as exc:
        return ToolResult(tool="deepface", success=False, error=str(exc))


async def run_facenet(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="facenet", success=False, error=err or "no image source")
    try:
        findings = await analyze_facenet(path, url)
        return findings_to_tool_result("facenet", findings, platform="facenet_analysis", group="face_analysis")
    except Exception as exc:
        return ToolResult(tool="facenet", success=False, error=str(exc))


async def run_pillow(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="pillow", success=False, error=err or "no image source")
    try:
        findings = await analyze_pillow(path, url)
        return findings_to_tool_result("pillow", findings, platform="metadata_extraction", group="metadata")
    except Exception as exc:
        return ToolResult(tool="pillow", success=False, error=str(exc))


async def run_exiftool(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="exiftool", success=False, error=err or "no image source")
    try:
        findings = await analyze_exiftool(path, url)
        return findings_to_tool_result("exiftool", findings, platform="exiftool_metadata", group="metadata")
    except Exception as exc:
        return ToolResult(tool="exiftool", success=False, error=str(exc))


async def run_hachoir(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="hachoir", success=False, error=err or "no image source")
    try:
        findings = await analyze_hachoir(path, url)
        return findings_to_tool_result("hachoir", findings, platform="hachoir_metadata", group="metadata")
    except Exception as exc:
        return ToolResult(tool="hachoir", success=False, error=str(exc))


async def run_tesseract(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="tesseract", success=False, error=err or "no image source")
    try:
        findings = await analyze_tesseract(path, url)
        return findings_to_tool_result("tesseract", findings, platform="ocr_text", group="ocr")
    except Exception as exc:
        return ToolResult(tool="tesseract", success=False, error=str(exc))


async def run_easyocr(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="easyocr", success=False, error=err or "no image source")
    try:
        findings = await analyze_easyocr(path, url)
        return findings_to_tool_result("easyocr", findings, platform="easyocr", group="ocr")
    except Exception as exc:
        return ToolResult(tool="easyocr", success=False, error=str(exc))


async def run_paddleocr(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="paddleocr", success=False, error=err or "no image source")
    try:
        findings = await analyze_paddleocr(path, url)
        return findings_to_tool_result("paddleocr", findings, platform="paddleocr", group="ocr")
    except Exception as exc:
        return ToolResult(tool="paddleocr", success=False, error=str(exc))


async def run_yolo(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="yolo", success=False, error=err or "no image source")
    try:
        findings = await analyze_yolo(path, url)
        return findings_to_tool_result("yolo", findings, platform="yolo_detection", group="object_detection")
    except Exception as exc:
        return ToolResult(tool="yolo", success=False, error=str(exc))


async def run_grounding_dino(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="grounding_dino", success=False, error=err or "no image source")
    try:
        findings = await analyze_grounding_dino(path, url)
        return findings_to_tool_result("grounding_dino", findings, platform="grounding_dino_detection", group="object_detection")
    except Exception as exc:
        return ToolResult(tool="grounding_dino", success=False, error=str(exc))


async def run_clip(query: str) -> ToolResult:
    path, url, err = await _resolve(query)
    if err or not path:
        return ToolResult(tool="clip", success=False, error=err or "no image source")
    try:
        findings = await analyze_clip(path, url)
        return findings_to_tool_result("clip", findings, platform="clip_embedding", group="object_detection")
    except Exception as exc:
        return ToolResult(tool="clip", success=False, error=str(exc))
