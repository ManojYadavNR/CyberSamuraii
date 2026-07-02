"""
Identity Correlation Engine — multi-modal account linkage from fusion entities.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from schemas.correlation import AccountCluster, CorrelationEvidence, CorrelationOutput
from schemas.fusion import Entity, FusionOutput
from services.correlation.account_parser import AccountProfile, profiles_from_entities
from services.correlation.behavior_similarity import behavior_similarity
from services.correlation.image_similarity import (
    avatar_hash_similarity,
    image_similarity,
    imagehash_available,
    insightface_available,
)
from services.correlation.location_similarity import location_similarity
from services.correlation.negative_signals import negative_signal_check
from services.correlation.text_similarity import sentence_transformers_available, text_similarity
from services.correlation.username_similarity import username_similarity

logger = logging.getLogger(__name__)

MULTIMODAL_WEIGHTS: dict[str, float] = {
    "username": 0.30,
    "image": 0.25,
    "behavior": 0.20,
    "text": 0.20,
    "location": 0.05,
}

SIGNAL_WEIGHTS: dict[str, float] = dict(MULTIMODAL_WEIGHTS)

LINK_THRESHOLD = 0.52
CONFLICT_GAP = 0.45
EMAIL_MATCH_BOOST = 0.15
USERNAME_LINK_MIN = 0.85
IMAGE_LINK_MIN = 0.80
SINGLE_LINK_USERNAME_MIN = 0.75
AVATAR_HASH_USERNAME_SCALE = 0.72
NEGATIVE_BLOCK_PENALTY = 0.85

SIGNAL_LABELS = {
    "username": "username_similarity",
    "image": "image_similarity",
    "behavior": "behavior_similarity",
    "text": "text_similarity",
    "location": "location_similarity",
}


def calculate_multimodal_score(
    signal_scores: dict[str, float],
    active_signals: dict[str, bool] | None = None,
) -> float:
    """Weighted score with renormalization when signals are unavailable."""
    if not active_signals:
        return round(
            sum(MULTIMODAL_WEIGHTS[k] * signal_scores.get(k, 0.0) for k in MULTIMODAL_WEIGHTS),
            4,
        )

    available = [k for k in MULTIMODAL_WEIGHTS if active_signals.get(k)]
    if not available:
        return 0.0

    total_weight = sum(MULTIMODAL_WEIGHTS[k] for k in available)
    if total_weight <= 0:
        return 0.0

    weighted = sum(
        (MULTIMODAL_WEIGHTS[k] / total_weight) * signal_scores.get(k, 0.0) for k in available
    )
    return round(weighted, 4)


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
        if "perceptual_hash_avatar" in detail:
            return f"Avatar perceptual hash match ({strength}) — {detail}"
        cosine_match = re.search(r"cosine=([\d.]+)", detail)
        method_match = re.search(r"method=([\w+]+)", detail)
        cosine_val = cosine_match.group(1) if cosine_match else f"{score:.2f}"
        method = method_match.group(1) if method_match else "perceptual_hash"
        return f"Face/image embeddings match via {method} (cosine similarity: {cosine_val})"

    if evidence.type == "behavior":
        if "activity_window" in detail or "night" in detail.lower():
            return f"Behavior pattern matches shared activity window — score {score:.2f} ({detail})"
        if "topic(" in detail:
            return f"Behavior topic overlap {strength} — shared interests/posts ({detail})"
        return f"Behavior pattern overlap {strength} (posts, hashtags, activity windows) — {detail}"

    if evidence.type == "text":
        if "cosine" in detail.lower():
            cosine_match = re.search(r"cosine=([\d.]+)", detail)
            cosine_val = cosine_match.group(1) if cosine_match else f"{score:.2f}"
            return f"Bio text similarity indicates shared profile language (cosine similarity: {cosine_val})"
        return f"Bio text similarity {strength} — shared bio patterns ({detail})"

    if evidence.type == "location":
        return f"Location proximity {strength} ({a.location} ↔ {b.location}) — {detail}"

    if evidence.type == "email":
        return f"Shared email address corroborates identity link ({detail})"

    return f"{evidence.type} signal {strength} ({score:.2f}): {detail}"


def _resolve_conflicts(
    evidences: list[CorrelationEvidence],
    base_confidence: float,
) -> tuple[float, bool, list[str]]:
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

    for e in evidences:
        if e.score <= 0.35 or e.score >= 0.7:
            e.conflicting = True

    explanations: list[str] = []
    strong = [e for e in evidences if e.score >= 0.7]
    weak = [e for e in evidences if e.score <= 0.35]
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


def _link_trigger(
    signal_scores: dict[str, float],
    confidence: float,
    has_email_match: bool,
) -> str:
    if has_email_match:
        return "email"
    if signal_scores.get("username", 0.0) >= USERNAME_LINK_MIN:
        return "username_override"
    if signal_scores.get("image", 0.0) >= IMAGE_LINK_MIN:
        return "image_override"
    if signal_scores.get("text", 0.0) >= 0.90:
        return "text_override"
    if confidence >= LINK_THRESHOLD:
        return "threshold"
    return ""


def _strong_link(
    signal_scores: dict[str, float],
    confidence: float,
    has_email_match: bool,
    blocked: bool,
) -> bool:
    """Union-find only merges on strong direct links — avoids weak transitive chains."""
    if blocked:
        return False
    trigger = _link_trigger(signal_scores, confidence, has_email_match)
    if trigger in ("email", "username_override", "image_override", "text_override"):
        return True
    if confidence >= LINK_THRESHOLD and signal_scores.get("username", 0.0) >= SINGLE_LINK_USERNAME_MIN:
        return True
    return False


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

    def __init__(self) -> None:
        self._last_link_metrics: list[dict[str, Any]] = []
        self._computed_signal_counts: dict[str, int] = {}

    async def correlate(
        self,
        fusion: FusionOutput | None,
        seed_query: str = "",
        *,
        entities: list[Entity] | None = None,
    ) -> CorrelationOutput:
        entity_list = entities or (fusion.deduplicated_entities if fusion else [])
        profiles = profiles_from_entities(entity_list, seed_query)

        self._last_link_metrics = []
        self._computed_signal_counts = {k: 0 for k in MULTIMODAL_WEIGHTS}

        warnings: list[str] = []
        if len(profiles) < 2:
            return CorrelationOutput(
                total_accounts_analyzed=len(profiles),
                total_clusters=len(profiles),
                clusters=self._singleton_clusters(profiles),
                signal_availability=self._signal_availability(profiles),
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
                if result["strong_link"]:
                    uf.union(i, j)
                    self._log_link_metric(profiles[i], profiles[j], result)

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
            correlation_engine_version="2.1.1",
            signal_availability=self._signal_availability(profiles),
            warnings=warnings,
        )

    def _log_link_metric(self, a: AccountProfile, b: AccountProfile, result: dict[str, Any]) -> None:
        metric = {
            "platform_a": a.platform,
            "handle_a": a.handle,
            "platform_b": b.platform,
            "handle_b": b.handle,
            "confidence": result["confidence"],
            "link_trigger": result.get("link_trigger", ""),
            "signal_scores": result.get("signal_scores", {}),
            "negative_penalty": result.get("negative_penalty", 0.0),
            "blocked": result.get("blocked", False),
        }
        self._last_link_metrics.append(metric)
        logger.info("correlation_link %s", metric)

    def _signal_availability(self, profiles: list[AccountProfile]) -> dict[str, bool]:
        from services.correlation.image_similarity import _check_opencv

        has_behavior = any(p.behavior_corpus or p.posting_times or p.hashtags for p in profiles)
        has_text = any(p.text_corpus for p in profiles)
        has_location = any(p.location for p in profiles)
        has_avatar = any(p.avatar_source or p.image_path for p in profiles)

        return {
            "username_rapidfuzz": True,
            "text_sentence_transformers": sentence_transformers_available(),
            "text_bio_corpus": has_text,
            "behavior_activity_data": has_behavior,
            "behavior_topic_tfidf": has_behavior,
            "behavior_activity_windows": any(p.activity_windows or p.posting_times for p in profiles),
            "image_perceptual_hash": imagehash_available(),
            "image_avatar_hash_username": imagehash_available() and has_avatar,
            "image_opencv_orb": _check_opencv(),
            "image_insightface": insightface_available(),
            "location_fuzzy": has_location,
            "negative_signals": True,
            "weight_renormalization": True,
            "strong_link_clustering": True,
            "computed_username": self._computed_signal_counts.get("username", 0) > 0,
            "computed_text": self._computed_signal_counts.get("text", 0) > 0,
            "computed_behavior": self._computed_signal_counts.get("behavior", 0) > 0,
            "computed_image": self._computed_signal_counts.get("image", 0) > 0,
            "computed_location": self._computed_signal_counts.get("location", 0) > 0,
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
        signal_scores: dict[str, float] = {k: 0.0 for k in MULTIMODAL_WEIGHTS}
        active_signals: dict[str, bool] = {k: False for k in MULTIMODAL_WEIGHTS}

        u_score, u_detail = username_similarity(a.handle, b.handle)
        if a.handle and b.handle:
            signal_scores["username"] = u_score
            active_signals["username"] = True
            self._computed_signal_counts["username"] = self._computed_signal_counts.get("username", 0) + 1
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
                active_signals["username"] = True
                evidences.append(
                    CorrelationEvidence(
                        type="username",
                        score=1.0,
                        weight=SIGNAL_WEIGHTS["username"],
                        detail=f"seed query handle '{seed_handle}' matches profile",
                    )
                )

        has_email_match = bool(a.email and b.email and a.email == b.email)
        if a.email and b.email:
            email_score = 1.0 if has_email_match else 0.0
            evidences.append(
                CorrelationEvidence(
                    type="email",
                    score=email_score,
                    weight=0.0,
                    detail=f"email_a={a.email}, email_b={b.email}",
                )
            )

        if a.text_corpus and b.text_corpus:
            t_score, t_detail = text_similarity(a.text_corpus, b.text_corpus)
            signal_scores["text"] = t_score
            active_signals["text"] = True
            self._computed_signal_counts["text"] = self._computed_signal_counts.get("text", 0) + 1
            evidences.append(
                CorrelationEvidence(type="text", score=t_score, weight=SIGNAL_WEIGHTS["text"], detail=t_detail)
            )

        from services.query_detector import detect_query_type

        use_faces = detect_query_type(seed_query) == "image"
        img_a = a.image_path or a.avatar_source
        img_b = b.image_path or b.avatar_source
        if img_a and img_b:
            if img_a == img_b:
                signal_scores["image"] = 1.0
                active_signals["image"] = True
                self._computed_signal_counts["image"] = self._computed_signal_counts.get("image", 0) + 1
                evidences.append(
                    CorrelationEvidence(
                        type="image", score=1.0, weight=SIGNAL_WEIGHTS["image"], detail="same avatar URL"
                    )
                )
            elif use_faces:
                i_score, i_detail = await image_similarity(img_a, img_b, use_face_embedding=True)
                if i_score > 0:
                    signal_scores["image"] = i_score
                    active_signals["image"] = True
                    self._computed_signal_counts["image"] = self._computed_signal_counts.get("image", 0) + 1
                evidences.append(
                    CorrelationEvidence(type="image", score=i_score, weight=SIGNAL_WEIGHTS["image"], detail=i_detail)
                )
            else:
                i_score, i_detail = await avatar_hash_similarity(img_a, img_b)
                if i_score > 0:
                    signal_scores["image"] = round(i_score * AVATAR_HASH_USERNAME_SCALE, 4)
                    active_signals["image"] = True
                    self._computed_signal_counts["image"] = self._computed_signal_counts.get("image", 0) + 1
                    evidences.append(
                        CorrelationEvidence(
                            type="image",
                            score=signal_scores["image"],
                            weight=SIGNAL_WEIGHTS["image"],
                            detail=i_detail,
                        )
                    )
                else:
                    evidences.append(
                        CorrelationEvidence(
                            type="image",
                            score=0.0,
                            weight=SIGNAL_WEIGHTS["image"],
                            detail=i_detail or "avatar hash unavailable",
                        )
                    )

        behavior_ready = bool(
            (a.behavior_corpus and b.behavior_corpus)
            or (a.posting_times and b.posting_times)
            or (a.hashtags and b.hashtags)
            or (a.activity_windows and b.activity_windows)
        )
        if behavior_ready:
            b_score, b_detail = behavior_similarity(
                a.behavior_corpus,
                b.behavior_corpus,
                a.posting_times,
                b.posting_times,
                hashtags_a=a.hashtags,
                hashtags_b=b.hashtags,
                activity_windows_a=a.activity_windows,
                activity_windows_b=b.activity_windows,
            )
            if b_score > 0:
                if (
                    a.behavior_corpus
                    and a.behavior_corpus == b.behavior_corpus
                    and not (a.metadata.get("social_posts") or b.metadata.get("social_posts"))
                ):
                    b_score = min(b_score, 0.3)
                    b_detail = f"shared_corpus_capped=0.3, {b_detail}"
                signal_scores["behavior"] = b_score
                active_signals["behavior"] = True
                self._computed_signal_counts["behavior"] = self._computed_signal_counts.get("behavior", 0) + 1
                evidences.append(
                    CorrelationEvidence(
                        type="behavior", score=b_score, weight=SIGNAL_WEIGHTS["behavior"], detail=b_detail
                    )
                )

        if a.location and b.location:
            l_score, l_detail = location_similarity(a.location, b.location)
            signal_scores["location"] = l_score
            active_signals["location"] = True
            self._computed_signal_counts["location"] = self._computed_signal_counts.get("location", 0) + 1
            evidences.append(
                CorrelationEvidence(
                    type="location", score=l_score, weight=SIGNAL_WEIGHTS["location"], detail=l_detail
                )
            )

        confidence = calculate_multimodal_score(signal_scores, active_signals)

        if has_email_match:
            confidence = min(confidence + EMAIL_MATCH_BOOST, 1.0)

        neg_penalty, neg_detail, blocked = negative_signal_check(a, b)
        if neg_penalty > 0:
            evidences.append(
                CorrelationEvidence(
                    type="text",
                    score=0.0,
                    weight=0.0,
                    detail=f"negative_signal penalty={neg_penalty:.2f}: {neg_detail}",
                    conflicting=True,
                )
            )
            if blocked:
                confidence = 0.0
            else:
                confidence = round(confidence * (1.0 - min(neg_penalty, NEGATIVE_BLOCK_PENALTY)), 4)

        confidence, conflicting, conflict_explanations = _resolve_conflicts(evidences, confidence)

        link_trigger = _link_trigger(signal_scores, confidence, has_email_match)
        strong_link = _strong_link(signal_scores, confidence, has_email_match, blocked)

        return {
            "confidence": confidence,
            "strong_link": strong_link,
            "link_trigger": link_trigger,
            "evidence": evidences,
            "conflicting": conflicting,
            "conflict_explanations": conflict_explanations,
            "profiles": (a, b),
            "signal_scores": signal_scores,
            "active_signals": active_signals,
            "negative_penalty": neg_penalty,
            "blocked": blocked,
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
        active_any: dict[str, bool] = {k: False for k in MULTIMODAL_WEIGHTS}
        explainability: list[str] = []
        conflicting_pairs = 0
        triggers: list[str] = []

        for i in range(len(member_indices)):
            for j in range(i + 1, len(member_indices)):
                key = (min(member_indices[i], member_indices[j]), max(member_indices[i], member_indices[j]))
                result = pair_results.get(key)
                if not result:
                    continue
                if result.get("strong_link"):
                    trigger = result.get("link_trigger")
                    if trigger:
                        triggers.append(trigger)
                pair_confidences.append(result["confidence"])
                if result["conflicting"]:
                    conflicting_pairs += 1
                explainability.extend(result.get("conflict_explanations", []))
                for signal, active in (result.get("active_signals") or {}).items():
                    if active:
                        active_any[signal] = True
                for ev in result["evidence"]:
                    if ev.type in SIGNAL_WEIGHTS or ev.type == "email":
                        aggregated.setdefault(ev.type, []).append(ev.score)
                    if ev.score >= 0.35:
                        a, b = result["profiles"]
                        explainability.append(_format_explainability(ev, a, b))

        cluster_signal_avg: dict[str, float] = {
            signal: sum(scores) / len(scores) for signal, scores in aggregated.items() if scores
        }
        cluster_confidence = calculate_multimodal_score(cluster_signal_avg, active_any) * 100

        if pair_confidences and not cluster_signal_avg:
            cluster_confidence = (sum(pair_confidences) / len(pair_confidences)) * 100

        if conflicting_pairs:
            reduction = min(0.25, 0.08 * conflicting_pairs)
            cluster_confidence *= 1.0 - reduction
            explainability.append(
                f"Cluster-level conflict resolution: {conflicting_pairs} conflicting pair(s) "
                f"reduced confidence by {reduction * 100:.0f}% — accounts retained in cluster"
            )

        if triggers:
            explainability.append(f"Link triggers: {', '.join(sorted(set(triggers)))}")

        cluster_confidence = min(cluster_confidence, 100.0)

        evidence_summary: list[CorrelationEvidence] = []
        for signal, scores in aggregated.items():
            if not scores:
                continue
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
        meta = profile.metadata or {}
        extracted = meta.get("extracted_intelligence") or {}
        if not isinstance(extracted, dict):
            extracted = {}
        return {
            "entity_id": profile.entity_id,
            "platform": profile.platform,
            "handle": profile.handle,
            "url": profile.url,
            "email": profile.email,
            "verified": profile.verified,
            "fusion_score": profile.fusion_score,
            "sources": profile.sources,
            "display_name": meta.get("display_name") or extracted.get("display_name"),
            "bio": profile.bio,
            "location": profile.location,
            "avatar_url": profile.avatar_source or meta.get("avatar_url") or extracted.get("avatar_url"),
            "website": meta.get("website") or extracted.get("website"),
            "organizations": profile.organizations or extracted.get("organizations") or meta.get("organizations") or [],
            "behavior_snippets": profile.behavior_corpus[:240] if profile.behavior_corpus else None,
            "extracted_intelligence": extracted or None,
        }


correlation_engine = IdentityCorrelationEngine()
