import { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
// @ts-expect-error no types
import coseBilkent from 'cytoscape-cose-bilkent';
import { runGraph } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';

cytoscape.use(coseBilkent);

export function GraphView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const selectedClusterId = useInvestigationStore((s) => s.selectedClusterId);
  const updateResult = useInvestigationStore((s) => s.updateResult);
  const [filter, setFilter] = useState('all');
  const [subView, setSubView] = useState<'canvas' | 'influence' | 'communities'>('canvas');
  const [rebuilding, setRebuilding] = useState(false);

  useEffect(() => {
    if (!containerRef.current || !result || subView !== 'canvas') return;

    const elements: cytoscape.ElementDefinition[] = [];
    const clusters = result.correlation?.clusters ?? [];
    const selected = clusters.find((c) => c.account_cluster_id === selectedClusterId);
    const targetClusters = filter === 'selected' && selected ? [selected] : clusters;

    targetClusters.forEach((cluster) => {
      const personId = `person_${cluster.account_cluster_id}`;
      elements.push({ data: { id: personId, label: 'Person', type: 'Person' } });

      const acctIds: string[] = [];
      cluster.linked_accounts.forEach((acct, i) => {
        const id = `acct_${cluster.account_cluster_id}_${i}`;
        acctIds.push(id);
        elements.push({ data: { id, label: acct.handle || acct.platform, type: 'Account' } });
        elements.push({ data: { source: personId, target: id, label: 'OWNS' } });
      });

      for (let i = 0; i < acctIds.length; i++) {
        for (let j = i + 1; j < acctIds.length; j++) {
          elements.push({ data: { source: acctIds[i], target: acctIds[j], label: 'CONNECTED' } });
        }
      }
    });

    result.graph?.suspicious_networks?.forEach((net, ni) => {
      const hubId = `sus_${ni}`;
      elements.push({ data: { id: hubId, label: net.network_type, type: 'Suspicious' } });
      net.members.slice(0, 8).forEach((m, mi) => {
        const mid = `susm_${ni}_${mi}`;
        elements.push({ data: { id: mid, label: m.slice(0, 20), type: 'Flagged' } });
        elements.push({ data: { source: hubId, target: mid, label: 'FLAG' } });
      });
    });

    if (cyRef.current) cyRef.current.destroy();

    cyRef.current = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        { selector: 'node', style: { label: 'data(label)', 'font-size': 10, color: '#e2e8f0', 'text-valign': 'bottom', 'text-margin-y': 4, 'background-color': '#3b82f6', width: 28, height: 28 } },
        { selector: 'node[type="Person"]', style: { 'background-color': '#8b5cf6', width: 36, height: 36 } },
        { selector: 'node[type="Suspicious"]', style: { 'background-color': '#ef4444', shape: 'diamond' } },
        { selector: 'edge', style: { width: 1.5, 'line-color': '#475569', 'target-arrow-shape': 'triangle', 'target-arrow-color': '#475569', 'curve-style': 'bezier', opacity: 0.7 } },
      ],
      layout: { name: 'cose-bilkent', randomize: true } as cytoscape.LayoutOptions,
      minZoom: 0.2,
      maxZoom: 3,
    });

    return () => { cyRef.current?.destroy(); cyRef.current = null; };
  }, [result, selectedClusterId, filter, subView]);

  const handleRebuildGraph = async () => {
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

  if (!result) {
    return <div className="flex h-80 items-center justify-center text-sm text-slate-500">Graph appears after investigation</div>;
  }

  const influence = result.graph?.influence_scores ?? [];
  const communities = result.graph?.clusters ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {(['canvas', 'influence', 'communities'] as const).map((v) => (
          <button key={v} onClick={() => setSubView(v)} className={`rounded px-3 py-1 text-xs capitalize ${subView === v ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}>
            {v === 'canvas' ? 'Network' : v}
          </button>
        ))}
        {subView === 'canvas' && (
          <>
            <button onClick={() => setFilter('all')} className={`rounded px-3 py-1 text-xs ${filter === 'all' ? 'bg-slate-600 text-white' : 'bg-slate-800 text-slate-400'}`}>All</button>
            <button onClick={() => setFilter('selected')} className={`rounded px-3 py-1 text-xs ${filter === 'selected' ? 'bg-slate-600 text-white' : 'bg-slate-800 text-slate-400'}`}>Selected</button>
            <button onClick={() => cyRef.current?.fit()} className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300">Fit</button>
          </>
        )}
        <button
          onClick={handleRebuildGraph}
          disabled={rebuilding}
          className="ml-auto rounded border border-slate-600 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
          title="POST /api/intel/graph"
        >
          {rebuilding ? 'Rebuilding…' : 'Rebuild Graph'}
        </button>
      </div>

      {result.graph?.warnings && result.graph.warnings.length > 0 && (
        <div className="text-xs text-amber-400">{result.graph.warnings.join(' · ')}</div>
      )}

      {subView === 'canvas' && (
        <>
          <div ref={containerRef} className="h-72 w-full rounded-lg border border-slate-700 bg-slate-900" />
          <div className="text-xs text-slate-500">
            {result.graph?.node_count ?? 0} nodes · {result.graph?.edge_count ?? 0} edges
            {result.graph?.neo4j_exported && ' · Neo4j exported'}
          </div>
        </>
      )}

      {subView === 'influence' && (
        <div className="max-h-80 overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-400">
                <th className="py-2">Node</th><th>Type</th><th>PageRank</th><th>Betweenness</th>
              </tr>
            </thead>
            <tbody>
              {influence.slice(0, 25).map((s) => (
                <tr key={s.node_id} className="border-b border-slate-800 text-slate-300">
                  <td className="py-1.5 font-mono">{s.node_id.slice(0, 16)}…</td>
                  <td>{s.node_type}</td>
                  <td>{s.pagerank.toFixed(4)}</td>
                  <td>{s.betweenness.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!influence.length && <p className="py-4 text-center text-slate-500">No influence scores</p>}
        </div>
      )}

      {subView === 'communities' && (
        <div className="max-h-80 space-y-2 overflow-y-auto">
          {communities.map((c) => (
            <div key={c.cluster_id} className="rounded-lg border border-slate-700 bg-slate-800/40 p-3 text-sm">
              <div className="flex justify-between">
                <span className="font-mono text-slate-300">{c.cluster_id}</span>
                <span className="text-xs text-slate-500">{c.algorithm}{c.modularity != null ? ` · mod ${c.modularity}` : ''}</span>
              </div>
              <div className="mt-1 text-xs text-slate-400">{c.members.length} members</div>
            </div>
          ))}
          {!communities.length && <p className="py-4 text-center text-slate-500">No communities detected</p>}
        </div>
      )}
    </div>
  );
}
