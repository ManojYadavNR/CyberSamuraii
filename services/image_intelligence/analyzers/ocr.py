"""OCR intelligence — Tesseract, EasyOCR, PaddleOCR."""

from __future__ import annotations

import shutil

from schemas.image_intelligence import ImageFinding
from services.image_intelligence.models import easyocr_reader, paddle_ocr
from services.image_intelligence.runtime import run_in_ml_thread
from services.image_intelligence.text_parser import parse_ocr_entities

_OCR_CONFIDENCE = {
    "emails": 0.92,
    "phones": 0.85,
    "urls": 0.88,
    "usernames": 0.78,
    "names": 0.72,
    "companies": 0.7,
    "events": 0.68,
    "visible_text": 0.8,
}


def _require_tesseract() -> None:
    if not shutil.which("tesseract"):
        raise RuntimeError("tesseract binary required — run: scripts/install_tools.sh")


def _findings_from_text(text: str, tool: str, path: str, url: str | None) -> list[ImageFinding]:
    if not text.strip():
        return []
    findings: list[ImageFinding] = []
    parsed = parse_ocr_entities(text)
    for field, values in parsed.items():
        conf = _OCR_CONFIDENCE.get(field, 0.65)
        for val in values:
            findings.append(ImageFinding(
                category="ocr",
                field=field,
                value=val,
                source_tool=tool,
                extraction_strategy=f"{tool}_ocr_parse",
                confidence=conf,
                evidence={"raw_text_sample": text[:500], "text": text[:5000], "file": path, "url": url},
            ))
    return findings


async def analyze_tesseract(path: str, url: str | None) -> list[ImageFinding]:
    _require_tesseract()

    def _run() -> list[ImageFinding]:
        import pytesseract
        from PIL import Image

        text = pytesseract.image_to_string(Image.open(path))
        return _findings_from_text(text, "tesseract", path, url)

    return await run_in_ml_thread(_run)


async def analyze_easyocr(path: str, url: str | None) -> list[ImageFinding]:
    def _run() -> list[ImageFinding]:
        reader = easyocr_reader()
        lines = reader.readtext(path, detail=0, paragraph=True)
        text = "\n".join(str(line) for line in lines if line).strip()
        return _findings_from_text(text, "easyocr", path, url)

    return await run_in_ml_thread(_run)


async def analyze_paddleocr(path: str, url: str | None) -> list[ImageFinding]:
    def _run() -> list[ImageFinding]:
        ocr = paddle_ocr()
        result = ocr.ocr(path, cls=True)
        lines: list[str] = []
        for block in result or []:
            for row in block or []:
                if row and len(row) > 1 and row[1]:
                    lines.append(str(row[1][0]))
        text = "\n".join(lines).strip()
        return _findings_from_text(text, "paddleocr", path, url)

    return await run_in_ml_thread(_run)


async def analyze_ocr(path: str, url: str | None) -> list[ImageFinding]:
    import asyncio

    results = await asyncio.gather(
        analyze_tesseract(path, url),
        analyze_easyocr(path, url),
        analyze_paddleocr(path, url),
        return_exceptions=True,
    )
    findings: list[ImageFinding] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        findings.extend(result)
    return findings
