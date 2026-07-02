import { useInvestigationStore } from '../store/investigationStore';
import { startInvestigation } from '../api/investigate';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';
import type { DiscoveryLead, InvestigationTreeNode } from '../types';

function TreeNodeView({ node, nodes, depth = 0 }: { node: InvestigationTreeNode; nodes: InvestigationTreeNode[]; depth?: number }) {
  const children = nodes.filter((n) => n.parent_id === node.node_id);
  const indent = depth * 16;
  const icon = node.node_type === 'seed' ? '🌱' : node.node_type === 'evidence' ? '📋' : node.node_type === 'lead' ? '🔍' : node.node_type === 'hop' ? '⚡' : '👤';
  const color = node.node_type === 'evidence' ? 'text-emerald-400' : node.node_type === 'lead' ? 'text-cyan-400' : node.node_type === 'hop' ? 'text-violet-400' : 'text-slate-300';

  return (
    <div>
      <div className="flex items-start gap-2 py-1" style={{ paddingLeft: indent }}>
        <span className="text-sm">{icon}</span>
        <div className="min-w-0 flex-1">
          <p className={`text-xs ${color}`}>{node.label}</p>
          {node.value && node.value !== node.label && (
            <p className="font-mono text-[10px] text-slate-500">{node.value}</p>
          )}
          {node.status && <span className="text-[10px] text-slate-600"> · {node.status}</span>}
          {node.feature && <span className="text-[10px] text-slate-600"> · {node.feature}</span>}
          {node.lead_type && <span className="text-[10px] text-slate-600"> · {node.lead_type}</span>}
          {node.provenance?.strategy ? (
            <p className="text-[10px] text-slate-600">{String(node.provenance.strategy)}</p>
          ) : null}
        </div>
        <Badge variant="muted">{node.node_type}</Badge>
      </div>
      {children.map((child) => (
        <TreeNodeView key={child.node_id} node={child} nodes={nodes} depth={depth + 1} />
      ))}
    </div>
  );
}

export function DiscoveryChainPanel() {
  const result = useInvestigationStore((s) => s.result);
  const discovery = result?.discovery;
  const tree = discovery?.investigation_tree ?? result?.identity_profile?.investigation_tree;

  if (!discovery?.enabled) {
    return (
      <EmptyState
        icon="🔗"
        title="Auto-pivot discovery"
        description="Run an investigation to automatically follow evidence-generated leads."
      />
    );
  }

  const rootNode = tree?.nodes.find((n) => n.node_id === tree.root_id);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="info">{discovery.total_hops} hop(s)</Badge>
        <Badge variant="success">{discovery.total_leads_discovered} lead(s) found</Badge>
        <Badge variant="muted">{discovery.total_leads_expanded} expanded</Badge>
        <Badge variant="muted">depth {discovery.max_depth_reached}</Badge>
        <Badge variant="muted">{discovery.seed_query_type}</Badge>
        {tree && (
          <>
            <Badge variant="info">{tree.total_evidence_nodes} evidence</Badge>
            <Badge variant="info">{tree.total_lead_nodes} leads</Badge>
            <Badge variant="info">{tree.total_hop_nodes} hops</Badge>
          </>
        )}
        {(discovery.visited?.length ?? 0) > 0 && (
          <Badge variant="muted">{discovery.visited!.length} visited</Badge>
        )}
        <span className="text-xs text-slate-500">Stopped: {discovery.stop_reason.replace(/_/g, ' ')}</span>
      </div>

      {discovery.config && (
        <p className="text-[10px] text-slate-600">
          Config: max depth {discovery.config.max_depth} · max hops {discovery.config.max_hops} · max leads/hop {discovery.config.max_leads_per_hop}
        </p>
      )}

      {tree && rootNode && (
        <div className="space-y-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Investigation Tree</h4>
          <p className="text-xs text-slate-500">How information was discovered — evidence → lead → evidence chains</p>
          <div className="intel-card max-h-80 overflow-y-auto p-4">
            <TreeNodeView node={rootNode} nodes={tree.nodes} />
          </div>
        </div>
      )}

      {discovery.hops.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Expansion Chain</h4>
          {discovery.hops.map((hop) => (
            <div key={hop.hop_id} className="intel-card p-4 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-mono text-cyan-300">{hop.query}</p>
                  <p className="text-xs text-slate-500">
                    depth {hop.depth} · {hop.feature} · {hop.lead_type}
                  </p>
                </div>
                <Badge variant={hop.status === 'completed' ? 'success' : 'danger'}>{hop.status}</Badge>
              </div>
              <p className="mt-2 text-xs text-slate-400">
                {hop.entities_found} entities · {hop.leads_spawned} new lead(s)
                {hop.execution_time_ms ? ` · ${(hop.execution_time_ms / 1000).toFixed(1)}s` : ''}
              </p>
              {hop.reason && <p className="mt-1 text-xs text-slate-500">{hop.reason}</p>}
              {hop.error && <p className="mt-1 text-xs text-rose-400">{hop.error}</p>}
            </div>
          ))}
        </div>
      )}

      {(discovery.pending_leads?.length ?? 0) > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Pending Leads ({discovery.pending_leads!.length})</h4>
          {discovery.pending_leads!.slice(0, 12).map((lead: DiscoveryLead) => (
            <div key={lead.lead_id} className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="font-mono text-xs text-amber-100">{lead.query}</p>
                <p className="mt-1 text-[10px] text-amber-200/60">
                  {lead.lead_type} · {lead.feature} · depth {lead.depth} · priority {(lead.priority * 100).toFixed(0)}%
                </p>
                {lead.reason && <p className="mt-1 text-[10px] text-slate-500">{lead.reason}</p>}
              </div>
              <button
                onClick={() => startInvestigation(lead.query, lead.lead_type)}
                className="intel-btn-ghost shrink-0 py-1 text-[10px]"
              >
                Investigate
              </button>
            </div>
          ))}
        </div>
      )}

      {discovery.timeline.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Discovery Timeline</h4>
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {discovery.timeline.map((event) => (
              <div key={event.event_id} className="rounded-lg border border-slate-800/80 bg-slate-900/40 px-3 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-300">{event.message}</span>
                  <span className="shrink-0 font-mono text-[10px] text-slate-600">{event.phase}</span>
                </div>
                {event.detail && <p className="mt-1 text-slate-500">{event.detail}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
