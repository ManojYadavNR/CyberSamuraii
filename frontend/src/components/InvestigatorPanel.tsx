import { useInvestigationStore } from '../store/investigationStore';
import { ConfidenceBar } from './ui/ConfidenceBar';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

const SIGNAL_LABELS: Record<string, string> = {
  username: 'Username Similarity',
  image: 'Image Similarity',
  behavior: 'Behavior Similarity',
  text: 'Text Similarity',
  location: 'Location Similarity',
  email: 'Email Match',
};

export function InvestigatorPanel() {
  const result = useInvestigationStore((s) => s.result);
  const selectedClusterId = useInvestigationStore((s) => s.selectedClusterId);

  if (!result) {
    return <EmptyState icon="💡" title="No reasoning data" description="Correlation explainability appears here after investigation completes." />;
  }

  const cluster = result.correlation?.clusters?.find((c) => c.account_cluster_id === selectedClusterId)
    ?? result.correlation?.clusters?.[0];

  if (!cluster) {
    return <EmptyState icon="🔗" title="No clusters" description="No identity clusters were formed from the evidence." />;
  }

  const conflicts = cluster.explainability.filter((e) => e.toLowerCase().includes('conflict'));
  const reasons = cluster.explainability.filter((e) => !e.toLowerCase().includes('conflict'));

  return (
    <div className="space-y-5">
      <div className="intel-card p-4">
        <p className="text-[10px] font-bold uppercase tracking-wider text-cyan-500">Why this match?</p>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">
          Cluster <span className="font-mono text-cyan-300">{cluster.account_cluster_id}</span> links{' '}
          <strong className="text-white">{cluster.linked_accounts.length}</strong> accounts with{' '}
          <strong className="text-white">{cluster.confidence_score.toFixed(1)}%</strong> confidence.
        </p>
        <div className="mt-3">
          <ConfidenceBar score={cluster.confidence_score} showLabel />
        </div>
      </div>

      <div>
        <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">Signal Analysis</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {cluster.evidence.map((ev) => (
            <div key={ev.type} className="intel-card p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-slate-200">
                  {SIGNAL_LABELS[ev.type] ?? ev.type}
                </span>
                <span className="font-mono text-lg font-bold text-white">{(ev.score * 100).toFixed(0)}%</span>
              </div>
              <ConfidenceBar score={ev.score * 100} />
              {ev.conflicting && <Badge variant="warn" className="mt-2">Conflict detected</Badge>}
              {ev.detail && <p className="mt-2 text-[10px] text-slate-500">{ev.detail}</p>}
            </div>
          ))}
        </div>
      </div>

      {reasons.length > 0 && (
        <div>
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">Link Reasoning</h3>
          <div className="space-y-2">
            {reasons.map((line, i) => (
              <div key={i} className="rounded-lg border-l-2 border-cyan-500/60 bg-slate-800/40 px-4 py-3 text-sm text-slate-300">
                {line}
              </div>
            ))}
          </div>
        </div>
      )}

      {conflicts.length > 0 && (
        <div>
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-amber-500">Conflict Explanations</h3>
          <div className="space-y-2">
            {conflicts.map((line, i) => (
              <div key={i} className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-4 py-3 text-sm text-amber-200/90">
                {line}
              </div>
            ))}
          </div>
        </div>
      )}

      {result.graph?.suspicious_networks && result.graph.suspicious_networks.length > 0 && (
        <div>
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-rose-400">Risk Indicators</h3>
          {result.graph.suspicious_networks.map((net) => (
            <div key={net.network_id} className="mb-2 intel-card border-rose-500/20 p-4">
              <p className="font-medium text-rose-300">{net.network_type.replace(/_/g, ' ')}</p>
              <ul className="mt-2 space-y-1 text-xs text-slate-400">
                {net.indicators.map((ind, i) => <li key={i}>• {ind}</li>)}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
