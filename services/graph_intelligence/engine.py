"""Graph Intelligence — NetworkX-based relationship discovery on correlated identities."""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from schemas.correlation import CorrelationOutput
from schemas.evidence import EvidenceExtractionOutput
from schemas.fusion import Entity, FusionOutput
from schemas.graph import GraphCluster, GraphOutput, InfluenceScore, SuspiciousNetwork
from schemas.intelligence import IdentityProfile
from schemas.pivot import InvestigationTree
from services.graph_intelligence.knowledge_graph import build_knowledge_graph
from services.graph_intelligence.reasoning import discover_reasoning_paths
from services.image_intelligence.path_utils import display_target_label, is_local_path

logger = logging.getLogger(__name__)

NODE_TYPES = frozenset({"Person", "Account", "Email", "Phone", "Domain", "Image", "Post", "Hashtag"})
EDGE_TYPES = frozenset({"OWNS", "POSTED", "SHARES_IMAGE", "USES_EMAIL", "MENTIONS", "CONNECTED_TO"})


def _import_networkx():
    try:
        import networkx as nx

        return nx
    except ImportError as exc:
        raise RuntimeError("networkx is required for graph intelligence") from exc


def _node_id(node_type: str, value: str) -> str:
    digest = hashlib.sha256(f"{node_type}:{value}".encode()).hexdigest()[:10]
    return f"{node_type.lower()}_{digest}"


class GraphIntelligenceEngine:
    """Build and analyze identity graphs from fusion + correlation outputs."""

    def analyze(
        self,
        fusion: FusionOutput | None,
        correlation: CorrelationOutput | None,
        seed_query: str = "",
        *,
        identity_profile: IdentityProfile | None = None,
        evidence_extraction: EvidenceExtractionOutput | None = None,
        investigation_tree: InvestigationTree | None = None,
    ) -> GraphOutput:
        warnings: list[str] = []
        nx = _import_networkx()
        graph = nx.Graph()

        entities = fusion.deduplicated_entities if fusion else []
        if not entities and not correlation:
            return GraphOutput(warnings=["No fusion or correlation data to build graph"])

        self._ingest_entities(graph, entities)
        self._ingest_correlation(graph, correlation, seed_query)

        if graph.number_of_nodes() == 0:
            return GraphOutput(warnings=["Graph construction produced zero nodes"])

        clusters = self._community_detection(graph, nx)
        influence = self._centrality_analysis(graph, nx)
        suspicious = self._detect_suspicious_networks(graph, correlation, nx)

        neo4j_exported = self._export_neo4j(graph)

        kg_nodes, kg_edges = build_knowledge_graph(
            seed_query=seed_query,
            fusion=fusion,
            correlation=correlation,
            identity_profile=identity_profile,
            evidence_extraction=evidence_extraction,
            investigation_tree=investigation_tree,
        )
        reasoning_paths = discover_reasoning_paths(kg_nodes, kg_edges, seed_query=seed_query)

        return GraphOutput(
            clusters=clusters,
            influence_scores=influence,
            suspicious_networks=suspicious,
            node_count=max(graph.number_of_nodes(), len(kg_nodes)),
            edge_count=max(graph.number_of_edges(), len(kg_edges)),
            warnings=warnings,
            neo4j_exported=neo4j_exported,
            knowledge_graph_nodes=kg_nodes,
            knowledge_graph_edges=kg_edges,
            reasoning_paths=reasoning_paths,
        )

    def _ingest_entities(self, graph: Any, entities: list[Entity]) -> None:
        for entity in entities:
            value = entity.canonical_value or entity.value
            if is_local_path(str(value)):
                continue
            node_type = self._map_entity_type(entity.type)
            nid = _node_id(node_type, value)
            graph.add_node(
                nid,
                label=value,
                node_type=node_type,
                fusion_score=entity.fusion_score,
                sources=entity.sources,
            )

            if entity.type == "account":
                email = entity.metadata.get("email")
                if email:
                    email_nid = _node_id("Email", str(email))
                    graph.add_node(email_nid, label=str(email), node_type="Email")
                    graph.add_edge(nid, email_nid, relation="USES_EMAIL", weight=entity.fusion_score)

            if entity.type == "image":
                for acct in entities:
                    if acct.type == "account" and acct.metadata.get("avatar_url"):
                        acct_val = acct.canonical_value or acct.value
                        if is_local_path(str(acct_val)):
                            continue
                        acct_nid = _node_id("Account", acct_val)
                        if graph.has_node(acct_nid):
                            graph.add_edge(acct_nid, nid, relation="SHARES_IMAGE", weight=0.8)

            if entity.type == "comment" or entity.metadata.get("is_comment"):
                owner = entity.metadata.get("ownerUsername")
                platform = entity.metadata.get("platform", "instagram")
                post_url = entity.metadata.get("postUrl")
                
                if owner:
                    owner_val = f"{platform}:{owner.lower()}"
                    owner_nid = _node_id("Account", owner_val)
                    if not graph.has_node(owner_nid):
                        graph.add_node(owner_nid, label=owner_val, node_type="Account", platform=platform)
                    graph.add_edge(owner_nid, nid, relation="COMMENTED_ON", weight=0.9)
                    
                if post_url:
                    post_nid = _node_id("Post", post_url)
                    if not graph.has_node(post_nid):
                        graph.add_node(post_nid, label=post_url, node_type="Post", platform=platform)
                    graph.add_edge(nid, post_nid, relation="PART_OF", weight=1.0)

    def _ingest_correlation(
        self,
        graph: Any,
        correlation: CorrelationOutput | None,
        seed_query: str,
    ) -> None:
        if not correlation:
            return

        for cluster in correlation.clusters:
            person_id = _node_id("Person", cluster.account_cluster_id)
            graph.add_node(
                person_id,
                label=cluster.account_cluster_id,
                node_type="Person",
                confidence=cluster.confidence_score,
            )

            account_nodes: list[str] = []
            for acct in cluster.linked_accounts:
                platform = acct.get("platform", "unknown")
                handle = acct.get("handle", "")
                value = f"{platform}:{handle}"
                acct_nid = _node_id("Account", value)
                if not graph.has_node(acct_nid):
                    graph.add_node(acct_nid, label=value, node_type="Account", platform=platform)
                graph.add_edge(person_id, acct_nid, relation="OWNS", weight=cluster.confidence_score / 100)
                account_nodes.append(acct_nid)

            for i in range(len(account_nodes)):
                for j in range(i + 1, len(account_nodes)):
                    graph.add_edge(
                        account_nodes[i],
                        account_nodes[j],
                        relation="CONNECTED_TO",
                        weight=cluster.confidence_score / 100,
                    )

        if seed_query and not is_local_path(seed_query):
            seed_nid = _node_id("Hashtag", seed_query)
            graph.add_node(seed_nid, label=seed_query, node_type="Hashtag")
            for node, data in graph.nodes(data=True):
                if data.get("node_type") == "Account" and seed_query.lower() in str(data.get("label", "")).lower():
                    graph.add_edge(node, seed_nid, relation="MENTIONS", weight=0.6)

    def _map_entity_type(self, entity_type: str) -> str:
        mapping = {
            "account": "Account",
            "email": "Email",
            "phone": "Phone",
            "domain": "Domain",
            "image": "Image",
            "person": "Person",
            "post": "Post",
            "hashtag": "Hashtag",
            "comment": "Comment",
            "document": "Document",
        }
        return mapping.get(entity_type, "Account")

    def _community_detection(self, graph: Any, nx: Any) -> list[GraphCluster]:
        clusters: list[GraphCluster] = []
        if graph.number_of_nodes() < 2:
            return clusters

        try:
            from networkx.algorithms import community

            louvain = list(community.louvain_communities(graph, weight="weight", seed=42))
            modularity = community.modularity(graph, louvain, weight="weight")
            for idx, members in enumerate(louvain):
                clusters.append(
                    GraphCluster(
                        cluster_id=f"louvain_{idx}",
                        members=sorted(members),
                        algorithm="louvain",
                        modularity=round(modularity, 4),
                    )
                )
        except Exception as exc:
            logger.debug("Louvain failed: %s", exc)

        try:
            labels = nx.community.label_propagation_communities(graph)
            for idx, members in enumerate(labels):
                clusters.append(
                    GraphCluster(
                        cluster_id=f"label_prop_{idx}",
                        members=sorted(members),
                        algorithm="label_propagation",
                    )
                )
        except Exception as exc:
            logger.debug("Label propagation failed: %s", exc)

        return clusters

    def _centrality_analysis(self, graph: Any, nx: Any) -> list[InfluenceScore]:
        scores: list[InfluenceScore] = []
        if graph.number_of_nodes() == 0:
            return scores

        try:
            pr = nx.pagerank(graph, weight="weight")
        except Exception:
            pr = {n: 0.0 for n in graph.nodes()}

        try:
            bt = nx.betweenness_centrality(graph, weight="weight")
        except Exception:
            bt = {n: 0.0 for n in graph.nodes()}

        for node, data in graph.nodes(data=True):
            scores.append(
                InfluenceScore(
                    node_id=node,
                    node_type=str(data.get("node_type", "Unknown")),
                    pagerank=round(pr.get(node, 0.0), 6),
                    betweenness=round(bt.get(node, 0.0), 6),
                )
            )

        scores.sort(key=lambda s: (-s.pagerank, -s.betweenness))
        return scores[:50]

    def _detect_suspicious_networks(
        self,
        graph: Any,
        correlation: CorrelationOutput | None,
        nx: Any,
    ) -> list[SuspiciousNetwork]:
        suspicious: list[SuspiciousNetwork] = []
        if graph.number_of_nodes() < 3:
            return suspicious

        account_nodes = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "Account"]
        if len(account_nodes) >= 5:
            degrees = dict(graph.degree(account_nodes))
            avg_deg = sum(degrees.values()) / max(len(degrees), 1)
            hub_nodes = [n for n, d in degrees.items() if d >= avg_deg * 2 and d >= 4]
            if hub_nodes:
                suspicious.append(
                    SuspiciousNetwork(
                        network_id="net_bot_hub",
                        network_type="bot_network",
                        members=hub_nodes[:20],
                        confidence=min(0.5 + len(hub_nodes) * 0.05, 0.95),
                        indicators=[
                            "High-degree account hubs suggest automated coordination",
                            f"{len(hub_nodes)} hub accounts with degree >= 2x average",
                        ],
                    )
                )

        if correlation:
            for cluster in correlation.clusters:
                if len(cluster.linked_accounts) >= 8 and cluster.confidence_score < 55:
                    refs = cluster.linked_account_refs or [
                        f"{a.get('platform', 'unknown')}:{a.get('handle', '')}"
                        for a in cluster.linked_accounts
                    ]
                    suspicious.append(
                        SuspiciousNetwork(
                            network_id=f"net_sock_{cluster.account_cluster_id}",
                            network_type="sock_puppet",
                            members=refs[:30],
                            confidence=round(1.0 - cluster.confidence_score / 100, 2),
                            indicators=[
                                f"Large cluster ({len(cluster.linked_accounts)} accounts) with low confidence",
                                "Possible sock-puppet ring — manual verification recommended",
                            ],
                        )
                    )
                conflicting = any(e.conflicting for e in cluster.evidence)
                if conflicting and len(cluster.linked_accounts) >= 4:
                    suspicious.append(
                        SuspiciousNetwork(
                            network_id=f"net_scam_{cluster.account_cluster_id}",
                            network_type="scam_ring",
                            members=cluster.linked_account_refs[:20],
                            confidence=0.65,
                            indicators=[
                                "Conflicting multi-modal signals across cluster members",
                                "Mixed strong/weak identity signals suggest impersonation or scam ring",
                            ],
                        )
                    )

        try:
            if graph.number_of_edges() > 0:
                dense = [c for c in nx.community.greedy_modularity_communities(graph) if len(c) >= 6]
                if dense:
                    members = sorted(dense[0])
                    suspicious.append(
                        SuspiciousNetwork(
                            network_id="net_propaganda_0",
                            network_type="propaganda_cluster",
                            members=members[:25],
                            confidence=0.55,
                            indicators=[
                                f"Dense community of {len(dense[0])} interconnected nodes",
                                "Coordinated narrative or propaganda cluster pattern",
                            ],
                        )
                    )
        except Exception as exc:
            logger.debug("Greedy modularity communities skipped: %s", exc)

        return suspicious

    def _export_neo4j(self, graph: Any) -> bool:
        uri = os.getenv("NEO4J_URI")
        if not uri:
            return False
        try:
            from neo4j import GraphDatabase

            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "")
            driver = GraphDatabase.driver(uri, auth=(user, password))
            with driver.session() as session:
                for node, data in graph.nodes(data=True):
                    session.run(
                        "MERGE (n:Node {id: $id}) SET n.label=$label, n.node_type=$node_type",
                        id=node,
                        label=data.get("label", node),
                        node_type=data.get("node_type", "Unknown"),
                    )
                for u, v, data in graph.edges(data=True):
                    session.run(
                        "MATCH (a:Node {id: $u}), (b:Node {id: $v}) "
                        "MERGE (a)-[r:REL {type: $rel}]->(b) SET r.weight=$weight",
                        u=u,
                        v=v,
                        rel=data.get("relation", "CONNECTED_TO"),
                        weight=data.get("weight", 0.5),
                    )
            driver.close()
            return True
        except Exception as exc:
            logger.debug("Neo4j export skipped: %s", exc)
            return False


graph_engine = GraphIntelligenceEngine()
