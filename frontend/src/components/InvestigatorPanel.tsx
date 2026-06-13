import { useInvestigationStore } from '../store/investigationStore';

export function InvestigatorPanel() {
  const result = useInvestigationStore((s) => s.result);
  const selectedClusterId = useInvestigationStore((s) => s.selectedClusterId);

  if (!result) {
    return <div className="text-sm text-slate-500">Select a cluster to see AI reasoning</div>;
  }

  const cluster = result.correlation?.clusters?.find((c) => c.account_cluster_id === selectedClusterId)
    ?? result.correlation?.clusters?.[0];

  if (!cluster) {
    return <div className="text-sm text-slate-500">No correlation data available</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Why this match?</h3>
        <p className="text-sm text-slate-300">
          Cluster <span className="font-mono text-blue-300">{cluster.account_cluster_id}</span> linked with{' '}
          <strong>{cluster.confidence_score.toFixed(1)}%</strong> confidence across{' '}
          {cluster.linked_accounts.length} account(s).
        </p>
      </div>

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Explainability</h3>
        {cluster.explainability.length === 0 ? (
          <p className="text-sm text-slate-500">No explainability lines generated</p>
        ) : (
          <ul className="space-y-2">
            {cluster.explainability.map((line, i) => (
              <li key={i} className="rounded-lg border-l-2 border-blue-500 bg-slate-800/60 px-3 py-2 text-sm text-slate-300">
                {line}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence Scores</h3>
        <div className="space-y-1">
          {cluster.evidence.map((ev) => (
            <div key={ev.type} className="flex justify-between rounded bg-slate-800/50 px-3 py-1.5 text-sm">
              <span className="capitalize text-slate-400">{ev.type}</span>
              <span className="font-mono text-slate-200">
                score {(ev.score * 100).toFixed(0)}% · weight {(ev.weight * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {result.graph?.suspicious_networks && result.graph.suspicious_networks.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-400">Suspicious Indicators</h3>
          {result.graph.suspicious_networks.map((net) => (
            <div key={net.network_id} className="mb-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm">
              <div className="font-medium text-red-300">{net.network_type.replace(/_/g, ' ')}</div>
              <ul className="mt-1 list-inside list-disc text-slate-400">
                {net.indicators.map((ind, i) => <li key={i}>{ind}</li>)}
              </ul>
            </div>
          ))}
        </div>
      )}

      {result.correlation?.correlation_engine_version && (
        <p className="text-xs text-slate-600">Correlation engine v{result.correlation.correlation_engine_version}</p>
      )}

      {result.confidence_raw_inputs && result.confidence_raw_inputs.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs text-slate-400">Confidence raw inputs ({result.confidence_raw_inputs.length})</summary>
          <pre className="mt-2 max-h-32 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-500">
            {JSON.stringify(result.confidence_raw_inputs, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
