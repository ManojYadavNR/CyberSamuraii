"""Build investigation trees from pivot evidence and lead chains."""

from __future__ import annotations

from uuid import uuid4

from schemas.discovery import DiscoveryHop, DiscoveryLead
from schemas.pivot import InvestigationTree, InvestigationTreeNode, PivotEvidence


def _node(
    *,
    node_type: str,
    label: str,
    value: str | None = None,
    parent_id: str | None = None,
    depth: int = 0,
    **kwargs,
) -> InvestigationTreeNode:
    return InvestigationTreeNode(
        node_id=str(uuid4()),
        node_type=node_type,  # type: ignore[arg-type]
        label=label,
        value=value,
        parent_id=parent_id,
        depth=depth,
        **kwargs,
    )


class InvestigationTreeBuilder:
    """Tracks evidence → lead → hop chains for investigator transparency."""

    def __init__(self, seed_query: str):
        self.seed_query = seed_query
        self.root = _node(node_type="seed", label="Seed investigation", value=seed_query, depth=0)
        self.nodes: dict[str, InvestigationTreeNode] = {self.root.node_id: self.root}
        self._lead_nodes: dict[str, str] = {}
        self._evidence_nodes: dict[str, str] = {}

    def add_evidence(self, evidence: PivotEvidence, *, parent_id: str | None = None) -> str:
        parent = parent_id or self.root.node_id
        key = f"{evidence.entity_id}:{evidence.field}:{evidence.value.lower()}"
        if key in self._evidence_nodes:
            return self._evidence_nodes[key]

        node = _node(
            node_type="evidence",
            label=f"{evidence.field}: {evidence.value[:80]}",
            value=evidence.value,
            parent_id=parent,
            depth=self.nodes[parent].depth + 1,
            provenance={
                "entity_id": evidence.entity_id,
                "entity_type": evidence.entity_type,
                "strategy": evidence.strategy,
                "source_tool": evidence.source_tool,
                "source_platform": evidence.source_platform,
                "source_ref": evidence.source_ref,
                "confidence": evidence.confidence,
            },
        )
        self.nodes[node.node_id] = node
        self.nodes[parent].children_ids.append(node.node_id)
        self._evidence_nodes[key] = node.node_id
        return node.node_id

    def add_lead(self, lead: DiscoveryLead, *, parent_evidence_id: str | None = None) -> str:
        parent = parent_evidence_id or self.root.node_id
        if lead.lead_id in self._lead_nodes:
            return self._lead_nodes[lead.lead_id]

        node = _node(
            node_type="lead",
            label=f"Lead: {lead.query}",
            value=lead.query,
            parent_id=parent,
            depth=self.nodes[parent].depth + 1,
            status="queued",
            feature=lead.feature,
            lead_type=lead.lead_type,
            provenance={
                "reason": lead.reason,
                "source_entity_id": lead.source_entity_id,
                "source_entity_type": lead.source_entity_type,
                "priority": lead.priority,
                **lead.metadata,
            },
        )
        self.nodes[node.node_id] = node
        self.nodes[parent].children_ids.append(node.node_id)
        self._lead_nodes[lead.lead_id] = node.node_id
        return node.node_id

    def add_hop(
        self,
        hop: DiscoveryHop,
        *,
        parent_lead_id: str | None,
        evidence_items: list[PivotEvidence] | None = None,
    ) -> str:
        parent_node_id = self._lead_nodes.get(parent_lead_id or "") or self.root.node_id
        node = _node(
            node_type="hop",
            label=f"Investigated: {hop.query}",
            value=hop.query,
            parent_id=parent_node_id,
            depth=self.nodes[parent_node_id].depth + 1,
            status=hop.status,
            feature=hop.feature,
            lead_type=hop.lead_type,
            provenance={
                "hop_id": hop.hop_id,
                "entities_found": hop.entities_found,
                "leads_spawned": hop.leads_spawned,
                "reason": hop.reason,
                "error": hop.error,
            },
        )
        self.nodes[node.node_id] = node
        self.nodes[parent_node_id].children_ids.append(node.node_id)
        if parent_lead_id and parent_lead_id in self._lead_nodes:
            lead_node = self.nodes[self._lead_nodes[parent_lead_id]]
            lead_node.status = hop.status

        for ev in evidence_items or []:
            self.add_evidence(ev, parent_id=node.node_id)

        return node.node_id

    def build(self) -> InvestigationTree:
        all_nodes = list(self.nodes.values())
        evidence_count = sum(1 for n in all_nodes if n.node_type == "evidence")
        lead_count = sum(1 for n in all_nodes if n.node_type == "lead")
        hop_count = sum(1 for n in all_nodes if n.node_type == "hop")
        max_depth = max((n.depth for n in all_nodes), default=0)
        return InvestigationTree(
            root_id=self.root.node_id,
            seed_query=self.seed_query,
            nodes=all_nodes,
            total_evidence_nodes=evidence_count,
            total_lead_nodes=lead_count,
            total_hop_nodes=hop_count,
            max_depth=max_depth,
        )
