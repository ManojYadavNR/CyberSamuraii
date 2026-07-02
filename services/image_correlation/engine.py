"""Cross-platform image correlation using embeddings, hashes, and reverse matches."""

from __future__ import annotations

from uuid import uuid4

from schemas.fusion import FusionOutput
from schemas.image_intelligence import ImageIntelligenceOutput
from schemas.reverse_image import DetectedFace, IdentityCandidate, ImageCorrelationOutput, ReverseImageDiscoveryOutput
from services.face_crops import crop_preview_url, seed_preview_url
from services.image_intelligence.path_utils import is_local_path, is_public_url


class ImageCorrelationEngine:
    """Merge image signals into identity candidates for investigator UI."""

    def correlate(
        self,
        *,
        seed_image: str,
        fusion: FusionOutput | None,
        image_intel: ImageIntelligenceOutput | None,
        reverse_discovery: ReverseImageDiscoveryOutput | None,
    ) -> ImageCorrelationOutput:
        hash_sigs = dict(image_intel.perceptual_hashes) if image_intel else {}
        sim_sig = image_intel.similarity_signature if image_intel else None
        content_type = image_intel.content_type if image_intel else ""
        ocr_text = image_intel.ocr_text if image_intel else ""

        face_matches: list[dict] = []
        detected_faces: list[DetectedFace] = []
        seen_person_idx: set[int] = set()
        if image_intel:
            ranked = sorted(
                [f for f in image_intel.findings if f.category == "face"],
                key=lambda f: float(f.confidence or 0),
                reverse=True,
            )
            for finding in ranked:
                if finding.field not in ("face_detection", "face_embedding"):
                    continue
                evidence = finding.evidence or {}
                person_idx = int(evidence.get("face_index", len(detected_faces)))
                if person_idx in seen_person_idx:
                    continue
                crop_path = evidence.get("crop_path")
                seen_person_idx.add(person_idx)
                bbox = evidence.get("bbox") or []
                detected_faces.append(DetectedFace(
                    face_id=f"face_{person_idx}",
                    person_index=person_idx,
                    source_tool=finding.source_tool,
                    confidence=float(finding.confidence or 0),
                    quality_score=float(evidence.get("face_quality_score") or 0) or None,
                    bbox=[float(v) for v in bbox] if bbox else [],
                    crop_path=str(crop_path) if crop_path else None,
                    crop_preview_url=crop_preview_url(str(crop_path)) if crop_path else None,
                    embedding_signature=evidence.get("embedding_signature"),
                ))
                face_matches.append({
                    "field": finding.field,
                    "value": finding.value,
                    "source_tool": finding.source_tool,
                    "confidence": finding.confidence,
                    "quality": evidence.get("face_quality_score"),
                    "embedding": evidence.get("embedding_signature"),
                    "crop_path": crop_path,
                    "crop_preview_url": crop_preview_url(str(crop_path)) if crop_path else None,
                    "person_index": person_idx,
                    "bbox": bbox,
                })
            detected_faces.sort(key=lambda f: f.person_index)

        reverse_matches = list(reverse_discovery.matches if reverse_discovery else [])
        chains = reverse_discovery.evidence_chains if reverse_discovery else []

        candidates: list[IdentityCandidate] = []
        accounts: set[str] = set()

        if fusion:
            for ent in fusion.deduplicated_entities or []:
                if ent.type == "account":
                    accounts.add(ent.canonical_value or ent.value)

        is_logo = content_type in ("logo", "company logo", "product packaging", "event banner")
        no_faces = (image_intel.face_count if image_intel else 0) == 0

        if face_matches and not is_logo:
            best = max(face_matches, key=lambda f: f.get("confidence", 0))
            candidates.insert(0, IdentityCandidate(
                candidate_id=str(uuid4()),
                label="Face detected in uploaded photo",
                confidence=float(best.get("confidence", 0.7)),
                reasons=[
                    f"Faces detected: {image_intel.face_count if image_intel else 0}",
                    f"Source: {best.get('source_tool')}",
                    "Searching public platforms for visually similar profile photos",
                ],
                face_match_score=float(best.get("quality") or best.get("confidence", 0)),
                evidence_paths=[["uploaded_photo", "face_analysis", str(best.get("embedding", ""))]],
            ))

        if is_logo and not face_matches:
            label = ocr_text[:80] if ocr_text else "Logo / graphic image (not a person photo)"
            candidates.append(IdentityCandidate(
                candidate_id=str(uuid4()),
                label=label,
                confidence=0.85 if ocr_text else 0.45,
                reasons=[
                    f"CLIP classified as: {content_type or 'graphic'}",
                    "No verified face detected — person identity linking disabled",
                    f"OCR text: {ocr_text[:120]}" if ocr_text else "Run OCR to extract visible text",
                ],
                evidence_paths=[[seed_image, "content_analysis", content_type or "graphic"]],
            ))

        elif no_faces and ocr_text and not face_matches:
            label = ocr_text[:80]
            candidates.append(IdentityCandidate(
                candidate_id=str(uuid4()),
                label=label,
                confidence=0.85,
                reasons=[
                    f"Content type: {content_type or 'text/graphic'}",
                    f"OCR text: {ocr_text[:120]}",
                ],
                evidence_paths=[[seed_image, "content_analysis", content_type or "graphic"]],
            ))

        for match in reverse_matches[:15]:
            if not match.provenance.get("face_verified") and not match.profile_urls:
                continue
            if not match.provenance.get("hash_verified") and not match.profile_urls:
                continue
            hash_score = float(match.provenance.get("hash_similarity") or 0)
            label = match.title or match.platform or match.match_url
            reasons = [
                f"Hash-verified match via {match.source}" if match.provenance.get("hash_verified") else f"Profile URL via {match.source}",
                f"Match type: {match.match_type}",
                f"Visual similarity: {hash_score:.0%}" if hash_score else f"Confidence: {match.confidence:.0%}",
            ]
            if match.profile_urls:
                reasons.append(f"Linked profiles: {len(match.profile_urls)}")
            clean_path = [p for p in match.evidence_path if p and is_public_url(p) and not is_local_path(p)]
            candidates.append(IdentityCandidate(
                candidate_id=str(uuid4()),
                label=label,
                confidence=match.confidence,
                reasons=reasons,
                linked_accounts=match.profile_urls[:5],
                hash_similarity_score=hash_score if hash_score >= 0.72 else None,
                image_similarity_score=float(match.provenance.get("face_similarity") or 0) or None,
                evidence_paths=[clean_path or [match.source, match.match_url]],
            ))

        if accounts:
            candidates.append(IdentityCandidate(
                candidate_id=str(uuid4()),
                label="Linked account cluster",
                confidence=0.6,
                reasons=[f"{len(accounts)} accounts correlated with image investigation"],
                linked_accounts=sorted(accounts)[:10],
            ))

        verified_reverse = [m for m in reverse_matches if m.provenance.get("hash_verified")]
        breakdown = {
            "face_analysis": max((f.get("confidence", 0) for f in face_matches), default=0.0),
            "reverse_image": max((m.confidence for m in verified_reverse), default=0.0),
            "perceptual_hash": 0.9 if hash_sigs else 0.0,
            "account_linkage": min(1.0, len(accounts) * 0.15),
        }

        return ImageCorrelationOutput(
            seed_image=seed_image,
            seed_preview_url=seed_preview_url(seed_image),
            detected_faces=detected_faces,
            identity_candidates=candidates[:15],
            face_matches=face_matches,
            reverse_matches=reverse_matches,
            hash_signatures=hash_sigs,
            similarity_signature=sim_sig,
            confidence_breakdown=breakdown,
            evidence_chains=chains,
        )


image_correlation_engine = ImageCorrelationEngine()
