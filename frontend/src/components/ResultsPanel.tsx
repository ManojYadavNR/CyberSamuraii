import { useInvestigationStore } from '../store/investigationStore';
import { flattenAccounts, confidenceTier, tierLabel, tierClasses } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';
import { ConfidenceBar } from './ui/ConfidenceBar';
import { EmptyState } from './ui/EmptyState';

export function ResultsPanel() {
  const result = useInvestigationStore((s) => s.result);
  const openEntityDrawer = useInvestigationStore((s) => s.openEntityDrawer);
  const accounts = flattenAccounts(result);

  if (!result) {
    return (
      <EmptyState
        icon="🔍"
        title="No accounts discovered"
        description="Start an investigation to discover linked accounts across platforms. Results appear as intelligence cards with confidence scoring."
      />
    );
  }

  const allWarnings = [...(result.warnings ?? []), ...(result.correlation?.warnings ?? [])];

  return (
    <div className="space-y-4">
      {allWarnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-4 py-3 text-sm text-amber-200/90">
          {allWarnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">
          <span className="font-semibold text-white">{accounts.length}</span> account intelligence cards
        </p>
        {result.correlation?.signal_availability && (
          <div className="flex flex-wrap gap-1">
            {Object.entries(result.correlation.signal_availability).slice(0, 4).map(([k, v]) => (
              <span key={k} className={`rounded px-1.5 py-0.5 text-[9px] ${v ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-800 text-slate-600'}`}>
                {k.split('_')[0]}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {accounts.map((acct) => {
          const tier = confidenceTier(acct.confidence);
          return (
            <button
              key={acct.id}
              type="button"
              onClick={() => openEntityDrawer(acct.id)}
              className="intel-card group p-4 text-left transition hover:border-cyan-500/30 hover:shadow-cyan-900/10"
            >
              <div className="mb-3 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-mono text-sm font-semibold text-white group-hover:text-cyan-200">
                    {acct.handle}
                  </p>
                  <p className="truncate text-xs text-slate-500">{acct.platform}</p>
                </div>
                <span className={`shrink-0 rounded border px-2 py-0.5 text-[9px] font-bold ${tierClasses(tier)}`}>
                  {tierLabel(tier).split(' ')[0]}
                </span>
              </div>

              <ConfidenceBar score={acct.confidence} showLabel />

              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <Badge variant={acct.verified ? 'success' : 'muted'}>{acct.verified ? 'Verified' : 'Unverified'}</Badge>
                <Badge variant="info">{acct.evidenceCount} evidence</Badge>
                {acct.sources.slice(0, 2).map((s) => (
                  <Badge key={s} variant="muted">{s}</Badge>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      {accounts.length === 0 && (
        <EmptyState icon="📭" title="No linked accounts" description="Tools completed but no account entities were correlated." />
      )}
    </div>
  );
}
