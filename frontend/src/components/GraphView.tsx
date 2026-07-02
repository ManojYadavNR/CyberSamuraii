import { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
// @ts-expect-error no types
import coseBilkent from 'cytoscape-cose-bilkent';
import { runGraph } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';
import { NODE_COLORS } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

cytoscape.use(coseBilkent);

type NodeFilter = 'all' | string;
type GraphMode = 'network' | 'community' | 'influence' | 'suspicious';

export function GraphView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const selectedClusterId = useInvestigationStore((s) => s.selectedClusterId);
  const updateResult = useInvestigationStore((s) => s.updateResult);
  const [nodeFilter, setNodeFilter] = useState<NodeFilter>('all');
  const [graphMode, setGraphMode] = useState<GraphMode>('network');
  const [clusterFilter, setClusterFilter] = useState<'all' | 'selected'>('all');
  const [tooltip, setTooltip] = useState('');
  const [fullscreen, setFullscreen] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [selectedPathId, setSelectedPathId] = useState<string | null>(null);

  const influenceMap = new Map(
    (result?.graph?.influence_scores ?? []).map((s) => [s.node_id, s.pagerank]),
  );

  const nodeSize = (id: string, type: string) => {
    const pr = influenceMap.get(id) ?? 0;
    const base = type === 'Person' ? 42 : 28;
    return base + Math.min(pr * 800, 36);
  };

  useEffect(() => {
    if (!containerRef.current || !result || graphMode !== 'network') return;

    const elements: cytoscape.ElementDefinition[] = [];
    const kgNodes = result.graph?.knowledge_graph_nodes ?? [];
    const kgEdges = result.graph?.knowledge_graph_edges ?? [];
    const selectedPath = result.graph?.reasoning_paths?.find((p) => p.path_id === selectedPathId);
    const highlightNodes = new Set(selectedPath?.node_ids ?? []);

    if (kgNodes.length > 0) {
      for (const node of kgNodes) {
        if (nodeFilter !== 'all' && nodeFilter !== node.node_type) continue;
        elements.push({
          data: {
            id: node.node_id,
            label: node.label || node.value || node.node_type,
            type: node.node_type,
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
            weight: edge.weight ?? 0.5,
            evidence: evidenceText,
            edgeWidth: Math.max(1.5, (edge.weight ?? 0.5) * 3),
            highlighted: highlightNodes.has(edge.source_id) && highlightNodes.has(edge.target_id),
          },
        });
      }
      if (nodeFilter === 'all') {
        result.graph?.suspicious_networks?.forEach((net, ni) => {
          const hubId = `sus_${ni}`;
          elements.push({ data: { id: hubId, label: net.network_type.replace(/_/g, ' '), type: 'Suspicious', size: 34 } });
          net.members.slice(0, 6).forEach((m, mi) => {
            const mid = `susm_${ni}_${mi}`;
            elements.push({ data: { id: mid, label: m.slice(0, 16), type: 'Flagged', size: 20 } });
            elements.push({ data: { source: hubId, target: mid, label: 'FLAG', edgeWidth: 1.5 } });
          });
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
            data: { id: personId, label: 'Person', type: 'Person', size: nodeSize(personId, 'Person') },
          });
        }

        const acctIds: string[] = [];
        cluster.linked_accounts.forEach((acct, i) => {
          const id = `acct_${cluster.account_cluster_id}_${i}`;
          const email = acct.email;
          acctIds.push(id);
          if (nodeFilter === 'all' || nodeFilter === 'Account') {
            elements.push({
              data: {
                id,
                label: acct.handle || acct.platform,
                type: 'Account',
                platform: acct.platform,
                size: nodeSize(id, 'Account'),
              },
            });
          }
          if (nodeFilter === 'all' || nodeFilter === 'Person') {
            elements.push({ data: { source: personId, target: id, label: 'OWNS', edgeWidth: 1.5 } });
          }
          if (email && (nodeFilter === 'all' || nodeFilter === 'Email')) {
            const eid = `email_${id}`;
            elements.push({ data: { id: eid, label: email, type: 'Email', size: 24 } });
            elements.push({ data: { source: id, target: eid, label: 'USES_EMAIL', edgeWidth: 1.5 } });
          }
        });

        for (let i = 0; i < acctIds.length; i++) {
          for (let j = i + 1; j < acctIds.length; j++) {
            elements.push({ data: { source: acctIds[i], target: acctIds[j], label: 'CONNECTED', edgeWidth: 1.5 } });
          }
        }
      });

      if (graphMode === 'network' || nodeFilter === 'all') {
        result.graph?.suspicious_networks?.forEach((net, ni) => {
          const hubId = `sus_${ni}`;
          elements.push({ data: { id: hubId, label: net.network_type.replace(/_/g, ' '), type: 'Suspicious', size: 34 } });
          net.members.slice(0, 6).forEach((m, mi) => {
            const mid = `susm_${ni}_${mi}`;
            elements.push({ data: { id: mid, label: m.slice(0, 16), type: 'Flagged', size: 20 } });
            elements.push({ data: { source: hubId, target: mid, label: 'FLAG', edgeWidth: 1.5 } });
          });
        });
      }
    }

    if (cyRef.current) cyRef.current.destroy();

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'font-size': 9,
            color: '#cbd5e1',
            'text-valign': 'bottom',
            'text-margin-y': 6,
            width: 'data(size)',
            height: 'data(size)',
            'background-color': '#3b82f6',
            'border-width': 1,
            'border-color': '#1e293b',
            'transition-property': 'background-color, width, height',
            'transition-duration': 300,
          },
        },
        ...Object.entries(NODE_COLORS).map(([type, color]) => ({
          selector: `node[type="${type}"]`,
          style: { 'background-color': color },
        })),
        {
          selector: 'edge[edgeWidth]',
          style: {
            width: 'data(edgeWidth)',
            'line-color': '#334155',
            'target-arrow-color': '#475569',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            opacity: 0.65,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1.5,
            'line-color': '#334155',
            'target-arrow-color': '#475569',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            opacity: 0.65,
          },
        },
        { selector: 'node[highlighted]', style: { 'border-width': 3, 'border-color': '#a855f7' } },
        { selector: 'edge[highlighted]', style: { 'line-color': '#a855f7', 'target-arrow-color': '#a855f7', width: 3, opacity: 1 } },
        { selector: 'node:selected', style: { 'border-width': 3, 'border-color': '#22d3ee' } },
      ],
      layout: { name: 'cose-bilkent', randomize: true, animate: true, animationDuration: 500 } as cytoscape.LayoutOptions,
      minZoom: 0.15,
      maxZoom: 4,
    });

    cy.on('mouseover', 'node', (e) => {
      const d = e.target.data();
      setTooltip(`${d.type}: ${d.label}`);
    });
    cy.on('mouseover', 'edge', (e) => {
      const d = e.target.data();
      const parts = [d.label];
      if (d.evidence) parts.push(d.evidence);
      setTooltip(parts.join(' — '));
    });
    cy.on('mouseout', 'node, edge', () => setTooltip(''));

    cyRef.current = cy;
    return () => { cy.destroy(); cyRef.current = null; };
  }, [result, selectedClusterId, clusterFilter, nodeFilter, graphMode, selectedPathId]);

  const handleRebuild = async () => {
    if (!result?.fusion?.deduplicated_entities) return;
    setRebuilding(true);
    try {
      const graph = await runGraph(
        query,
        result.fusion.deduplicated_entities as unknown as Record<string, unknown>[],
        (result.correlation?.clusters ?? []) as unknown as Record<string, unknown>[],
      );
      updateResult({ graph });
    } catch {
      alert('Graph rebuild failed');
    } finally {
      setRebuilding(false);
    }
  };

  const toggleFullscreen = () => {
    if (!wrapperRef.current) return;
    if (!document.fullscreenElement) {
      wrapperRef.current.requestFullscreen?.();
      setFullscreen(true);
    } else {
      document.exitFullscreen?.();
      setFullscreen(false);
    }
  };

  if (!result) {
    return <EmptyState icon="🕸" title="Network graph" description="Relationship graph builds automatically after correlation completes." />;
  }

  const influence = result.graph?.influence_scores ?? [];
  const communities = result.graph?.clusters ?? [];
  const suspicious = result.graph?.suspicious_networks ?? [];
  const reasoningPaths = result.graph?.reasoning_paths ?? [];
  const kgNodeTypes = [...new Set((result.graph?.knowledge_graph_nodes ?? []).map((n) => n.node_type))];

  const FILTERS: { id: NodeFilter; label: string }[] = [
    { id: 'all', label: 'Show All' },
    ...kgNodeTypes.map((t) => ({ id: t, label: t })),
    ...(kgNodeTypes.length === 0
      ? [
          { id: 'Person', label: 'Persons' },
          { id: 'Account', label: 'Accounts' },
          { id: 'Email', label: 'Emails' },
          { id: 'Domain', label: 'Domains' },
          { id: 'Phone', label: 'Phones' },
          { id: 'Image', label: 'Images' },
        ]
      : []),
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {(['network', 'community', 'influence', 'suspicious'] as GraphMode[]).map((m) => (
          <button
            key={m}
            onClick={() => setGraphMode(m)}
            className={`rounded-md px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider ${
              graphMode === m ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' : 'bg-slate-800/50 text-slate-500 border border-transparent'
            }`}
          >
            {m === 'network' ? 'Network' : m === 'community' ? 'Community' : m === 'influence' ? 'Influence' : 'Suspicious'}
          </button>
        ))}
      </div>

      {graphMode === 'network' && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((f) => (
              <button key={f.id} onClick={() => setNodeFilter(f.id)} className={`rounded px-2 py-1 text-[10px] ${nodeFilter === f.id ? 'bg-slate-600 text-white' : 'text-slate-500 hover:text-slate-300'}`}>
                {f.label}
              </button>
            ))}
          </div>
          {selectedClusterId && (
            <div className="ml-auto flex gap-1 rounded-lg border border-slate-800/80 bg-slate-900/40 p-0.5">
              {(['all', 'selected'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setClusterFilter(mode)}
                  className={`rounded px-2 py-1 text-[10px] font-medium ${
                    clusterFilter === mode ? 'bg-cyan-500/20 text-cyan-300' : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {mode === 'all' ? 'All Clusters' : 'Selected Cluster'}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {graphMode === 'network' && (
        <div ref={wrapperRef} className={`relative overflow-hidden rounded-xl border border-slate-800 bg-[#060a12] ${fullscreen ? 'h-screen' : 'h-[420px]'}`}>
          <div ref={containerRef} className="h-full w-full" />
          {tooltip && (
            <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-xs text-cyan-200 shadow-xl">
              {tooltip}
            </div>
          )}
          <div className="absolute bottom-3 right-3 flex gap-2">
            <button onClick={() => cyRef.current?.fit(undefined, 40)} className="intel-btn-ghost py-1 text-xs">Fit</button>
            <button onClick={toggleFullscreen} className="intel-btn-ghost py-1 text-xs">{fullscreen ? 'Exit' : 'Fullscreen'}</button>
            <button onClick={handleRebuild} disabled={rebuilding} className="intel-btn-ghost py-1 text-xs">{rebuilding ? '…' : 'Rebuild'}</button>
          </div>
          <div className="absolute bottom-3 left-3 flex flex-wrap gap-2 rounded-lg border border-slate-800/80 bg-slate-900/90 p-2">
            {Object.entries(NODE_COLORS).slice(0, 6).map(([type, color]) => (
              <span key={type} className="flex items-center gap-1 text-[9px] text-slate-400">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                {type}
              </span>
            ))}
          </div>
        </div>
      )}

      {graphMode === 'community' && (
        <div className="max-h-[420px] space-y-2 overflow-y-auto">
          {communities.map((c) => (
            <div key={c.cluster_id} className="intel-card p-4">
              <div className="flex justify-between">
                <span className="font-mono text-sm text-cyan-300">{c.cluster_id}</span>
                <Badge variant="info">{c.algorithm}</Badge>
              </div>
              <p className="mt-1 text-xs text-slate-500">{c.members.length} members{c.modularity != null ? ` · modularity ${c.modularity}` : ''}</p>
            </div>
          ))}
          {!communities.length && <p className="py-8 text-center text-sm text-slate-500">No communities detected</p>}
        </div>
      )}

      {graphMode === 'influence' && (
        <div className="max-h-[420px] overflow-y-auto rounded-xl border border-slate-800">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-900">
              <tr className="border-b border-slate-800 text-left text-slate-500">
                <th className="p-3">Node</th><th className="p-3">Type</th><th className="p-3">PageRank</th><th className="p-3">Betweenness</th>
              </tr>
            </thead>
            <tbody>
              {influence.slice(0, 30).map((s) => (
                <tr key={s.node_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  <td className="p-3 font-mono text-slate-300">{s.node_id.slice(0, 18)}</td>
                  <td className="p-3"><Badge variant="muted">{s.node_type}</Badge></td>
                  <td className="p-3 font-mono text-cyan-400">{s.pagerank.toFixed(4)}</td>
                  <td className="p-3 font-mono text-slate-400">{s.betweenness.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {graphMode === 'suspicious' && (
        <div className="space-y-3">
          {suspicious.map((net) => (
            <div key={net.network_id} className="rounded-xl border border-rose-500/25 bg-rose-500/5 p-4">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-rose-300">{net.network_type.replace(/_/g, ' ')}</span>
                <Badge variant="danger">{(net.confidence * 100).toFixed(0)}% risk</Badge>
              </div>
              <ul className="mt-2 space-y-1 text-xs text-slate-400">
                {net.indicators.map((ind, i) => <li key={i}>• {ind}</li>)}
              </ul>
            </div>
          ))}
          {!suspicious.length && <EmptyState icon="✓" title="No suspicious networks" description="Graph analysis found no coordinated threat patterns." />}
        </div>
      )}

      <p className="text-[10px] text-slate-600">
        {result.graph?.knowledge_graph_nodes?.length ?? result.graph?.node_count ?? 0} nodes ·{' '}
        {result.graph?.knowledge_graph_edges?.length ?? result.graph?.edge_count ?? 0} edges
        {result.graph?.knowledge_graph_nodes?.length ? ' · knowledge graph' : ''}
        {clusterFilter === 'selected' && ' · filtered to selected cluster'}
      </p>

      {reasoningPaths.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-400">Reasoning paths — click to highlight on graph</p>
          {reasoningPaths.slice(0, 8).map((p) => (
            <button
              key={p.path_id}
              type="button"
              onClick={() => setSelectedPathId(selectedPathId === p.path_id ? null : p.path_id)}
              className={`w-full rounded-lg border px-3 py-2 text-left text-xs transition ${
                selectedPathId === p.path_id
                  ? 'border-purple-500/50 bg-purple-500/10 text-purple-100'
                  : 'border-slate-800/80 bg-slate-900/40 text-slate-300 hover:border-slate-700'
              }`}
            >
              <span className="font-mono text-cyan-400">{(p.confidence * 100).toFixed(0)}%</span> {p.summary}
              <p className="mt-1 font-mono text-[10px] text-slate-500">{p.labels.join(' → ')}</p>
              <p className="mt-0.5 text-[10px] text-slate-600">{p.relations.join(' → ')}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
