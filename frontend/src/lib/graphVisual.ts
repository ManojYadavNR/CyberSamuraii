import type cytoscape from 'cytoscape';
import { NODE_COLORS } from './uiHelpers';
import type { GraphOutput, InvestigationResult } from '../types';

export type GraphNodeFilter = 'all' | string;

export interface GraphBuildOptions {
  result: InvestigationResult;
  nodeFilter: GraphNodeFilter;
  clusterFilter: 'all' | 'selected';
  selectedClusterId: string | null;
  selectedPathId: string | null;
  showThreats: boolean;
  nodeSize: (id: string, type: string) => number;
}

export function truncateLabel(text: string, max = 22): string {
  const t = String(text || '').trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

export function nodeShape(type: string): string {
  switch (type) {
    case 'Person': return 'ellipse';
    case 'Account':
    case 'Username': return 'round-rectangle';
    case 'Email':
    case 'Phone': return 'diamond';
    case 'Domain':
    case 'Website': return 'hexagon';
    case 'Suspicious':
    case 'Flagged': return 'octagon';
    default: return 'ellipse';
  }
}

export function relationColor(relation: string): string {
  const r = relation.toUpperCase();
  if (r.includes('OWN')) return '#22d3ee';
  if (r.includes('CORRELAT') || r.includes('CONNECT')) return '#818cf8';
  if (r.includes('FLAG') || r.includes('SUSPIC')) return '#f87171';
  if (r.includes('EMAIL') || r.includes('PHONE')) return '#34d399';
  return '#475569';
}

export function buildGraphElements(opts: GraphBuildOptions): cytoscape.ElementDefinition[] {
  const { result, nodeFilter, clusterFilter, selectedClusterId, selectedPathId, showThreats, nodeSize } = opts;
  const elements: cytoscape.ElementDefinition[] = [];
  const kgNodes = result.graph?.knowledge_graph_nodes ?? [];
  const kgEdges = result.graph?.knowledge_graph_edges ?? [];
  const selectedPath = result.graph?.reasoning_paths?.find((p) => p.path_id === selectedPathId);
  const highlightNodes = new Set(selectedPath?.node_ids ?? []);

  if (kgNodes.length > 0) {
    for (const node of kgNodes) {
      if (nodeFilter !== 'all' && nodeFilter !== node.node_type) continue;
      const label = node.label || node.value || node.node_type;
      elements.push({
        data: {
          id: node.node_id,
          label: truncateLabel(label),
          fullLabel: label,
          type: node.node_type,
          shape: nodeShape(node.node_type),
          size: nodeSize(node.node_id, node.node_type),
          highlighted: highlightNodes.has(node.node_id),
        },
      });
    }
    for (const edge of kgEdges) {
      const src = kgNodes.find((n) => n.node_id === edge.source_id);
      const tgt = kgNodes.find((n) => n.node_id === edge.target_id);
      if (!src || !tgt) continue;
      if (nodeFilter !== 'all' && nodeFilter !== src.node_type && nodeFilter !== tgt.node_type) continue;
      const evidenceText = (edge.evidence ?? [])
        .map((ev) => `${ev.strategy || ev.source_tool || 'evidence'}: ${ev.detail || ev.source_ref || ''} (${((ev.confidence ?? 0.5) * 100).toFixed(0)}%)`)
        .join(' · ');
      elements.push({
        data: {
          id: edge.edge_id,
          source: edge.source_id,
          target: edge.target_id,
          label: edge.relation,
          relation: edge.relation,
          edgeColor: relationColor(edge.relation),
          weight: edge.weight ?? 0.5,
          evidence: evidenceText,
          edgeWidth: Math.max(1.2, (edge.weight ?? 0.5) * 2.5),
          highlighted: highlightNodes.has(edge.source_id) && highlightNodes.has(edge.target_id),
        },
      });
    }
  } else {
    const clusters = result.correlation?.clusters ?? [];
    const selected = clusters.find((c) => c.account_cluster_id === selectedClusterId);
    const targetClusters = clusterFilter === 'selected' && selected ? [selected] : clusters;

    targetClusters.forEach((cluster) => {
      const personId = `person_${cluster.account_cluster_id}`;
      if (nodeFilter === 'all' || nodeFilter === 'Person') {
        elements.push({
          data: {
            id: personId,
            label: 'Person',
            fullLabel: queryLabel(result, cluster.account_cluster_id),
            type: 'Person',
            shape: nodeShape('Person'),
            size: nodeSize(personId, 'Person'),
          },
        });
      }

      const acctIds: string[] = [];
      cluster.linked_accounts.forEach((acct, i) => {
        const id = `acct_${cluster.account_cluster_id}_${i}`;
        const email = acct.email;
        acctIds.push(id);
        const label = acct.handle || acct.platform;
        if (nodeFilter === 'all' || nodeFilter === 'Account') {
          elements.push({
            data: {
              id,
              label: truncateLabel(label),
              fullLabel: label,
              type: 'Account',
              shape: nodeShape('Account'),
              platform: acct.platform,
              size: nodeSize(id, 'Account'),
            },
          });
        }
        if (nodeFilter === 'all' || nodeFilter === 'Person') {
          elements.push({ data: { source: personId, target: id, label: 'OWNS', relation: 'OWNS', edgeColor: relationColor('OWNS'), edgeWidth: 2 } });
        }
        if (email && (nodeFilter === 'all' || nodeFilter === 'Email')) {
          const eid = `email_${id}`;
          elements.push({ data: { id: eid, label: truncateLabel(email), fullLabel: email, type: 'Email', shape: nodeShape('Email'), size: 26 } });
          elements.push({ data: { source: id, target: eid, label: 'USES_EMAIL', relation: 'USES_EMAIL', edgeColor: relationColor('USES_EMAIL'), edgeWidth: 1.5 } });
        }
      });

      for (let i = 0; i < acctIds.length; i++) {
        for (let j = i + 1; j < acctIds.length; j++) {
          elements.push({
            data: { source: acctIds[i], target: acctIds[j], label: 'CONNECTED', relation: 'CONNECTED', edgeColor: relationColor('CONNECTED'), edgeWidth: 1.2 },
          });
        }
      }
    });
  }

  if (showThreats && nodeFilter === 'all') {
    result.graph?.suspicious_networks?.forEach((net, ni) => {
      const hubId = `sus_${ni}`;
      elements.push({
        data: {
          id: hubId,
          label: truncateLabel(net.network_type.replace(/_/g, ' ')),
          fullLabel: net.network_type.replace(/_/g, ' '),
          type: 'Suspicious',
          shape: nodeShape('Suspicious'),
          size: 38,
        },
      });
      net.members.slice(0, 6).forEach((m, mi) => {
        const mid = `susm_${ni}_${mi}`;
        elements.push({ data: { id: mid, label: truncateLabel(m), fullLabel: m, type: 'Flagged', shape: nodeShape('Flagged'), size: 22 } });
        elements.push({ data: { source: hubId, target: mid, label: 'FLAG', relation: 'FLAG', edgeColor: relationColor('FLAG'), edgeWidth: 1.5 } });
      });
    });
  }

  return elements;
}

function queryLabel(result: InvestigationResult, clusterId: string): string {
  return result.fusion?.deduplicated_entities?.[0]?.value as string || clusterId.slice(0, 12);
}

export function graphStylesheet(): cytoscape.StylesheetJson {
  return [
    {
      selector: 'node',
      style: {
        label: 'data(label)',
        'font-size': 10,
        'font-family': 'ui-monospace, monospace',
        color: '#e2e8f0',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 8,
        'text-max-width': '90px',
        'text-wrap': 'ellipsis',
        'text-opacity': 0,
        'min-zoomed-font-size': 14,
        width: 'data(size)',
        height: 'data(size)',
        'background-opacity': 0.92,
        'background-color': '#3b82f6',
        'border-width': 2,
        'border-color': 'rgba(15, 23, 42, 0.9)',
        'border-opacity': 0.85,
        shape: 'ellipse',
        'transition-property': 'background-color, border-width, border-color, opacity, text-opacity',
        'transition-duration': 220,
      },
    },
    ...Object.entries(NODE_COLORS).map(([type, color]) => ({
      selector: `node[type="${type}"]`,
      style: {
        'background-color': color,
        'border-color': color,
        shape: nodeShape(type),
      },
    })),
    {
      selector: 'node[?highlighted]',
      style: {
        'border-width': 4,
        'border-color': '#c084fc',
        'text-opacity': 1,
      },
    },
    {
      selector: 'node.focused',
      style: {
        'border-width': 4,
        'border-color': '#22d3ee',
        'text-opacity': 1,
      },
    },
    {
      selector: 'node.neighbor',
      style: {
        'text-opacity': 0.85,
        'border-width': 3,
        'border-color': '#67e8f9',
      },
    },
    {
      selector: 'node.hovered',
      style: {
        'text-opacity': 1,
        'border-width': 3,
        'border-color': '#f8fafc',
      },
    },
    {
      selector: 'node.dimmed',
      style: { opacity: 0.12 },
    },
    {
      selector: 'edge',
      style: {
        width: 'data(edgeWidth)',
        'line-color': '#334155',
        'target-arrow-color': '#475569',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.85,
        'curve-style': 'unbundled-bezier',
        'control-point-distances': 40,
        'control-point-weights': 0.5,
        opacity: 0.35,
        'transition-property': 'opacity, line-color, width',
        'transition-duration': 220,
      },
    },
    {
      selector: 'edge[relation]',
      style: {
        'line-color': 'data(edgeColor)',
        'target-arrow-color': 'data(edgeColor)',
      },
    },
    {
      selector: 'edge[?highlighted]',
      style: {
        'line-color': '#c084fc',
        'target-arrow-color': '#c084fc',
        width: 3.5,
        opacity: 1,
      },
    },
    {
      selector: 'edge.focused',
      style: {
        'line-color': '#22d3ee',
        'target-arrow-color': '#22d3ee',
        opacity: 0.95,
        width: 3,
      },
    },
    {
      selector: 'edge.dimmed',
      style: { opacity: 0.06 },
    },
  ] as cytoscape.StylesheetJson;
}

export function graphLayoutOptions(nodeCount: number): cytoscape.LayoutOptions {
  const spread = nodeCount > 30 ? 180 : nodeCount > 15 ? 140 : 110;
  return {
    name: 'cose-bilkent',
    quality: 'default',
    randomize: true,
    animate: true,
    animationDuration: 900,
    animationEasing: 'ease-out-cubic',
    fit: true,
    padding: 48,
    nodeDimensionsIncludeLabels: false,
    idealEdgeLength: spread,
    edgeElasticity: 0.42,
    nestingFactor: 0.08,
    gravity: 0.22,
    numIter: 2800,
    tile: true,
    tilingPaddingVertical: 24,
    tilingPaddingHorizontal: 24,
  } as cytoscape.LayoutOptions;
}

export function graphStats(graph?: GraphOutput) {
  const nodes = graph?.knowledge_graph_nodes?.length ?? graph?.node_count ?? 0;
  const edges = graph?.knowledge_graph_edges?.length ?? graph?.edge_count ?? 0;
  const paths = graph?.reasoning_paths?.length ?? 0;
  const threats = graph?.suspicious_networks?.length ?? 0;
  return { nodes, edges, paths, threats };
}
