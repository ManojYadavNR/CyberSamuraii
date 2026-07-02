import { useInvestigationStore } from '../store/investigationStore';
import { flattenAccounts, flattenProbeCandidates, confidenceTier, tierLabel, tierClasses } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';
import { ConfidenceBar } from './ui/ConfidenceBar';
import { EmptyState } from './ui/EmptyState';

export function ResultsPanel() {
  const result = useInvestigationStore((s) => s.result);
  const openEntityDrawer = useInvestigationStore((s) => s.openEntityDrawer);
  const accounts = flattenAccounts(result);
  const probes = flattenProbeCandidates(result);

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
                <div className="flex min-w-0 items-start gap-3">
                  {acct.avatarUrl && (
                    <img
                      src={acct.avatarUrl}
                      alt={acct.displayName || acct.handle}
                      className="h-12 w-12 shrink-0 rounded-lg border border-slate-700 object-cover bg-slate-900"
                      loading="lazy"
                      referrerPolicy="no-referrer"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  )}
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm font-semibold text-white group-hover:text-cyan-200">
                      {acct.displayName || acct.handle}
                    </p>
                    <p className="truncate text-xs text-slate-500">{acct.platform}</p>
                  {acct.bio && (
                    <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-slate-400">{acct.bio}</p>
                  )}
                  {acct.location && (
                    <p className="mt-0.5 text-[10px] text-slate-600">📍 {acct.location}</p>
                  )}
                  </div>
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

      {accounts.length === 0 && probes.length === 0 && (
        <EmptyState icon="📭" title="No linked accounts" description="Tools completed but no verified account entities were found. Unverified probe hits may appear below." />
      )}

      {probes.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-slate-400">
            <span className="font-semibold text-amber-200">{probes.length}</span> unverified probe hit(s) — pending live verification
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {probes.slice(0, 12).map((probe) => (
              <div key={probe.id} className="rounded-lg border border-slate-700/60 bg-slate-900/40 px-3 py-2 text-left">
                <p className="truncate font-mono text-xs text-slate-300">{probe.handle}</p>
                <p className="truncate text-[10px] text-slate-500">{probe.platform}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  <Badge variant="muted">Probe</Badge>
                  {probe.sources.slice(0, 2).map((s) => (
                    <Badge key={s} variant="muted">{s}</Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
