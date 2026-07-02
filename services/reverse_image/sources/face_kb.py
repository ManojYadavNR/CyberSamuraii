"""Reverse image source — match seed against face knowledge base."""

from __future__ import annotations

from uuid import uuid4

from schemas.reverse_image import ReverseImageMatch
from services.json_utils import embedding_nonempty, normalize_embedding
from services.reverse_image.matcher import classify_match_type
from services.reverse_image.registry import register_source


@register_source
class FaceKnowledgeBaseSource:
    name = "face_kb"

    async def search(
        self,
        image_path: str,
        image_url: str | None,
        *,
        seed_query: str,
        context: dict | None = None,
    ) -> list[ReverseImageMatch]:
        ctx = context or {}
        query_emb = normalize_embedding(ctx.get("primary_face_embedding"))
        if query_emb is None:
            try:
                from services.image_intelligence.analyzers.face import analyze_insightface

                findings = await analyze_insightface(image_path, image_url)
                for f in findings:
                    if f.field == "face_embedding" and embedding_nonempty(f.evidence.get("embedding_vector")):
                        query_emb = normalize_embedding(f.evidence["embedding_vector"])
                        break
            except Exception:
                return []

        if query_emb is None:
            return []

        from services.face_intelligence.kb import face_kb

        hits = face_kb.search(query_emb, limit=8)
        matches: list[ReverseImageMatch] = []
        for hit in hits:
            ref = hit.get("image_url") or hit.get("image_path") or ""
            if not ref:
                continue
            sim = float(hit.get("similarity") or 0)
            platform = str(hit.get("platform") or hit.get("source") or "face_kb")
            match_type = classify_match_type(
                url_a=image_url or image_path,
                url_b=ref,
                face_similarity=sim,
            )
            profile_urls = [ref] if ref.startswith("http") else []
            matches.append(ReverseImageMatch(
                match_id=str(uuid4()),
                source=self.name,
                match_type=match_type,
                match_url=ref,
                page_url=ref,
                title=f"Face KB match ({platform})",
                platform=platform,
                confidence=round(min(sim, 0.98), 4),
                profile_urls=profile_urls,
                evidence_path=[image_path, self.name, ref],
                provenance={
                    "face_similarity": sim,
                    "record_id": hit.get("record_id"),
                    "entity_id": hit.get("entity_id"),
                    "face_verified": True,
                },
            ))
        return matches
