"""Knowledge graph schema extensions with evidence-backed relationships."""

from typing import Any

from pydantic import BaseModel, Field


class GraphEvidence(BaseModel):
    """Provenance attached to every graph relationship."""

    source_tool: str | None = None
    source_ref: str | None = None
    source_platform: str | None = None
    strategy: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    detail: str = ""


class KnowledgeGraphNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    value: str = ""
    fusion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphEdge(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[GraphEvidence] = Field(default_factory=list)


class ReasoningPath(BaseModel):
    """Investigator reasoning chain through the knowledge graph."""

    path_id: str
    seed: str
    node_ids: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    summary: str = ""


class GraphCluster(BaseModel):
    cluster_id: str
    members: list[str] = Field(default_factory=list)
    algorithm: str = Field(description="louvain | label_propagation")
    modularity: float | None = None


class InfluenceScore(BaseModel):
    node_id: str
    node_type: str
    pagerank: float = 0.0
    betweenness: float = 0.0


class SuspiciousNetwork(BaseModel):
    network_id: str
    network_type: str = Field(description="bot_network | scam_ring | sock_puppet | propaganda_cluster")
    members: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    indicators: list[str] = Field(default_factory=list)


class GraphOutput(BaseModel):
    clusters: list[GraphCluster] = Field(default_factory=list)
    influence_scores: list[InfluenceScore] = Field(default_factory=list)
    suspicious_networks: list[SuspiciousNetwork] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    graph_engine_version: str = "2.0.0"
    warnings: list[str] = Field(default_factory=list)
    neo4j_exported: bool = False
    knowledge_graph_nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    knowledge_graph_edges: list[KnowledgeGraphEdge] = Field(default_factory=list)
    reasoning_paths: list[ReasoningPath] = Field(default_factory=list)
