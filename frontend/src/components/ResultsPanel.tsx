import { useInvestigationStore } from '../store/investigationStore';

function ConfidenceBar({ score }: { score: number }) {
  const color = score >= 70 ? 'bg-green-500' : score >= 40 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="h-1.5 w-full rounded-full bg-slate-700">
      <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${Math.min(score, 100)}%` }} />
    </div>
  );
}

export function ResultsPanel() {
  const result = useInvestigationStore((s) => s.result);
  const selectedClusterId = useInvestigationStore((s) => s.selectedClusterId);
  const selectCluster = useInvestigationStore((s) => s.selectCluster);

  if (!result) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-500">
        Run an investigation to see unified accounts
      </div>
    );
  }

  const clusters = result.correlation?.clusters ?? [];
  const fusionScore = (result.fusion?.fusion_score ?? 0) * 100;
  const selected = clusters.find((c) => c.account_cluster_id === selectedClusterId) ?? clusters[0];
  const allWarnings = [...(result.warnings ?? []), ...(result.correlation?.warnings ?? [])];
  const signals = result.correlation?.signal_availability ?? {};

  return (
    <div className="space-y-4">
      {allWarnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-sm text-amber-200">
          {allWarnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Fusion Score" value={`${fusionScore.toFixed(1)}%`} />
        <Stat label="Clusters" value={String(result.correlation?.total_clusters ?? 0)} />
        <Stat label="Accounts" value={String(result.correlation?.total_accounts_analyzed ?? 0)} />
        <Stat label="Runtime" value={`${(result.total_execution_time_ms / 1000).toFixed(1)}s`} />
      </div>

      {(result.query_normalized || result.feature) && (
        <div className="flex flex-wrap gap-3 text-xs text-slate-500">
          <span>Feature: <strong className="text-slate-300">{result.feature}</strong></span>
          {result.query_normalized && (
            <span>Normalized: <strong className="font-mono text-slate-300">{result.query_normalized}</strong></span>
          )}
          <span>Tools: {result.tools_succeeded} ok / {result.tools_failed} failed</span>
        </div>
      )}

      {Object.keys(signals).length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase text-slate-400">Signal Availability</h3>
          <div className="flex flex-wrap gap-1">
            {Object.entries(signals).map(([sig, avail]) => (
              <span
                key={sig}
                className={`rounded px-2 py-0.5 text-xs ${avail ? 'bg-green-500/15 text-green-300' : 'bg-slate-800 text-slate-500'}`}
              >
                {sig.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        {clusters.map((cluster) => (
          <button
            key={cluster.account_cluster_id}
            onClick={() => selectCluster(cluster.account_cluster_id)}
            className={`w-full rounded-lg border p-3 text-left transition ${
              selected?.account_cluster_id === cluster.account_cluster_id
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-slate-700 bg-slate-800/50 hover:border-slate-600'
            }`}
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-xs text-slate-400">{cluster.account_cluster_id}</span>
              <span className="text-sm font-semibold text-slate-200">{cluster.confidence_score.toFixed(1)}%</span>
            </div>
            <ConfidenceBar score={cluster.confidence_score} />
            <div className="mt-2 flex flex-wrap gap-1">
              {(cluster.linked_account_refs ?? []).slice(0, 6).map((ref) => (
                <span key={ref} className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300">{ref}</span>
              ))}
              {(cluster.linked_account_refs?.length ?? 0) > 6 && (
                <span className="text-xs text-slate-500">+{cluster.linked_account_refs!.length - 6} more</span>
              )}
            </div>
          </button>
        ))}
      </div>

      {selected && (
        <div className="rounded-lg border border-slate-700 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Signal Breakdown</h3>
          <div className="space-y-2">
            {selected.evidence.map((ev) => (
              <div key={ev.type} className="flex items-center gap-3 text-sm">
                <span className="w-20 capitalize text-slate-400">{ev.type}</span>
                <div className="flex-1">
                  <ConfidenceBar score={ev.score * 100} />
                </div>
                <span className="w-12 text-right font-mono text-slate-300">{(ev.score * 100).toFixed(0)}%</span>
                {ev.conflicting && <span className="text-xs text-amber-400">conflict</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-800/80 px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold text-slate-100">{value}</div>
    </div>
  );
}
