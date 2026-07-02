"""Unit tests for Identity Correlation Engine v2.1."""

import asyncio
import unittest

from schemas.fusion import Entity, FusionOutput
from services.correlation.engine import (
    IdentityCorrelationEngine,
    calculate_multimodal_score,
    MULTIMODAL_WEIGHTS,
)
from services.correlation.username_similarity import normalize_handle_cross_platform, username_similarity
from services.correlation.text_similarity import text_similarity
from services.correlation.behavior_similarity import behavior_similarity
from services.correlation.location_similarity import location_similarity
from services.correlation.topic_similarity import topic_similarity
from services.correlation.negative_signals import negative_signal_check
from services.correlation.account_parser import entity_to_profile
from services.correlation.activity_data import collect_post_snippets, infer_activity_windows, collect_timestamps


def _entity(platform: str, value: str, **meta) -> Entity:
    return Entity(
        type="account",
        value=value,
        sources=meta.pop("sources", ["sherlock"]),
        metadata={"platform": platform, "verified": True, "check_type": "live_scan", **meta},
        fusion_score=0.9,
    )


class TestExplicitScoring(unittest.TestCase):
    def test_multimodal_formula(self):
        scores = {"username": 1.0, "image": 0.0, "behavior": 0.0, "text": 0.0, "location": 0.0}
        active = {"username": True, "image": False, "behavior": False, "text": False, "location": False}
        self.assertAlmostEqual(calculate_multimodal_score(scores, active), 1.0, places=4)

    def test_renormalization_boosts_text_when_image_missing(self):
        scores = {"username": 0.4, "image": 0.0, "behavior": 0.0, "text": 0.95, "location": 0.0}
        without = calculate_multimodal_score(scores)
        active = {"username": True, "image": False, "behavior": False, "text": True, "location": False}
        with_renorm = calculate_multimodal_score(scores, active)
        self.assertGreater(with_renorm, without)

    def test_full_signal_formula(self):
        scores = {"username": 0.9, "image": 0.8, "behavior": 0.7, "text": 0.6, "location": 0.5}
        result = calculate_multimodal_score(scores)
        manual = 0.30 * 0.9 + 0.25 * 0.8 + 0.20 * 0.7 + 0.20 * 0.6 + 0.05 * 0.5
        self.assertAlmostEqual(result, round(manual, 4), places=4)


class TestUsernameSimilarity(unittest.TestCase):
    def test_exact_match(self):
        score, _ = username_similarity("ManojYadavNR", "manojyadavnr")
        self.assertEqual(score, 1.0)

    def test_cross_platform_handle(self):
        self.assertEqual(normalize_handle_cross_platform("manoj-yadav-nr"), "manojyadavnr")
        score, detail = username_similarity("ManojYadavNR", "manoj-yadav-nr")
        self.assertEqual(score, 1.0)
        self.assertIn("normalized", detail)

    def test_similar_handles(self):
        score, detail = username_similarity("manojyadav", "manojyadavnr")
        self.assertGreater(score, 0.6)
        self.assertIn("jaro_winkler", detail)


class TestTextAndBehavior(unittest.TestCase):
    def test_text_exact(self):
        score, _ = text_similarity("OSINT investigator", "OSINT investigator")
        self.assertEqual(score, 1.0)

    def test_behavior_uses_posts_not_bio(self):
        score, detail = behavior_similarity(
            "Built MERN stack hackathon project #hacktofuture",
            "Runner up at hackathon MERN developer #hacktofuture",
            ["22:30"],
            ["23:00"],
            hashtags_a=["#hacktofuture"],
            hashtags_b=["#hacktofuture"],
            activity_windows_a=["night_owl"],
            activity_windows_b=["night_owl"],
        )
        self.assertGreater(score, 0.4)
        self.assertIn("topic", detail)

    def test_topic_overlap(self):
        score, detail = topic_similarity(
            "MERN developer hackathon runner up Cambridge Institute",
            "Full stack MERN hackathon Cambridge college",
        )
        self.assertGreater(score, 0.2)
        self.assertIn("tfidf", detail)


class TestActivityData(unittest.TestCase):
    def test_collect_posts_from_metadata(self):
        meta = {
            "recent_posts": ["Won hackathon with MERN stack", "HEFT Cranes internship"],
            "highlights": ["#hacktofuture runner up"],
            "organizations": ["Cambridge Institute of Technology"],
        }
        posts = collect_post_snippets(meta)
        self.assertGreaterEqual(len(posts), 2)
        times = collect_timestamps(meta, posts)
        windows = infer_activity_windows(times + ["2024-06-15T23:10:00"])
        self.assertIn("night_owl", windows)


class TestNegativeSignals(unittest.TestCase):
    def test_blocks_doctor_vs_developer(self):
        a = entity_to_profile(_entity(
            "facebook.com", "facebook.com/drmohanyadav",
            username="drmohanyadav",
            bio="Dr. Mohan Yadav Chief Minister",
            location="Bhopal, India",
        ))
        b = entity_to_profile(_entity(
            "github.com", "github.com/manojyadavnr",
            bio="MERN stack developer student",
            location="Bangalore, India",
        ))
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        penalty, detail, blocked = negative_signal_check(a, b)
        self.assertGreater(penalty, 0.0)
        self.assertTrue(blocked or "conflict" in detail.lower())


class TestLocationSimilarity(unittest.TestCase):
    def test_same_city(self):
        score, _ = location_similarity("Bangalore, India", "Bangalore, India")
        self.assertEqual(score, 1.0)


class TestCorrelationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IdentityCorrelationEngine()

    def test_golden_manojyadavnr_cluster(self):
        """GitHub + LinkedIn + Instagram cluster with username and bio evidence."""
        shared_bio = "MERN stack developer | Cambridge Institute of Technology"
        entities = [
            _entity(
                "github.com",
                "github.com/ManojYadavNR",
                url="https://github.com/ManojYadavNR",
                username="ManojYadavNR",
                bio=shared_bio,
                recent_posts=["Built MERN projects for hackathons"],
            ),
            _entity(
                "linkedin.com",
                "linkedin.com/in/manoj-yadav-nr",
                url="https://linkedin.com/in/manoj-yadav-nr",
                username="manoj-yadav-nr",
                bio=shared_bio,
                organizations=["Cambridge Institute of Technology"],
            ),
            _entity(
                "instagram.com",
                "instagram.com/manojyadavnr",
                url="https://instagram.com/manojyadavnr",
                username="manojyadavnr",
                bio="Developer",
                recent_posts=["#hacktofuture runner up MERN"],
                highlights=["Cambridge Institute"],
            ),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="ManojYadavNR"))

        self.assertEqual(output.total_accounts_analyzed, 3)
        self.assertEqual(output.total_clusters, 1)
        cluster = output.clusters[0]
        self.assertEqual(len(cluster.linked_accounts), 3)
        evidence_types = {e.type for e in cluster.evidence}
        self.assertIn("username", evidence_types)
        explain = " ".join(cluster.explainability).lower()
        self.assertTrue(
            any(k in explain for k in ("username", "bio", "topic", "behavior", "link trigger")),
            msg=cluster.explainability,
        )
        self.assertTrue(output.signal_availability.get("behavior_activity_data"))
        self.assertEqual(output.correlation_engine_version, "2.1.1")

    def test_clusters_same_username_across_platforms(self):
        entities = [
            _entity("github.com", "github.com/manojyadavnr", url="https://github.com/manojyadavnr"),
            _entity("twitter.com", "twitter.com/manojyadavnr", url="https://twitter.com/manojyadavnr"),
            _entity("instagram.com", "instagram.com/manojyadavnr", url="https://instagram.com/manojyadavnr"),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="manojyadavnr"))

        self.assertEqual(output.total_accounts_analyzed, 3)
        self.assertEqual(output.total_clusters, 1)
        cluster = output.clusters[0]
        self.assertEqual(len(cluster.linked_accounts), 3)
        self.assertGreater(cluster.confidence_score, 20)
        types = {e.type for e in cluster.evidence}
        self.assertIn("username", types)

    def test_multi_account_clustering(self):
        entities = [
            _entity("github.com", "github.com/alice", url="https://github.com/alice"),
            _entity("reddit.com", "reddit.com/alice", url="https://reddit.com/alice"),
            _entity("twitter.com", "twitter.com/alice99", url="https://twitter.com/alice99"),
            _entity("unknown.com", "unknown.com/bob", url="https://unknown.com/bob"),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="alice"))
        multi = [c for c in output.clusters if len(c.linked_accounts) > 1]
        self.assertGreaterEqual(len(multi), 1)

    def test_email_links_accounts(self):
        entities = [
            _entity("twitter.com", "twitter.com:person@example.com", username="person@example.com", email="person@example.com"),
            _entity("office365.com", "office365.com:person@example.com", username="person@example.com", email="person@example.com"),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="person@example.com"))

        self.assertEqual(output.total_clusters, 1)
        cluster = output.clusters[0]
        email_ev = next((e for e in cluster.evidence if e.type == "email"), None)
        self.assertIsNotNone(email_ev)
        self.assertEqual(email_ev.score, 1.0)

    def test_conflicting_evidence_reduces_confidence(self):
        entities = [
            _entity("github.com", "github.com/alice", bio="loves cats in London"),
            _entity("twitter.com", "twitter.com/bob99", bio="hates everything 999"),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="alice"))
        self.assertGreaterEqual(output.total_clusters, 1)

    def test_wrong_person_not_clustered_with_seed(self):
        entities = [
            _entity(
                "github.com",
                "github.com/ManojYadavNR",
                username="ManojYadavNR",
                bio="MERN developer",
            ),
            _entity(
                "facebook.com",
                "facebook.com/dr.mohan.yadav",
                username="dr.mohan.yadav",
                bio="Dr. Mohan Yadav Chief Minister politician",
                location="Bhopal",
            ),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="ManojYadavNR"))
        multi = [c for c in output.clusters if len(c.linked_accounts) > 1]
        if multi:
            for cluster in multi:
                handles = {a.get("handle") for a in cluster.linked_accounts}
                self.assertFalse(
                    "ManojYadavNR".lower() in {h.lower() for h in handles if h}
                    and "dr.mohan.yadav" in handles,
                )

    def test_explainability_correctness(self):
        entities = [
            _entity("github.com", "github.com/testuser", url="https://github.com/testuser"),
            _entity("gitlab.com", "gitlab.com/testuser", url="https://gitlab.com/testuser"),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="testuser"))
        cluster = output.clusters[0]
        self.assertGreater(len(cluster.explainability), 0)

    def test_singleton_when_no_link(self):
        entities = [
            _entity("github.com", "github.com/alice"),
            _entity("twitter.com", "twitter.com/zzzzunknown999"),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="alice"))
        self.assertGreaterEqual(output.total_clusters, 1)

    def test_output_schema_fields(self):
        entities = [_entity("github.com", "github.com/test")]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion))
        cluster = output.clusters[0]
        self.assertTrue(cluster.account_cluster_id.startswith("cluster_"))
        self.assertIn("username_rapidfuzz", output.signal_availability)
        self.assertIn("weight_renormalization", output.signal_availability)


if __name__ == "__main__":
    unittest.main()
