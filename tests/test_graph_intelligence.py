"""Unit tests for Graph Intelligence Engine."""

import unittest

from schemas.correlation import AccountCluster, CorrelationOutput
from schemas.fusion import Entity, FusionOutput
from schemas.evidence import FieldProvenance
from schemas.intelligence import IdentityProfile
from services.graph_intelligence.engine import GraphIntelligenceEngine
from services.graph_intelligence.knowledge_graph import build_knowledge_graph
from services.graph_intelligence.reasoning import discover_reasoning_paths


def _entity(platform: str, handle: str, **meta) -> Entity:
    return Entity(
        type="account",
        value=f"{platform}/{handle}",
        canonical_value=f"{platform}:{handle}",
        sources=["sherlock"],
        metadata={"platform": platform, "verified": True, "handle": handle, **meta},
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

    def test_knowledge_graph_with_evidence_edges(self):
        fusion = FusionOutput(
            deduplicated_entities=[
                _entity("github.com", "alice", website="https://example.org"),
                Entity(
                    type="email",
                    value="alice@example.org",
                    canonical_value="alice@example.org",
                    sources=["maigret"],
                    fusion_score=0.9,
                ),
            ]
        )
        correlation = CorrelationOutput(
            clusters=[
                AccountCluster(
                    account_cluster_id="cluster_test",
                    linked_accounts=[{"platform": "github.com", "handle": "alice", "email": "alice@example.org"}],
                    linked_account_refs=["github:alice"],
                    confidence_score=80.0,
                    explainability=["Email match"],
                )
            ],
            total_accounts_analyzed=1,
            total_clusters=1,
        )
        identity = IdentityProfile(
            seed_query="alice",
            confidence_score=0.82,
            primary_name="Alice Example",
            emails=[FieldProvenance(field="email", value="alice@example.org", confidence=0.9, source_tool="maigret")],
            organizations=[FieldProvenance(field="organization", value="Example Org", confidence=0.7)],
            total_evidence_fields=3,
            verified_platform_count=1,
            enrichment_passes=1,
        )
        output = self.engine.analyze(
            fusion,
            correlation,
            seed_query="alice",
            identity_profile=identity,
        )
        self.assertGreater(len(output.knowledge_graph_nodes), 0)
        self.assertGreater(len(output.knowledge_graph_edges), 0)
        for edge in output.knowledge_graph_edges:
            self.assertTrue(edge.relation)
            self.assertTrue(edge.source_id)
            self.assertTrue(edge.target_id)
        self.assertGreater(len(output.reasoning_paths), 0)

    def test_build_knowledge_graph_standalone(self):
        nodes, edges = build_knowledge_graph(
            seed_query="targetuser",
            fusion=FusionOutput(deduplicated_entities=[_entity("github.com", "targetuser")]),
            correlation=CorrelationOutput(),
            identity_profile=IdentityProfile(
                seed_query="targetuser",
                confidence_score=0.5,
                usernames=[FieldProvenance(field="username", value="targetuser", confidence=0.8)],
                total_evidence_fields=1,
                verified_platform_count=0,
                enrichment_passes=0,
            ),
        )
        paths = discover_reasoning_paths(nodes, edges, seed_query="targetuser")
        self.assertTrue(any(n.node_type == "Person" or n.node_type == "Username" for n in nodes))
        self.assertIsInstance(paths, list)

    def test_output_schema(self):
        output = self.engine.analyze(FusionOutput(), CorrelationOutput())
        self.assertEqual(output.node_count, 0)
        self.assertGreater(len(output.warnings), 0)

    def test_single_email_no_edges_does_not_crash(self):
        fusion = FusionOutput(
            deduplicated_entities=[
                Entity(
                    type="email",
                    value="manjeshshetty1@gmail.com",
                    canonical_value="manjeshshetty1@gmail.com",
                    sources=["holehe"],
                    fusion_score=0.8,
                )
            ]
        )
        output = self.engine.analyze(fusion, CorrelationOutput(), seed_query="manjeshshetty1@gmail.com")
        self.assertGreaterEqual(output.node_count, 1)
        self.assertIsInstance(output.suspicious_networks, list)


if __name__ == "__main__":
    unittest.main()
