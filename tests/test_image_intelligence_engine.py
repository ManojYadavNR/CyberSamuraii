"""Tests for Image Intelligence Engine."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from schemas.common import ToolResult
from schemas.image_intelligence import ImageFinding
from services.image_intelligence.engine import ImageIntelligenceEngine
from services.image_intelligence.text_parser import parse_ocr_entities


def _make_test_image(text: str = "Contact alice@example.org @alice_handle") -> str:
    img = Image.new("RGB", (400, 200), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.text((20, 80), text, fill=(0, 0, 0))
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    return path


@pytest.fixture
def mock_heavy_analyzers(monkeypatch):
    """Avoid loading DeepFace/YOLO/etc. in unit tests — integration uses real models at runtime."""

    async def mock_faces(path, url):
        return [
            ImageFinding(
                category="face", field="face_count", value="1", source_tool="opencv_face",
                extraction_strategy="test", confidence=0.8, evidence={"file": path},
            )
        ], 1

    async def mock_metadata(path, url):
        return [
            ImageFinding(
                category="metadata", field="timestamp", value="2024:01:01",
                source_tool="pillow", extraction_strategy="test", confidence=0.8, evidence={"file": path},
            )
        ]

    async def mock_ocr(path, url):
        return [
            ImageFinding(
                category="ocr", field="emails", value="alice@example.org",
                source_tool="tesseract", extraction_strategy="test", confidence=0.9, evidence={"file": path},
            )
        ]

    async def mock_objects(path, url):
        return [
            ImageFinding(
                category="object", field="vehicle", value="car",
                source_tool="yolo", extraction_strategy="test", confidence=0.7, evidence={"file": path},
            )
        ]

    async def mock_fingerprint(path, url):
        from services.image_intelligence.analyzers.fingerprint import analyze_fingerprint

        return await analyze_fingerprint(path, url)

    monkeypatch.setattr("services.image_intelligence.engine.analyze_faces", mock_faces)
    monkeypatch.setattr("services.image_intelligence.engine.analyze_metadata", mock_metadata)
    monkeypatch.setattr("services.image_intelligence.engine.analyze_ocr", mock_ocr)
    monkeypatch.setattr("services.image_intelligence.engine.analyze_objects", mock_objects)
    monkeypatch.setattr("services.image_intelligence.engine.analyze_fingerprint", mock_fingerprint)


def test_parse_ocr_entities_extracts_structured_fields():
    text = "Alice Johnson works at Acme Corp LLC. Email: bob@test.io phone +1 555-123-4567 @validuser hackathon 2026"
    parsed = parse_ocr_entities(text)
    assert "bob@test.io" in parsed.get("emails", [])
    assert parsed.get("usernames")
    assert parsed.get("names") or parsed.get("companies")
    assert parsed.get("events")


@pytest.mark.asyncio
async def test_image_intelligence_engine_produces_entities_and_fingerprints(mock_heavy_analyzers):
    path = _make_test_image()
    try:
        engine = ImageIntelligenceEngine()
        output = await engine.analyze(path)
        assert output.image_path == path
        assert output.perceptual_hashes
        assert output.entities
        assert any(e.type == "image" for e in output.entities)
        assert output.modules_run
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_merge_into_fusion_adds_engine_entities(mock_heavy_analyzers):
    from services.fusion import build_fusion_output

    path = _make_test_image("test@corp.com Summit Event")
    try:
        engine = ImageIntelligenceEngine()
        intel = await engine.analyze(path, tool_results=[
            ToolResult(tool="tesseract", success=True, data=[{
                "platform": "ocr_text",
                "source_tool": "tesseract",
                "text": "test@corp.com Summit Event",
                "file": path,
            }]),
        ])
        base = build_fusion_output([], "image_intel", path)
        merged = engine.merge_into_fusion(base, intel)
        assert merged.deduplicated_entities
        assert merged.fusion_score >= 0
        assert intel.findings
    finally:
        Path(path).unlink(missing_ok=True)
