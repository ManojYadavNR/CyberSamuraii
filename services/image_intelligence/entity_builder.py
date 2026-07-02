"""Convert image findings into fusion entities with evidence and provenance."""

from __future__ import annotations

from schemas.fusion import Entity
from schemas.image_intelligence import ImageFinding
from services.fusion_engine import _make_entity


def _entity_type_for_finding(finding: ImageFinding) -> str:
    if finding.field in ("emails",) or finding.category == "ocr" and finding.field == "emails":
        return "email"
    if finding.field in ("phones",):
        return "phone"
    if finding.field in ("usernames",):
        return "account"
    if finding.field in ("urls",):
        return "domain"
    if finding.category in ("face", "fingerprint") or finding.field in (
        "face_detection",
        "face_embedding",
        "face_count",
        "image_metadata",
        "perceptual_hash_ahash",
        "perceptual_hash_phash",
        "perceptual_hash_dhash",
        "perceptual_hash_whash",
        "opencv_orb_signature",
    ):
        return "image"
    if finding.field == "gps_coordinates":
        return "document"
    return "document"


def _entity_value(finding: ImageFinding, image_source: str) -> str:
    if finding.category == "face" and finding.evidence.get("crop_path"):
        return str(finding.evidence["crop_path"])
    if finding.field == "usernames":
        return f"image_ocr:{finding.value.lower()}"
    if finding.field == "urls":
        val = finding.value
        return val if val.startswith("http") else f"https://{val}"
    if finding.field == "face_count":
        return image_source
    if finding.category == "fingerprint":
        return image_source
    if finding.field == "image_metadata":
        return image_source
    return finding.value[:500] if len(finding.value) > 500 else finding.value


def build_entities(
    findings: list[ImageFinding],
    *,
    image_source: str,
    image_path: str | None,
    image_url: str | None,
    perceptual_hashes: dict[str, str] | None = None,
    similarity_signature: str | None = None,
) -> list[Entity]:
    entities: list[Entity] = []
    seen: set[tuple[str, str]] = set()

    base_meta = {
        "intel_engine": "image_intelligence",
        "image_source": image_source,
        "file": image_path,
        "url": image_url,
    }
    if perceptual_hashes:
        base_meta["perceptual_hashes"] = perceptual_hashes
    if similarity_signature:
        base_meta["similarity_signature"] = similarity_signature

    for finding in findings:
        etype = _entity_type_for_finding(finding)
        value = _entity_value(finding, image_source)
        if not value:
            continue
        dedupe_key = (etype, value.lower())
        if dedupe_key in seen and finding.category != "face":
            continue
        seen.add(dedupe_key)

        meta = {
            **base_meta,
            "category": finding.category,
            "field": finding.field,
            "extraction_strategy": finding.extraction_strategy,
            "finding_confidence": finding.confidence,
            "platform": finding.source_tool,
            **finding.evidence,
        }
        if finding.field in ("emails", "phones", "usernames"):
            meta["image_attributed"] = True
            meta["pivotable"] = True
        if finding.category == "face" and finding.evidence.get("crop_path"):
            meta["face_crop"] = True
            meta["face_quality_score"] = finding.evidence.get("face_quality_score")
            meta["embedding_signature"] = finding.evidence.get("embedding_signature")

        entities.append(
            _make_entity(
                etype,
                value,
                finding.source_tool,
                meta,
                raw_payload=finding.evidence,
                raw_source_ref=image_url or image_path or image_source,
            )
        )

    # Seed image entity with bundled intelligence
    if image_source:
        bundle_meta = {
            **base_meta,
            "platform": "image_intelligence_engine",
            "category": "bundle",
            "finding_count": len(findings),
        }
        entities.append(
            _make_entity(
                "image",
                image_source,
                "image_intelligence_engine",
                bundle_meta,
                raw_source_ref=image_url or image_path or image_source,
            )
        )

    return entities
