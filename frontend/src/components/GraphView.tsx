import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
// @ts-expect-error no types
import coseBilkent from 'cytoscape-cose-bilkent';
import {
  LuFocus, LuMaximize2, LuMinimize2, LuRefreshCw, LuRoute, LuShieldAlert, LuUsers, LuZap,
} from 'react-icons/lu';
import { runGraph } from '../api/client';
import {
  buildGraphElements,
  graphLayoutOptions,
  graphStats,
  graphStylesheet,
  type GraphNodeFilter,
} from '../lib/graphVisual';
import { NODE_COLORS } from '../lib/uiHelpers';
import { useInvestigationStore } from '../store/investigationStore';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

cytoscape.use(coseBilkent);

type GraphMode = 'network' | 'community' | 'influence' | 'suspicious';

interface SelectedNodeInfo {
  id: string;
  label: string;
  type: string;
  degree: number;
}

export function GraphView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const selectedClusterId = useInvestigationStore((s) => s.selectedClusterId);
  const updateResult = useInvestigationStore((s) => s.updateResult);
  const [nodeFilter, setNodeFilter] = useState<GraphNodeFilter>('all');
  const [graphMode, setGraphMode] = useState<GraphMode>('network');
  const [clusterFilter, setClusterFilter] = useState<'all' | 'selected'>('all');
  const [showThreats, setShowThreats] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [selectedPathId, setSelectedPathId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<SelectedNodeInfo | null>(null);
  const [hoverLabel, setHoverLabel] = useState('');

  const influenceMap = useMemo(
    () => new Map((result?.graph?.influence_scores ?? []).map((s) => [s.node_id, s.pagerank])),
    [result?.graph?.influence_scores],
  );

  const nodeSize = useCallback((id: string, type: string) => {
    const pr = influenceMap.get(id) ?? 0;
    const base = type === 'Person' ? 48 : type === 'Suspicious' ? 40 : 30;
    return base + Math.min(pr * 900, 32);
  }, [influenceMap]);

  const clearFocus = useCallback((cy: cytoscape.Core) => {
    cy.elements().removeClass('focused neighbor dimmed hovered');
    setSelectedNode(null);
  }, []);

  const focusNode = useCallback((cy: cytoscape.Core, node: cytoscape.NodeSingular) => {
    cy.elements().removeClass('focused neighbor dimmed hovered');
    const hood = node.closedNeighborhood();
    cy.elements().not(hood).addClass('dimmed');
    node.addClass('focused');
    node.neighborhood().nodes().not(node).addClass('neighbor');
    node.connectedEdges().addClass('focused');
    setSelectedNode({
      id: node.id(),
      label: String(node.data('fullLabel') || node.data('label') || node.id()),
      type: String(node.data('type') || 'Node'),
      degree: node.degree(),
    });
    cy.animate({
      center: { eles: node },
      zoom: Math.min(2.2, Math.max(cy.zoom(), 1.1)),
    }, { duration: 380 });
  }, []);

  useEffect(() => {
    if (!containerRef.current || !result || graphMode !== 'network') return;

    const elements = buildGraphElements({
      result,
      nodeFilter,
      clusterFilter,
      selectedClusterId,
      selectedPathId,
      showThreats,
      nodeSize,
    });

    if (cyRef.current) cyRef.current.destroy();

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: graphStylesheet(),
      layout: graphLayoutOptions(elements.filter((e) => !e.data.source).length),
      minZoom: 0.08,
      maxZoom: 3.5,
      wheelSensitivity: 0.22,
    });

    cy.on('mouseover', 'node', (e) => {
      const node = e.target;
      node.addClass('hovered');
      const d = node.data();
      setHoverLabel(`${d.type}: ${d.fullLabel || d.label}`);
    });
    cy.on('mouseout', 'node', (e) => {
      e.target.removeClass('hovered');
      setHoverLabel('');
    });
    cy.on('mouseover', 'edge', (e) => {
      const d = e.target.data();
      const parts = [d.relation || d.label];
      if (d.evidence) parts.push(d.evidence);
      setHoverLabel(parts.join(' — '));
    });
    cy.on('mouseout', 'edge', () => setHoverLabel(''));

    cy.on('tap', 'node', (e) => {
      focusNode(cy, e.target);
    });
    cy.on('tap', (e) => {
      if (e.target === cy) clearFocus(cy);
    });

    cyRef.current = cy;
    return () => { cy.destroy(); cyRef.current = null; };
  }, [result, selectedClusterId, clusterFilter, nodeFilter, graphMode, selectedPathId, showThreats, nodeSize, focusNode, clearFocus]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !selectedPathId) return;
    clearFocus(cy);
    const path = result?.graph?.reasoning_paths?.find((p) => p.path_id === selectedPathId);
    if (!path?.node_ids?.length) return;
    let nodes = cy.collection();
    for (const id of path.node_ids) {
      const n = cy.getElementById(id);
      if (n.nonempty()) nodes = nodes.union(n);
    }
    if (nodes.empty()) return;
    cy.elements().addClass('dimmed');
    nodes.removeClass('dimmed');
    nodes.connectedEdges().removeClass('dimmed');
    cy.animate({ fit: { eles: nodes, padding: 72 } }, { duration: 420 });
  }, [selectedPathId, result, clearFocus]);

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
    return <EmptyState icon="🕸" title="Intelligence Graph" description="Relationship graph builds automatically after correlation completes." />;
  }

  const influence = result.graph?.influence_scores ?? [];
  const communities = result.graph?.clusters ?? [];
  const suspicious = result.graph?.suspicious_networks ?? [];
  const reasoningPaths = result.graph?.reasoning_paths ?? [];
  const kgNodeTypes = [...new Set((result.graph?.knowledge_graph_nodes ?? []).map((n) => n.node_type))];
  const stats = graphStats(result.graph);

  const FILTERS: { id: GraphNodeFilter; label: string }[] = [
    { id: 'all', label: 'All types' },
    ...kgNodeTypes.map((t) => ({ id: t, label: t })),
    ...(kgNodeTypes.length === 0
      ? [
          { id: 'Person', label: 'Person' },
          { id: 'Account', label: 'Account' },
          { id: 'Email', label: 'Email' },
          { id: 'Domain', label: 'Domain' },
          { id: 'Phone', label: 'Phone' },
        ]
      : []),
  ];

  const MODES: { id: GraphMode; label: string; icon: typeof LuZap }[] = [
    { id: 'network', label: 'Network', icon: LuZap },
    { id: 'community', label: 'Communities', icon: LuUsers },
    { id: 'influence', label: 'Influence', icon: LuRoute },
    { id: 'suspicious', label: 'Threats', icon: LuShieldAlert },
  ];

  return (
    <div className="intel-graph">
      <div className="intel-graph__header">
        <div className="intel-graph__stats">
          <span className="intel-graph__stat"><strong>{stats.nodes}</strong> nodes</span>
          <span className="intel-graph__stat-sep" />
          <span className="intel-graph__stat"><strong>{stats.edges}</strong> edges</span>
          {stats.paths > 0 && (
            <>
              <span className="intel-graph__stat-sep" />
              <span className="intel-graph__stat"><strong>{stats.paths}</strong> paths</span>
            </>
          )}
          {query && <span className="intel-graph__query">Target: <em>{query}</em></span>}
        </div>
        <div className="intel-graph__modes">
          {MODES.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setGraphMode(id)}
              className={`intel-graph__mode ${graphMode === id ? 'intel-graph__mode--active' : ''}`}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden />
              {label}
            </button>
          ))}
        </div>
      </div>

      {graphMode === 'network' && (
        <>
          <div className="intel-graph__controls">
            <div className="intel-graph__filters">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setNodeFilter(f.id)}
                  className={`intel-graph__filter ${nodeFilter === f.id ? 'intel-graph__filter--active' : ''}`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="intel-graph__toggles">
              {selectedClusterId && (
                <div className="intel-graph__seg">
                  {(['all', 'selected'] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setClusterFilter(mode)}
                      className={`intel-graph__seg-btn ${clusterFilter === mode ? 'intel-graph__seg-btn--active' : ''}`}
                    >
                      {mode === 'all' ? 'All clusters' : 'Selected'}
                    </button>
                  ))}
                </div>
              )}
              <button
                type="button"
                onClick={() => setShowThreats((v) => !v)}
                className={`intel-graph__toggle ${showThreats ? 'intel-graph__toggle--on' : ''}`}
              >
                Threat overlay
              </button>
            </div>
          </div>

          <div className="intel-graph__stage">
            <div
              ref={wrapperRef}
              className={`intel-graph__canvas-wrap ${fullscreen ? 'intel-graph__canvas-wrap--fullscreen' : ''}`}
            >
              <div ref={containerRef} className="intel-graph__canvas" />
              {hoverLabel && (
                <div className="intel-graph__hover-tip">{hoverLabel}</div>
              )}
              <div className="intel-graph__legend">
                {Object.entries(NODE_COLORS).slice(0, 8).map(([type, color]) => (
                  <span key={type} className="intel-graph__legend-item">
                    <span className="intel-graph__legend-dot" style={{ backgroundColor: color }} />
                    {type}
                  </span>
                ))}
              </div>
              <div className="intel-graph__canvas-actions">
                <button
                  type="button"
                  className="intel-graph__fab"
                  title="Fit view"
                  onClick={() => {
                    const cy = cyRef.current;
                    if (!cy) return;
                    clearFocus(cy);
                    cy.fit(undefined, 56);
                  }}
                >
                  <LuFocus className="h-3.5 w-3.5" />
                </button>
                <button type="button" onClick={toggleFullscreen} className="intel-graph__fab" title="Fullscreen">
                  {fullscreen ? <LuMinimize2 className="h-3.5 w-3.5" /> : <LuMaximize2 className="h-3.5 w-3.5" />}
                </button>
                <button type="button" onClick={handleRebuild} disabled={rebuilding} className="intel-graph__fab intel-graph__fab--accent" title="Rebuild graph">
                  <LuRefreshCw className={`h-3.5 w-3.5 ${rebuilding ? 'animate-spin' : ''}`} />
                </button>
              </div>
              <p className="intel-graph__hint">Click a node to focus its connections · scroll to zoom · drag to pan</p>
            </div>

            {selectedNode && (
              <aside className="intel-graph__inspector">
                <p className="intel-graph__inspector-eyebrow">Selected entity</p>
                <h3 className="intel-graph__inspector-title">{selectedNode.label}</h3>
                <div className="intel-graph__inspector-meta">
                  <Badge variant="info">{selectedNode.type}</Badge>
                  <span>{selectedNode.degree} connection{selectedNode.degree === 1 ? '' : 's'}</span>
                </div>
                <p className="intel-graph__inspector-id">{selectedNode.id}</p>
                <button
                  type="button"
                  className="intel-graph__inspector-clear"
                  onClick={() => cyRef.current && clearFocus(cyRef.current)}
                >
                  Clear focus
                </button>
              </aside>
            )}
          </div>
        </>
      )}

      {graphMode === 'community' && (
        <div className="intel-graph__panel-scroll">
          {communities.map((c) => (
            <div key={c.cluster_id} className="intel-graph__card">
              <div className="flex justify-between gap-2">
                <span className="font-mono text-sm text-cyan-300">{c.cluster_id}</span>
                <Badge variant="info">{c.algorithm}</Badge>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {c.members.length} members{c.modularity != null ? ` · modularity ${c.modularity.toFixed(3)}` : ''}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                {c.members.slice(0, 12).map((m) => (
                  <span key={m} className="rounded bg-slate-800/80 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">{m.slice(0, 14)}</span>
                ))}
              </div>
            </div>
          ))}
          {!communities.length && <EmptyState icon="◎" title="No communities" description="Community detection will appear when the graph has enough connected entities." />}
        </div>
      )}

      {graphMode === 'influence' && (
        <div className="intel-graph__panel-scroll">
          <table className="intel-graph__table">
            <thead>
              <tr>
                <th>Node</th><th>Type</th><th>PageRank</th><th>Betweenness</th>
              </tr>
            </thead>
            <tbody>
              {influence.slice(0, 40).map((s) => (
                <tr key={s.node_id}>
                  <td className="font-mono text-slate-300">{s.node_id.slice(0, 22)}</td>
                  <td><Badge variant="muted">{s.node_type}</Badge></td>
                  <td className="font-mono text-cyan-400">{(s.pagerank * 100).toFixed(2)}%</td>
                  <td className="font-mono text-slate-400">{s.betweenness.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {graphMode === 'suspicious' && (
        <div className="intel-graph__panel-scroll">
          {suspicious.map((net) => (
            <div key={net.network_id} className="intel-graph__threat-card">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-rose-200">{net.network_type.replace(/_/g, ' ')}</span>
                <Badge variant="danger">{(net.confidence * 100).toFixed(0)}% risk</Badge>
              </div>
              <ul className="mt-2 space-y-1 text-xs text-slate-400">
                {net.indicators.map((ind, i) => <li key={i}>• {ind}</li>)}
              </ul>
              <div className="mt-3 flex flex-wrap gap-1">
                {net.members.slice(0, 10).map((m) => (
                  <span key={m} className="rounded border border-rose-500/20 bg-rose-500/10 px-1.5 py-0.5 font-mono text-[10px] text-rose-200">{m.slice(0, 18)}</span>
                ))}
              </div>
            </div>
          ))}
          {!suspicious.length && <EmptyState icon="✓" title="No threat patterns" description="Graph analysis found no coordinated suspicious networks." />}
        </div>
      )}

      {reasoningPaths.length > 0 && graphMode === 'network' && (
        <div className="intel-graph__paths">
          <div className="intel-graph__paths-head">
            <LuRoute className="h-4 w-4 text-purple-400" aria-hidden />
            <div>
              <p className="intel-graph__paths-title">Reasoning paths</p>
              <p className="intel-graph__paths-sub">Click a path to highlight it on the graph</p>
            </div>
          </div>
          <div className="intel-graph__paths-rail">
            {reasoningPaths.slice(0, 10).map((p) => (
              <button
                key={p.path_id}
                type="button"
                onClick={() => setSelectedPathId(selectedPathId === p.path_id ? null : p.path_id)}
                className={`intel-graph__path-card ${selectedPathId === p.path_id ? 'intel-graph__path-card--active' : ''}`}
              >
                <span className="intel-graph__path-confidence">{(p.confidence * 100).toFixed(0)}%</span>
                <span className="intel-graph__path-summary">{p.summary}</span>
                <span className="intel-graph__path-chain">
                  {p.labels.map((label, i) => (
                    <span key={`${p.path_id}-${i}`} className="intel-graph__path-chip">
                      {label}{i < p.labels.length - 1 ? <span className="intel-graph__path-arrow">→</span> : null}
                    </span>
                  ))}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
