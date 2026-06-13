from typing import Any

from pydantic import BaseModel, Field


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
    graph_engine_version: str = "1.0.0"
    warnings: list[str] = Field(default_factory=list)
    neo4j_exported: bool = False
