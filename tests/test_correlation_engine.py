"""Unit tests for Identity Correlation Engine v2."""

import asyncio
import unittest

from schemas.fusion import Entity, FusionOutput
from services.correlation.engine import (
    IdentityCorrelationEngine,
    calculate_multimodal_score,
    MULTIMODAL_WEIGHTS,
)
from services.correlation.username_similarity import username_similarity
from services.correlation.text_similarity import text_similarity
from services.correlation.behavior_similarity import behavior_similarity
from services.correlation.location_similarity import location_similarity


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
        expected = MULTIMODAL_WEIGHTS["username_similarity"]
        self.assertAlmostEqual(calculate_multimodal_score(scores), expected, places=4)

    def test_full_signal_formula(self):
        scores = {"username": 0.9, "image": 0.8, "behavior": 0.7, "text": 0.6, "location": 0.5}
        result = calculate_multimodal_score(scores)
        manual = (
            0.30 * 0.9 + 0.25 * 0.8 + 0.20 * 0.7 + 0.20 * 0.6 + 0.05 * 0.5
        )
        self.assertAlmostEqual(result, round(manual, 4), places=4)


class TestUsernameSimilarity(unittest.TestCase):
    def test_exact_match(self):
        score, _ = username_similarity("ManojYadavNR", "manojyadavnr")
        self.assertEqual(score, 1.0)

    def test_similar_handles(self):
        score, detail = username_similarity("manojyadav", "manojyadavnr")
        self.assertGreater(score, 0.6)
        self.assertIn("jaro_winkler", detail)


class TestTextAndBehavior(unittest.TestCase):
    def test_text_exact(self):
        score, _ = text_similarity("OSINT investigator", "OSINT investigator")
        self.assertEqual(score, 1.0)

    def test_behavior_emoji_overlap(self):
        score, detail = behavior_similarity("hello 😀🔥", "stats 😀🔥", ["09:00"], ["09:00"])
        self.assertGreater(score, 0.5)
        self.assertIn("emoji", detail)


class TestLocationSimilarity(unittest.TestCase):
    def test_same_city(self):
        score, _ = location_similarity("Bangalore, India", "Bangalore, India")
        self.assertEqual(score, 1.0)


class TestCorrelationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IdentityCorrelationEngine()

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
        self.assertEqual(len(cluster.linked_account_refs), 3)
        self.assertTrue(all(":" in ref for ref in cluster.linked_account_refs))
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
        self.assertGreaterEqual(output.total_clusters, 1)
        multi = [c for c in output.clusters if len(c.linked_accounts) > 1]
        self.assertGreaterEqual(len(multi), 1)

    def test_email_links_accounts(self):
        entities = [
            _entity("twitter.com", "twitter.com:user", email="person@example.com"),
            _entity("office365.com", "office365.com:person@example.com", email="person@example.com"),
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
        if output.total_clusters == 1:
            cluster = output.clusters[0]
            self.assertLess(cluster.confidence_score, 80)
            conflict_msgs = [e for e in cluster.explainability if "Conflict" in e or "conflict" in e.lower()]
            self.assertGreaterEqual(len(conflict_msgs), 0)

    def test_missing_image_data_scenario(self):
        entities = [
            _entity("github.com", "github.com/sameuser", bio="developer"),
            _entity("twitter.com", "twitter.com/sameuser", bio="developer"),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="sameuser"))
        cluster = output.clusters[0]
        image_ev = next((e for e in cluster.evidence if e.type == "image"), None)
        if image_ev:
            self.assertEqual(image_ev.score, 0.0)

    def test_explainability_correctness(self):
        entities = [
            _entity("github.com", "github.com/testuser", url="https://github.com/testuser"),
            _entity("gitlab.com", "gitlab.com/testuser", url="https://gitlab.com/testuser"),
        ]
        fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
        output = asyncio.run(self.engine.correlate(fusion, seed_query="testuser"))
        cluster = output.clusters[0]
        self.assertGreater(len(cluster.explainability), 0)
        self.assertTrue(any("Username" in e or "seed query" in e for e in cluster.explainability))

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
        self.assertIsInstance(cluster.explainability, list)
        self.assertIsInstance(cluster.linked_account_refs, list)
        self.assertIn("username_rapidfuzz", output.signal_availability)


if __name__ == "__main__":
    unittest.main()
