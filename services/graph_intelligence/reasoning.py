"""Reasoning path discovery over the investigator knowledge graph."""

from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from schemas.graph import KnowledgeGraphEdge, KnowledgeGraphNode, ReasoningPath

RELATION_LABELS: dict[str, str] = {
    "OWNS": "owns",
    "USES_IMAGE": "uses image",
    "REFERENCES_WEBSITE": "references website",
    "USES_EMAIL": "uses email",
    "BELONGS_TO": "belongs to",
    "HOSTS": "hosts",
    "CONTAINS": "contains",
    "HAS_USERNAME": "has username",
    "HAS_EMAIL": "has email",
    "HAS_PHONE": "has phone",
    "HAS_WEBSITE": "has website",
    "HAS_DOMAIN": "has domain",
    "HAS_PHOTO": "has photo",
    "ACHIEVED": "achieved",
    "WORKED_ON": "worked on",
    "PUBLISHED": "published",
    "PARTICIPATED_IN": "participated in",
    "APPEARED_AT": "appeared at",
    "ATTENDED": "attended",
    "DISCOVERED": "discovered",
    "LED_TO": "led to",
    "CORRELATED_WITH": "correlated with",
    "IDENTIFIED_AS": "identified as",
    "ALSO_KNOWN_AS": "also known as",
    "DESCRIBED_AS": "described as",
}


def discover_reasoning_paths(
    nodes: list[KnowledgeGraphNode],
    edges: list[KnowledgeGraphEdge],
    *,
    seed_query: str,
    max_paths: int = 20,
    max_depth: int = 8,
) -> list[ReasoningPath]:
    """Find investigator reasoning chains from seed through connected intelligence."""
    if not nodes or not edges:
        return []

    node_by_id = {n.node_id: n for n in nodes}
    adjacency: dict[str, list[tuple[str, KnowledgeGraphEdge]]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source_id].append((edge.target_id, edge))

    seed_nodes = [
        n.node_id for n in nodes
        if n.node_type == "Person" and (seed_query.lower() in n.value.lower() or seed_query.lower() in n.label.lower())
    ]
    if not seed_nodes:
        seed_nodes = [n.node_id for n in nodes if n.node_type == "Person"][:1]
    if not seed_nodes:
        seed_nodes = [nodes[0].node_id]

    paths: list[ReasoningPath] = []
    seen_signatures: set[str] = set()

    def walk(node_id: str, visited: set[str], chain_nodes: list[str], chain_edges: list[KnowledgeGraphEdge], depth: int) -> None:
        if len(paths) >= max_paths or depth > max_depth:
            return
        node = node_by_id.get(node_id)
        if not node:
            return

        out_degree = len(adjacency.get(node_id, []))
        if depth > 0 and (out_degree == 0 or depth >= 3):
            labels = [node_by_id[nid].label for nid in chain_nodes if nid in node_by_id]
            relations = [RELATION_LABELS.get(e.relation, e.relation.lower()) for e in chain_edges]
            confs = [e.weight for e in chain_edges] or [node.fusion_score]
            confidence = sum(confs) / len(confs) if confs else 0.5
            signature = "→".join(labels)
            if signature not in seen_signatures and len(labels) >= 2:
                seen_signatures.add(signature)
                paths.append(ReasoningPath(
                    path_id=str(uuid4()),
                    seed=seed_query,
                    node_ids=list(chain_nodes),
                    labels=labels,
                    relations=relations,
                    confidence=round(confidence, 4),
                    summary=" → ".join(labels),
                ))

        for target_id, edge in adjacency.get(node_id, []):
            if target_id in visited:
                continue
            visited.add(target_id)
            walk(target_id, visited, chain_nodes + [target_id], chain_edges + [edge], depth + 1)
            visited.discard(target_id)

    for start in seed_nodes:
        walk(start, {start}, [start], [], 0)

    paths.sort(key=lambda p: (-p.confidence, -len(p.labels)))
    return paths[:max_paths]
