"""Metadata analysis — ExifTool, Pillow, Hachoir."""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from schemas.image_intelligence import ImageFinding
from services.image_intelligence.runtime import run_in_ml_thread


def _gps_from_piexif(path: str) -> dict[str, float] | None:
    try:
        import piexif
    except ImportError:
        return None
    try:
        exif = piexif.load(path)
    except Exception:
        return None
    gps = exif.get("GPS")
    if not gps:
        return None

    def _ratio_to_float(ratio: tuple[int, int]) -> float:
        return float(ratio[0]) / float(ratio[1]) if ratio[1] else 0.0

    lat = gps.get(piexif.GPSIFD.GPSLatitude)
    lat_ref = gps.get(piexif.GPSIFD.GPSLatitudeRef, b"N")
    lon = gps.get(piexif.GPSIFD.GPSLongitude)
    lon_ref = gps.get(piexif.GPSIFD.GPSLongitudeRef, b"E")
    if lat is None or lon is None:
        return None

    lat_deg = _ratio_to_float(lat[0]) + _ratio_to_float(lat[1]) / 60 + _ratio_to_float(lat[2]) / 3600
    lon_deg = _ratio_to_float(lon[0]) + _ratio_to_float(lon[1]) / 60 + _ratio_to_float(lon[2]) / 3600
    if lat_ref in (b"S", "S"):
        lat_deg *= -1
    if lon_ref in (b"W", "W"):
        lon_deg *= -1
    return {"latitude": round(lat_deg, 6), "longitude": round(lon_deg, 6)}


def _pillow_metadata(path: str) -> dict[str, Any]:
    from PIL import Image
    from PIL.ExifTags import TAGS

    meta: dict[str, Any] = {}
    with Image.open(path) as img:
        meta["format"] = img.format
        meta["size"] = {"width": img.width, "height": img.height}
        meta["mode"] = img.mode
        exif = img._getexif() or {}
        exif_data = {}
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            if isinstance(value, bytes):
                value = value.decode(errors="replace")[:200]
            exif_data[str(tag)] = value
        meta["exif"] = exif_data
    gps = _gps_from_piexif(path)
    if gps:
        meta["gps"] = gps
    return meta


async def _exiftool_metadata(path: str) -> dict[str, Any]:
    if not shutil.which("exiftool"):
        raise RuntimeError("exiftool required — run: scripts/install_tools.sh")
    proc = await asyncio.create_subprocess_exec(
        "exiftool", "-json", path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace") or "exiftool failed")
    import json

    data = json.loads(stdout.decode(errors="replace"))
    return data[0] if data else {}


def _hachoir_metadata(path: str) -> dict[str, Any]:
    from hachoir.metadata import extractMetadata
    from hachoir.parser import createParser

    parser = createParser(path)
    if not parser:
        raise RuntimeError(f"hachoir could not parse: {path}")
    with parser:
        metadata = extractMetadata(parser)
        if not metadata:
            return {"file": path}
        out: dict[str, Any] = {"file": path}
        for item in metadata.exportPlaintext():
            if ":" in item:
                key, val = item.split(":", 1)
                out[key.strip()] = val.strip()
        return out


def _add_meta_finding(
    findings: list[ImageFinding],
    *,
    field: str,
    value: str,
    tool: str,
    strategy: str,
    confidence: float,
    evidence: dict[str, Any],
) -> None:
    findings.append(ImageFinding(
        category="metadata",
        field=field,
        value=value,
        source_tool=tool,
        extraction_strategy=strategy,
        confidence=confidence,
        evidence=evidence,
    ))


async def analyze_pillow(path: str, url: str | None) -> list[ImageFinding]:
    pillow = await run_in_ml_thread(_pillow_metadata, path)
    findings: list[ImageFinding] = []
    exif = pillow.get("exif") or {}

    for key in ("DateTimeOriginal", "DateTime", "CreateDate", "ModifyDate"):
        if exif.get(key):
            _add_meta_finding(
                findings, field="timestamp", value=str(exif[key]), tool="pillow",
                strategy="exif_timestamp", confidence=0.86,
                evidence={"exif_tag": key, "file": path, "url": url},
            )
            break
    for key in ("Make", "Model"):
        if exif.get(key):
            _add_meta_finding(
                findings, field="camera", value=str(exif[key]), tool="pillow",
                strategy="exif_camera", confidence=0.84,
                evidence={"exif_tag": key, "file": path, "url": url},
            )
    if exif.get("Software"):
        _add_meta_finding(
            findings, field="software", value=str(exif["Software"]), tool="pillow",
            strategy="exif_software", confidence=0.82,
            evidence={"file": path, "url": url},
        )
    gps = pillow.get("gps")
    if gps:
        _add_meta_finding(
            findings, field="gps_coordinates", value=f"{gps['latitude']},{gps['longitude']}",
            tool="pillow", strategy="exif_gps", confidence=0.9,
            evidence={**gps, "file": path, "url": url},
        )
    _add_meta_finding(
        findings, field="image_metadata", value=path, tool="pillow",
        strategy="pillow_metadata_bundle", confidence=0.8,
        evidence={"metadata": pillow, "file": path, "url": url},
    )
    return findings


async def analyze_exiftool(path: str, url: str | None) -> list[ImageFinding]:
    et = await _exiftool_metadata(path)
    findings: list[ImageFinding] = []
    for key in ("DateTimeOriginal", "CreateDate", "GPSLatitude", "GPSLongitude", "Make", "Model", "Software"):
        if et.get(key):
            _add_meta_finding(
                findings, field=f"exiftool_{key.lower()}", value=str(et[key]), tool="exiftool",
                strategy="exiftool_field", confidence=0.88,
                evidence={"exiftool": et, "file": path, "url": url},
            )
    _add_meta_finding(
        findings, field="exiftool_metadata", value=path, tool="exiftool",
        strategy="exiftool_bundle", confidence=0.86,
        evidence={"exif": et, "file": path, "url": url},
    )
    return findings


async def analyze_hachoir(path: str, url: str | None) -> list[ImageFinding]:
    meta = await run_in_ml_thread(_hachoir_metadata, path)
    return [ImageFinding(
        category="metadata",
        field="hachoir_metadata",
        value=path,
        source_tool="hachoir",
        extraction_strategy="hachoir_extract",
        confidence=0.78,
        evidence={"metadata": meta, "file": path, "url": url},
    )]


async def analyze_metadata(path: str, url: str | None) -> list[ImageFinding]:
    results = await asyncio.gather(
        analyze_pillow(path, url),
        analyze_exiftool(path, url),
        analyze_hachoir(path, url),
        return_exceptions=True,
    )
    findings: list[ImageFinding] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        findings.extend(result)
    return findings
