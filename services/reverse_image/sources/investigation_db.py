"""Match seed image against known investigation image fingerprints."""

from __future__ import annotations

import os
from uuid import uuid4

from schemas.reverse_image import ReverseImageMatch
from services.reverse_image.matcher import classify_match_type
from services.reverse_image.registry import register_source


@register_source
class InvestigationHashSource:
    name = "investigation_hashes"

    async def search(
        self,
        image_path: str,
        image_url: str | None,
        *,
        seed_query: str,
        context: dict | None = None,
    ) -> list[ReverseImageMatch]:
        try:
            import imagehash
            from PIL import Image
        except ImportError:
            return []

        try:
            seed = Image.open(image_path)
            seed_ahash = imagehash.average_hash(seed)
            seed_phash = imagehash.phash(seed)
        except Exception:
            return []

        candidates: list[tuple[str, str, float]] = []

        try:
            from services.persistence.postgres import load_recent_image_entities

            for ent in load_recent_image_entities(limit=200):
                ref = str(ent.get("value") or ent.get("url") or "")
                meta = ent.get("metadata") or {}
                hashes = meta.get("perceptual_hashes") or {}
                if hashes.get("ahash"):
                    try:
                        other = imagehash.hex_to_hash(str(hashes["ahash"]))
                        sim = max(0.0, 1.0 - (seed_ahash - other) / 64.0)
                        if sim >= 0.7:
                            candidates.append((ref, str(ent.get("entity_id") or ""), sim))
                    except Exception:
                        pass
                elif ref and os.path.isfile(ref):
                    try:
                        other_img = Image.open(ref)
                        sim = max(0.0, 1.0 - (seed_ahash - imagehash.average_hash(other_img)) / 64.0)
                        if sim >= 0.7:
                            candidates.append((ref, "file_match", sim))
                    except Exception:
                        pass
        except Exception:
            pass

        matches: list[ReverseImageMatch] = []
        for ref, ent_id, sim in candidates[:10]:
            match_type = classify_match_type(
                url_a=image_url or image_path,
                url_b=ref,
                hash_similarity=sim,
            )
            matches.append(ReverseImageMatch(
                match_id=str(uuid4()),
                source=self.name,
                match_type=match_type,
                match_url=ref,
                page_url=ref,
                title="Investigation database match",
                confidence=round(min(sim, 0.98), 4),
                evidence_path=[image_path, self.name, ref],
                provenance={"entity_id": ent_id, "hash_similarity": sim},
            ))
        return matches
