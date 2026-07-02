import { useInvestigationStore } from '../store/investigationStore';
import { investigationSummary } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';

export function InvestigationSummary() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const queryType = useInvestigationStore((s) => s.queryType);
  const status = useInvestigationStore((s) => s.status);
  const investigationId = useInvestigationStore((s) => s.investigationId);

  if (status !== 'complete' || !result) return null;

  const s = investigationSummary(result, query, queryType);

  const stats = [
    { label: 'Accounts Found', value: String(s.accountsFound), accent: 'text-cyan-300' },
    { label: 'Identity Confidence', value: `${s.identityConfidence.toFixed(0)}%`, accent: 'text-violet-300' },
    { label: 'Fields Extracted', value: String(result?.evidence_extraction?.fields_extracted ?? 0), accent: 'text-fuchsia-300' },
    { label: 'Entities Enriched', value: String(s.entitiesEnriched), accent: 'text-emerald-300' },
    { label: 'Discovery Hops', value: String(result?.discovery?.total_hops ?? 0), accent: 'text-violet-300' },
    { label: 'Reasoning Paths', value: String(s.reasoningPaths), accent: 'text-cyan-300' },
    { label: 'Fusion Score', value: `${s.fusionScore.toFixed(0)}%`, accent: 'text-emerald-300' },
    { label: 'Clusters', value: String(s.clusters), accent: 'text-blue-300' },
    { label: 'Runtime', value: `${s.runtime.toFixed(0)}s`, accent: 'text-slate-300' },
  ];

  return (
    <div className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-gradient-to-r from-cyan-950/40 to-blue-950/30 px-5 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-500/80">Investigation Summary</p>
            <h2 className="mt-1 font-mono text-lg font-semibold text-white">{s.target}</h2>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="info">{s.type}</Badge>
            <Badge variant="success">Complete</Badge>
            {investigationId && (
              <span className="font-mono text-[10px] text-slate-600">ID {investigationId.slice(0, 8)}…</span>
            )}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-px bg-slate-800/50 sm:grid-cols-3 lg:grid-cols-6">
        {stats.map((st) => (
          <div key={st.label} className="bg-slate-900/80 px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">{st.label}</p>
            <p className={`mt-1 text-xl font-bold tabular-nums ${st.accent}`}>{st.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
