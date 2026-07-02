"""Build evidence-backed investigator knowledge graph from all intelligence sources."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from schemas.correlation import CorrelationOutput
from schemas.evidence import EvidenceExtractionOutput
from schemas.fusion import Entity, FusionOutput
from schemas.graph import GraphEvidence, KnowledgeGraphEdge, KnowledgeGraphNode
from schemas.intelligence import IdentityProfile
from schemas.pivot import InvestigationTree
from services.image_intelligence.path_utils import display_target_label, is_local_path


ENTITY_NODE_TYPES: dict[str, str] = {
    "account": "Account",
    "email": "Email",
    "phone": "Phone",
    "domain": "Domain",
    "image": "Image",
    "person": "Person",
    "organization": "Organization",
    "event": "Event",
    "project": "Project",
    "achievement": "Achievement",
    "publication": "Publication",
    "location": "Location",
    "username": "Username",
}

FIELD_NODE_TYPES: dict[str, str] = {
    "names": "Person",
    "aliases": "Person",
    "usernames": "Username",
    "photos": "Image",
    "images": "Image",
    "emails": "Email",
    "phones": "Phone",
    "domains": "Domain",
    "websites": "Website",
    "organizations": "Organization",
    "companies": "Organization",
    "schools": "Organization",
    "achievements": "Achievement",
    "projects": "Project",
    "appearances": "Event",
    "publications": "Publication",
    "events": "Event",
    "locations": "Location",
    "social_accounts": "Account",
    "bios": "Person",
    "public_links": "Website",
}


def _node_id(node_type: str, value: str) -> str:
    digest = hashlib.sha256(f"{node_type}:{value}".encode()).hexdigest()[:12]
    return f"kg_{node_type.lower()}_{digest}"


def _edge_id(source_id: str, target_id: str, relation: str) -> str:
    digest = hashlib.sha256(f"{source_id}:{relation}:{target_id}".encode()).hexdigest()[:10]
    return f"ke_{digest}"


def _evidence_from_provenance(fp, strategy: str = "") -> GraphEvidence:
    return GraphEvidence(
        source_tool=getattr(fp, "source_tool", None),
        source_ref=getattr(fp, "source_ref", None),
        source_platform=getattr(fp, "source_platform", None),
        strategy=strategy or getattr(fp, "extraction_strategy", ""),
        confidence=float(getattr(fp, "confidence", 0.5)),
        detail=f"{getattr(fp, 'field', '')}={getattr(fp, 'value', '')}",
    )


class KnowledgeGraphBuilder:
    """Assemble connected intelligence from fusion, identity, and discovery tree."""

    def __init__(self, seed_query: str):
        self.seed_query = seed_query
        self.nodes: dict[str, KnowledgeGraphNode] = {}
        self.edges: dict[str, KnowledgeGraphEdge] = {}
        self._person_id: str | None = None

    def _ensure_node(
        self,
        node_type: str,
        value: str,
        *,
        label: str | None = None,
        fusion_score: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        val = value.strip()
        if not val:
            return ""
        if is_local_path(val):
            return ""
        nid = _node_id(node_type, val)
        if nid not in self.nodes:
            self.nodes[nid] = KnowledgeGraphNode(
                node_id=nid,
                node_type=node_type,
                label=label or val,
                value=val,
                fusion_score=fusion_score,
                metadata=metadata or {},
            )
        return nid

    def _add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        *,
        weight: float = 0.5,
        evidence: list[GraphEvidence] | None = None,
    ) -> None:
        if not source_id or not target_id or source_id == target_id:
            return
        eid = _edge_id(source_id, target_id, relation)
        if eid in self.edges:
            existing = self.edges[eid]
            if evidence:
                existing.evidence.extend(evidence)
            existing.weight = max(existing.weight, weight)
            return
        self.edges[eid] = KnowledgeGraphEdge(
            edge_id=eid,
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            weight=weight,
            evidence=evidence or [],
        )

    def _ensure_person(self, name: str | None = None) -> str:
        raw = name or self.seed_query
        person_val = display_target_label(raw, face_detected=True) if is_local_path(raw) else raw
        pid = self._ensure_node("Person", person_val, label=name or f"Subject: {person_val}", fusion_score=1.0)
        self._person_id = pid
        return pid

    def ingest_identity(self, profile: IdentityProfile | None) -> None:
        if not profile:
            return
        person_id = self._ensure_person(profile.primary_name or profile.seed_query)

        field_relations = {
            "names": ("IDENTIFIED_AS", "Person"),
            "aliases": ("ALSO_KNOWN_AS", "Person"),
            "usernames": ("HAS_USERNAME", "Username"),
            "photos": ("HAS_PHOTO", "Image"),
            "emails": ("HAS_EMAIL", "Email"),
            "phones": ("HAS_PHONE", "Phone"),
            "websites": ("HAS_WEBSITE", "Website"),
            "domains": ("HAS_DOMAIN", "Domain"),
            "organizations": ("BELONGS_TO", "Organization"),
            "companies": ("BELONGS_TO", "Organization"),
            "schools": ("ATTENDED", "Organization"),
            "achievements": ("ACHIEVED", "Achievement"),
            "projects": ("WORKED_ON", "Project"),
            "appearances": ("APPEARED_AT", "Event"),
            "events": ("PARTICIPATED_IN", "Event"),
            "publications": ("PUBLISHED", "Publication"),
            "locations": ("LOCATED_IN", "Location"),
            "bios": ("DESCRIBED_AS", "Person"),
            "social_accounts": ("OWNS", "Account"),
        }

        for field_name, (relation, node_type) in field_relations.items():
            items = getattr(profile, field_name, []) or []
            for fp in items:
                nid = self._ensure_node(
                    node_type,
                    fp.value,
                    fusion_score=fp.confidence,
                    metadata={"field": fp.field, "source_platform": fp.source_platform},
                )
                self._add_edge(person_id, nid, relation, weight=fp.confidence, evidence=[_evidence_from_provenance(fp)])

        for pp in profile.platform_profiles:
            acct_val = f"{pp.platform}:{pp.handle}" if pp.handle else (pp.url or pp.platform)
            acct_id = self._ensure_node("Account", acct_val, label=pp.platform, fusion_score=pp.fusion_score, metadata={"platform": pp.platform})
            ev = GraphEvidence(source_tool=pp.sources[0] if pp.sources else None, source_ref=pp.url, source_platform=pp.platform, confidence=pp.fusion_score, strategy="platform_profile")
            self._add_edge(person_id, acct_id, "OWNS", weight=pp.fusion_score, evidence=[ev])
            if pp.avatar_url:
                img_id = self._ensure_node("Image", pp.avatar_url, fusion_score=pp.fusion_score)
                self._add_edge(acct_id, img_id, "USES_IMAGE", weight=pp.fusion_score, evidence=[ev])
            if pp.website:
                web_id = self._ensure_node("Website", pp.website, fusion_score=pp.fusion_score)
                self._add_edge(acct_id, web_id, "REFERENCES_WEBSITE", weight=pp.fusion_score, evidence=[ev])
            if pp.email:
                email_id = self._ensure_node("Email", pp.email, fusion_score=pp.fusion_score)
                self._add_edge(acct_id, email_id, "USES_EMAIL", weight=pp.fusion_score, evidence=[ev])
            for org in pp.organizations:
                org_id = self._ensure_node("Organization", org, fusion_score=pp.fusion_score)
                self._add_edge(person_id, org_id, "BELONGS_TO", weight=pp.fusion_score, evidence=[ev])

        for rel in profile.relationships:
            target_id = self._ensure_node("Organization", rel.target, fusion_score=rel.confidence)
            self._add_edge(person_id, target_id, rel.relation_type.upper(), weight=rel.confidence, evidence=[
                GraphEvidence(source_ref=rel.source_ref, confidence=rel.confidence, detail=rel.relation_type)
            ])

    def ingest_entities(self, entities: list[Entity]) -> None:
        person_id = self._person_id or self._ensure_person()

        for entity in entities:
            val = entity.canonical_value or entity.value
            if is_local_path(str(val)):
                continue
            node_type = ENTITY_NODE_TYPES.get(entity.type, entity.type.title())
            nid = self._ensure_node(node_type, val, fusion_score=entity.fusion_score, metadata=dict(entity.metadata or {}))
            ev = GraphEvidence(
                source_tool=entity.sources[0] if entity.sources else None,
                confidence=entity.fusion_score,
                detail=f"entity:{entity.type}",
            )

            if entity.type == "account":
                self._add_edge(person_id, nid, "OWNS", weight=entity.fusion_score, evidence=[ev])
                meta = entity.metadata or {}
                if meta.get("email"):
                    eid = self._ensure_node("Email", str(meta["email"]), fusion_score=entity.fusion_score)
                    self._add_edge(nid, eid, "USES_EMAIL", weight=entity.fusion_score, evidence=[ev])
                if meta.get("avatar_url"):
                    iid = self._ensure_node("Image", str(meta["avatar_url"]), fusion_score=entity.fusion_score)
                    self._add_edge(nid, iid, "USES_IMAGE", weight=entity.fusion_score, evidence=[ev])
                if meta.get("website"):
                    wid = self._ensure_node("Website", str(meta["website"]), fusion_score=entity.fusion_score)
                    self._add_edge(nid, wid, "REFERENCES_WEBSITE", weight=entity.fusion_score, evidence=[ev])
                if meta.get("organization"):
                    oid = self._ensure_node("Organization", str(meta["organization"]), fusion_score=entity.fusion_score)
                    self._add_edge(person_id, oid, "BELONGS_TO", weight=entity.fusion_score, evidence=[ev])
            elif entity.type in ("email", "phone", "domain", "image"):
                self._add_edge(person_id, nid, "DISCOVERED", weight=entity.fusion_score, evidence=[ev])

    def ingest_correlation(self, correlation: CorrelationOutput | None) -> None:
        if not correlation:
            return
        for cluster in correlation.clusters:
            cluster_person = self._ensure_node("Person", cluster.account_cluster_id, label=f"Cluster {cluster.account_cluster_id[:8]}", fusion_score=cluster.confidence_score / 100)
            if self._person_id:
                self._add_edge(self._person_id, cluster_person, "CORRELATED_WITH", weight=cluster.confidence_score / 100, evidence=[
                    GraphEvidence(confidence=cluster.confidence_score / 100, detail="; ".join(cluster.explainability[:2]))
                ])
            for acct in cluster.linked_accounts:
                val = f"{acct.get('platform', 'unknown')}:{acct.get('handle', '')}"
                aid = self._ensure_node("Account", val, label=acct.get("platform", ""), fusion_score=float(acct.get("fusion_score") or 0.5))
                self._add_edge(cluster_person, aid, "OWNS", weight=cluster.confidence_score / 100)

    def ingest_investigation_tree(self, tree: InvestigationTree | None) -> None:
        if not tree:
            return
        node_map: dict[str, str] = {}
        for tnode in tree.nodes:
            val = tnode.value or tnode.label
            if is_local_path(str(val)):
                continue
            ntype = {"seed": "Person", "evidence": "Evidence", "lead": "Lead", "hop": "Investigation", "profile": "Person"}.get(tnode.node_type, "Evidence")
            kg_id = self._ensure_node(ntype, val, label=tnode.label, metadata=tnode.provenance)
            node_map[tnode.node_id] = kg_id
            if tnode.parent_id and tnode.parent_id in node_map:
                self._add_edge(node_map[tnode.parent_id], kg_id, "LED_TO", weight=0.6, evidence=[
                    GraphEvidence(strategy=str(tnode.provenance.get("expansion_strategy", "")), detail=tnode.label)
                ])

    def build(self) -> tuple[list[KnowledgeGraphNode], list[KnowledgeGraphEdge]]:
        return list(self.nodes.values()), list(self.edges.values())


def build_knowledge_graph(
    *,
    seed_query: str,
    fusion: FusionOutput | None = None,
    correlation: CorrelationOutput | None = None,
    identity_profile: IdentityProfile | None = None,
    evidence_extraction: EvidenceExtractionOutput | None = None,
    investigation_tree: InvestigationTree | None = None,
) -> tuple[list[KnowledgeGraphNode], list[KnowledgeGraphEdge]]:
    builder = KnowledgeGraphBuilder(seed_query)
    if identity_profile:
        builder.ingest_identity(identity_profile)
    elif evidence_extraction and evidence_extraction.unified_profile:
        from services.intelligence.person import build_identity_profile

        profile = build_identity_profile(
            seed_query=seed_query,
            fusion=fusion,
            evidence_extraction=evidence_extraction,
            investigation_tree=investigation_tree,
        )
        builder.ingest_identity(profile)
    if fusion:
        builder.ingest_entities(fusion.deduplicated_entities)
    builder.ingest_correlation(correlation)
    tree = investigation_tree
    if not tree and identity_profile and identity_profile.investigation_tree:
        tree = identity_profile.investigation_tree
    builder.ingest_investigation_tree(tree)
    return builder.build()
