"""Unit tests for Graph Intelligence Engine."""

import unittest

from schemas.correlation import AccountCluster, CorrelationOutput
from schemas.fusion import Entity, FusionOutput
from services.graph_intelligence.engine import GraphIntelligenceEngine


def _entity(platform: str, handle: str) -> Entity:
    return Entity(
        type="account",
        value=f"{platform}/{handle}",
        canonical_value=f"{platform}:{handle}",
        sources=["sherlock"],
        metadata={"platform": platform, "verified": True, "handle": handle},
        fusion_score=0.85,
    )


class TestGraphIntelligence(unittest.TestCase):
    def setUp(self):
        self.engine = GraphIntelligenceEngine()

    def test_builds_graph_from_correlation(self):
        fusion = FusionOutput(
            deduplicated_entities=[
                _entity("github.com", "alice"),
                _entity("twitter.com", "alice"),
                _entity("reddit.com", "bob"),
            ]
        )
        correlation = CorrelationOutput(
            clusters=[
                AccountCluster(
                    account_cluster_id="cluster_test",
                    linked_accounts=[
                        {"platform": "github.com", "handle": "alice"},
                        {"platform": "twitter.com", "handle": "alice"},
                    ],
                    linked_account_refs=["github:alice", "twitter:alice"],
                    confidence_score=78.5,
                    explainability=["Username similarity high"],
                )
            ],
            total_accounts_analyzed=3,
            total_clusters=2,
        )
        output = self.engine.analyze(fusion, correlation, seed_query="alice")
        self.assertGreater(output.node_count, 0)
        self.assertGreater(output.edge_count, 0)
        self.assertIsInstance(output.clusters, list)
        self.assertIsInstance(output.influence_scores, list)
        self.assertIsInstance(output.suspicious_networks, list)

    def test_output_schema(self):
        output = self.engine.analyze(FusionOutput(), CorrelationOutput())
        self.assertEqual(output.node_count, 0)
        self.assertGreater(len(output.warnings), 0)


if __name__ == "__main__":
    unittest.main()
