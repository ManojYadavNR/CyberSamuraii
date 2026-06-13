"""
Identity Correlation Engine — multi-modal account linkage from fusion entities.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from schemas.correlation import AccountCluster, CorrelationEvidence, CorrelationOutput
from schemas.fusion import Entity, FusionOutput
from services.correlation.account_parser import AccountProfile, profiles_from_entities
from services.correlation.behavior_similarity import behavior_similarity
from services.correlation.image_similarity import (
    image_similarity,
    imagehash_available,
    insightface_available,
)
from services.correlation.location_similarity import location_similarity
from services.correlation.text_similarity import sentence_transformers_available, text_similarity
from services.correlation.username_similarity import username_similarity

# Explicit multi-modal weighting model (fixed denominator — NOT renormalized).
MULTIMODAL_WEIGHTS: dict[str, float] = {
    "username_similarity": 0.30,
    "image_similarity": 0.25,
    "behavior_similarity": 0.20,
    "text_similarity": 0.20,
    "location_similarity": 0.05,
}

# Backward-compatible alias for evidence summaries.
SIGNAL_WEIGHTS: dict[str, float] = {
    "username": MULTIMODAL_WEIGHTS["username_similarity"],
    "image": MULTIMODAL_WEIGHTS["image_similarity"],
    "behavior": MULTIMODAL_WEIGHTS["behavior_similarity"],
    "text": MULTIMODAL_WEIGHTS["text_similarity"],
    "location": MULTIMODAL_WEIGHTS["location_similarity"],
    "email": 0.0,
}

LINK_THRESHOLD = 0.52
CONFLICT_GAP = 0.45
EMAIL_MATCH_BOOST = 0.15
USERNAME_LINK_MIN = 0.85
IMAGE_LINK_MIN = 0.80


def _should_link_pair(signal_scores: dict[str, float], confidence: float, has_email_match: bool) -> bool:
    """Link accounts when multimodal score or any dominant signal exceeds threshold."""
    if confidence >= LINK_THRESHOLD:
        return True
    if has_email_match:
        return True
    if signal_scores.get("username", 0.0) >= USERNAME_LINK_MIN:
        return True
    if signal_scores.get("image", 0.0) >= IMAGE_LINK_MIN:
        return True
    if signal_scores.get("text", 0.0) >= 0.90:
        return True
    return False


def calculate_multimodal_score(signal_scores: dict[str, float]) -> float:
    """
    Explicit weighted scoring formula:

    final_score =
        username_similarity  * 0.30 +
        image_similarity     * 0.25 +
        behavior_similarity  * 0.20 +
        text_similarity      * 0.20 +
        location_similarity  * 0.05

    Missing signals contribute 0. Weights are never renormalized.
    """
    return round(
        MULTIMODAL_WEIGHTS["username_similarity"] * signal_scores.get("username", 0.0)
        + MULTIMODAL_WEIGHTS["image_similarity"] * signal_scores.get("image", 0.0)
        + MULTIMODAL_WEIGHTS["behavior_similarity"] * signal_scores.get("behavior", 0.0)
        + MULTIMODAL_WEIGHTS["text_similarity"] * signal_scores.get("text", 0.0)
        + MULTIMODAL_WEIGHTS["location_similarity"] * signal_scores.get("location", 0.0),
        4,
    )


def _strength_label(score: float) -> str:
    if score >= 0.85:
        return "very high"
    if score >= 0.70:
        return "high"
    if score >= 0.50:
        return "moderate"
    if score >= 0.30:
        return "low"
    return "very low"


def _format_explainability(evidence: CorrelationEvidence, a: AccountProfile, b: AccountProfile) -> str:
    """Produce human-readable reasoning from signal evidence."""
    score = evidence.score
    strength = _strength_label(score)
    detail = evidence.detail or ""

    if evidence.type == "username":
        lev_match = re.search(r"levenshtein=([\d.]+)", detail)
        lev_val = lev_match.group(1) if lev_match else f"{score:.2f}"
        return (
            f"Username similarity {strength} (Levenshtein similarity: {lev_val}) "
            f"between {a.platform}/{a.handle} and {b.platform}/{b.handle}"
        )

    if evidence.type == "image":
        cosine_match = re.search(r"cosine=([\d.]+)", detail)
        method_match = re.search(r"method=([\w+]+)", detail)
        cosine_val = cosine_match.group(1) if cosine_match else f"{score:.2f}"
        method = method_match.group(1) if method_match else "perceptual_hash"
        return f"Face/image embeddings match via {method} (cosine similarity: {cosine_val})"

    if evidence.type == "behavior":
        if "night" in detail.lower() or "22:00" in detail or "02:00" in detail:
            return f"Behavior pattern matches night activity window (22:00–02:00) — score {score:.2f}"
        return f"Behavior pattern overlap {strength} (posting style, emoji usage, activity windows) — {detail}"

    if evidence.type == "text":
        if "cosine" in detail.lower():
            cosine_match = re.search(r"cosine=([\d.]+)", detail)
            cosine_val = cosine_match.group(1) if cosine_match else f"{score:.2f}"
            return f"Text similarity indicates shared slang and writing style (cosine similarity: {cosine_val})"
        return f"Text similarity {strength} — shared bio/language patterns ({detail})"

    if evidence.type == "location":
        return f"Location proximity {strength} ({a.location} ↔ {b.location}) — {detail}"

    if evidence.type == "email":
        return f"Shared email address corroborates identity link ({detail})"

    return f"{evidence.type} signal {strength} ({score:.2f}): {detail}"


def _resolve_conflicts(
    evidences: list[CorrelationEvidence],
    base_confidence: float,
) -> tuple[float, bool, list[str]]:
    """
    Conflict resolution: keep the match, reduce confidence proportionally, explain why.
    """
    scores = [e.score for e in evidences if e.score > 0]
    if len(scores) < 2:
        return base_confidence, False, []

    high = max(scores)
    low = min(scores)
    spread = high - low
    conflicting = spread >= CONFLICT_GAP and high >= 0.7 and low <= 0.35
    if not conflicting:
        return base_confidence, False, []

    reduction = min(0.45, spread * 0.55)
    adjusted = round(base_confidence * (1.0 - reduction), 4)

    strong = [e for e in evidences if e.score >= 0.7]
    weak = [e for e in evidences if e.score <= 0.35]
    for e in evidences:
        if e.score <= 0.35 or e.score >= 0.7:
            e.conflicting = True

    explanations: list[str] = []
    for s in strong:
        explanations.append(
            f"Conflict: strong {s.type} match ({s.score:.2f}) conflicts with weak signals — "
            f"confidence reduced by {reduction * 100:.0f}% but match retained"
        )
    for w in weak:
        explanations.append(
            f"Conflict: weak {w.type} match ({w.score:.2f}) offset by stronger corroborating signals"
        )

    return adjusted, True, explanations


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


class IdentityCorrelationEngine:
    """Determine whether multiple accounts belong to the same real-world person."""

    async def correlate(
        self,
        fusion: FusionOutput | None,
        seed_query: str = "",
        *,
        entities: list[Entity] | None = None,
    ) -> CorrelationOutput:
        entity_list = entities or (fusion.deduplicated_entities if fusion else [])
        profiles = profiles_from_entities(entity_list, seed_query)

        warnings: list[str] = []
        if len(profiles) < 2:
            return CorrelationOutput(
                total_accounts_analyzed=len(profiles),
                total_clusters=len(profiles),
                clusters=self._singleton_clusters(profiles),
                signal_availability=self._signal_availability(),
                warnings=["Need at least 2 account profiles for pairwise correlation"]
                if len(profiles) == 1
                else ["No correlatable account profiles in fusion output"],
            )

        pair_results: dict[tuple[int, int], dict[str, Any]] = {}
        uf = _UnionFind(len(profiles))

        for i in range(len(profiles)):
            for j in range(i + 1, len(profiles)):
                result = await self._compare_pair(profiles[i], profiles[j], seed_query)
                pair_results[(i, j)] = result
                if result["should_link"]:
                    uf.union(i, j)

        clusters_map: dict[int, list[int]] = {}
        for idx in range(len(profiles)):
            root = uf.find(idx)
            clusters_map.setdefault(root, []).append(idx)

        clusters: list[AccountCluster] = []
        for members in clusters_map.values():
            cluster = self._build_cluster(profiles, members, pair_results, seed_query)
            clusters.append(cluster)

        clusters.sort(key=lambda c: (-c.confidence_score, -len(c.linked_accounts)))

        return CorrelationOutput(
            clusters=clusters,
            total_accounts_analyzed=len(profiles),
            total_clusters=len(clusters),
            signal_availability=self._signal_availability(),
            warnings=warnings,
        )

    def _signal_availability(self) -> dict[str, bool]:
        from services.correlation.image_similarity import _check_opencv

        return {
            "username_rapidfuzz": True,
            "text_sentence_transformers": sentence_transformers_available(),
            "image_perceptual_hash": imagehash_available(),
            "image_opencv_orb": _check_opencv(),
            "image_insightface": insightface_available(),
            "behavior_heuristics": True,
            "location_fuzzy": True,
        }

    def _singleton_clusters(self, profiles: list[AccountProfile]) -> list[AccountCluster]:
        clusters: list[AccountCluster] = []
        for p in profiles:
            ref = self._account_ref(p)
            clusters.append(
                AccountCluster(
                    account_cluster_id=self._cluster_id([p.entity_id]),
                    linked_accounts=[self._account_dict(p)],
                    linked_account_refs=[ref],
                    confidence_score=round(p.fusion_score * 100, 2),
                    evidence=[],
                    explainability=[f"Singleton account on {p.platform} — no linkage peers"],
                )
            )
        return clusters

    async def _compare_pair(
        self,
        a: AccountProfile,
        b: AccountProfile,
        seed_query: str,
    ) -> dict[str, Any]:
        evidences: list[CorrelationEvidence] = []
        signal_scores: dict[str, float] = {
            "username": 0.0,
            "image": 0.0,
            "behavior": 0.0,
            "text": 0.0,
            "location": 0.0,
        }

        u_score, u_detail = username_similarity(a.handle, b.handle)
        if a.handle and b.handle:
            signal_scores["username"] = u_score
            evidences.append(
                CorrelationEvidence(
                    type="username",
                    score=u_score,
                    weight=SIGNAL_WEIGHTS["username"],
                    detail=u_detail,
                )
            )

        seed = seed_query.lower().strip()
        if seed and "@" not in seed:
            seed_handle = seed
            if a.handle == seed_handle or b.handle == seed_handle:
                signal_scores["username"] = max(signal_scores["username"], 1.0)
                evidences.append(
                    CorrelationEvidence(
                        type="username",
                        score=1.0,
                        weight=SIGNAL_WEIGHTS["username"],
                        detail=f"seed query handle '{seed_handle}' matches profile",
                    )
                )

        if a.email and b.email:
            email_score = 1.0 if a.email == b.email else 0.0
            evidences.append(
                CorrelationEvidence(
                    type="email",
                    score=email_score,
                    weight=0.0,
                    detail=f"email_a={a.email}, email_b={b.email}",
                )
            )

        if a.bio and b.bio:
            t_score, t_detail = text_similarity(a.bio, b.bio)
            signal_scores["text"] = t_score
            evidences.append(
                CorrelationEvidence(type="text", score=t_score, weight=SIGNAL_WEIGHTS["text"], detail=t_detail)
            )

        img_a = a.image_path or a.avatar_source
        img_b = b.image_path or b.avatar_source
        if img_a and img_b:
            i_score, i_detail = await image_similarity(img_a, img_b)
            signal_scores["image"] = i_score
            evidences.append(
                CorrelationEvidence(type="image", score=i_score, weight=SIGNAL_WEIGHTS["image"], detail=i_detail)
            )
        elif not img_a or not img_b:
            evidences.append(
                CorrelationEvidence(
                    type="image",
                    score=0.0,
                    weight=SIGNAL_WEIGHTS["image"],
                    detail="missing image data on one or both profiles",
                )
            )

        b_score, b_detail = behavior_similarity(
            a.text_corpus, b.text_corpus, a.posting_times, b.posting_times
        )
        if b_score > 0:
            signal_scores["behavior"] = b_score
            evidences.append(
                CorrelationEvidence(
                    type="behavior", score=b_score, weight=SIGNAL_WEIGHTS["behavior"], detail=b_detail
                )
            )

        if a.location and b.location:
            l_score, l_detail = location_similarity(a.location, b.location)
            signal_scores["location"] = l_score
            evidences.append(
                CorrelationEvidence(
                    type="location", score=l_score, weight=SIGNAL_WEIGHTS["location"], detail=l_detail
                )
            )

        confidence = calculate_multimodal_score(signal_scores)

        has_email_match = bool(a.email and b.email and a.email == b.email)
        if has_email_match:
            confidence = min(confidence + EMAIL_MATCH_BOOST, 1.0)

        confidence, conflicting, conflict_explanations = _resolve_conflicts(evidences, confidence)
        should_link = _should_link_pair(signal_scores, confidence, has_email_match)

        return {
            "confidence": confidence,
            "should_link": should_link,
            "evidence": evidences,
            "conflicting": conflicting,
            "conflict_explanations": conflict_explanations,
            "profiles": (a, b),
            "signal_scores": signal_scores,
        }

    def _build_cluster(
        self,
        profiles: list[AccountProfile],
        member_indices: list[int],
        pair_results: dict[tuple[int, int], dict[str, Any]],
        seed_query: str,
    ) -> AccountCluster:
        members = [profiles[i] for i in member_indices]
        entity_ids = [m.entity_id for m in members]

        if len(members) == 1:
            p = members[0]
            return AccountCluster(
                account_cluster_id=self._cluster_id(entity_ids),
                linked_accounts=[self._account_dict(p)],
                linked_account_refs=[self._account_ref(p)],
                confidence_score=round(members[0].fusion_score * 100, 2),
                evidence=[],
                explainability=[f"Standalone profile: {p.platform}/{p.handle}"],
            )

        pair_confidences: list[float] = []
        aggregated: dict[str, list[float]] = {}
        explainability: list[str] = []
        conflicting_pairs = 0

        for i in range(len(member_indices)):
            for j in range(i + 1, len(member_indices)):
                key = (min(member_indices[i], member_indices[j]), max(member_indices[i], member_indices[j]))
                result = pair_results.get(key)
                if not result:
                    continue
                pair_confidences.append(result["confidence"])
                if result["conflicting"]:
                    conflicting_pairs += 1
                explainability.extend(result.get("conflict_explanations", []))
                for ev in result["evidence"]:
                    if ev.type in SIGNAL_WEIGHTS:
                        aggregated.setdefault(ev.type, []).append(ev.score)
                    if ev.score >= 0.35:
                        a, b = result["profiles"]
                        explainability.append(_format_explainability(ev, a, b))

        cluster_signal_avg: dict[str, float] = {
            signal: sum(scores) / len(scores) for signal, scores in aggregated.items() if scores
        }
        cluster_confidence = calculate_multimodal_score(cluster_signal_avg) * 100

        if pair_confidences and not cluster_signal_avg:
            cluster_confidence = (sum(pair_confidences) / len(pair_confidences)) * 100

        if conflicting_pairs:
            reduction = min(0.25, 0.08 * conflicting_pairs)
            cluster_confidence *= 1.0 - reduction
            explainability.append(
                f"Cluster-level conflict resolution: {conflicting_pairs} conflicting pair(s) "
                f"reduced confidence by {reduction * 100:.0f}% — accounts retained in cluster"
            )

        cluster_confidence = min(cluster_confidence, 100.0)

        evidence_summary: list[CorrelationEvidence] = []
        for signal, scores in aggregated.items():
            avg = sum(scores) / len(scores)
            evidence_summary.append(
                CorrelationEvidence(
                    type=signal,
                    score=round(avg, 4),
                    weight=SIGNAL_WEIGHTS.get(signal, 0.0),
                    detail=f"averaged over {len(scores)} pair(s)",
                    conflicting=any(s <= 0.35 for s in scores) and any(s >= 0.7 for s in scores),
                )
            )

        if seed_query:
            explainability.insert(0, f"Correlation anchored to seed query: '{seed_query}'")

        unique_explainability = list(dict.fromkeys(explainability))

        return AccountCluster(
            account_cluster_id=self._cluster_id(entity_ids),
            linked_accounts=[self._account_dict(m) for m in members],
            linked_account_refs=[self._account_ref(m) for m in members],
            confidence_score=round(cluster_confidence, 2),
            evidence=sorted(evidence_summary, key=lambda e: -e.score),
            explainability=unique_explainability[:15],
        )

    def _cluster_id(self, entity_ids: list[str]) -> str:
        digest = hashlib.sha256("|".join(sorted(entity_ids)).encode()).hexdigest()[:12]
        return f"cluster_{digest}"

    def _account_ref(self, profile: AccountProfile) -> str:
        platform = profile.platform.split(".")[0] if profile.platform else "unknown"
        return f"{platform}:{profile.handle}"

    def _account_dict(self, profile: AccountProfile) -> dict[str, Any]:
        return {
            "entity_id": profile.entity_id,
            "platform": profile.platform,
            "handle": profile.handle,
            "url": profile.url,
            "email": profile.email,
            "verified": profile.verified,
            "fusion_score": profile.fusion_score,
            "sources": profile.sources,
        }


correlation_engine = IdentityCorrelationEngine()
