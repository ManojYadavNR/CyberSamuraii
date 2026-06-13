import { useInvestigationStore } from '../store/investigationStore';
import { toolFindingsCount } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';

const STATUS_BADGE = {
  pending: { label: 'Pending', variant: 'muted' as const },
  running: { label: 'Running', variant: 'info' as const },
  done: { label: 'Completed', variant: 'success' as const },
  failed: { label: 'Failed', variant: 'danger' as const },
};

export function ProgressTracker() {
  const status = useInvestigationStore((s) => s.status);
  const toolProgress = useInvestigationStore((s) => s.toolProgress);
  const phase = useInvestigationStore((s) => s.phase);
  const queryType = useInvestigationStore((s) => s.queryType);
  const result = useInvestigationStore((s) => s.result);

  if (status === 'idle') return null;

  const phases = [
    { id: 'tool', label: 'Collection' },
    { id: 'fusion', label: 'Fusion' },
    { id: 'correlation', label: 'Correlation' },
    { id: 'graph', label: 'Graph Intel' },
  ];
  const phaseIndex = phases.findIndex((p) => p.id === phase);

  return (
    <div className="intel-panel p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Live Investigation</h3>
          <p className="text-xs text-slate-500">Type: {queryType} · Phase: {phase || 'initializing'}</p>
        </div>
        <Badge variant={status === 'running' ? 'info' : status === 'complete' ? 'success' : status === 'error' ? 'danger' : 'muted'}>
          {status}
        </Badge>
      </div>

      {toolProgress.length > 0 && (
        <div className="mb-4 grid gap-2 sm:grid-cols-2">
          {toolProgress.map((t) => {
            const findings = result ? toolFindingsCount(result, t.tool) : 0;
            const badge = STATUS_BADGE[t.status];
            return (
              <div
                key={t.tool}
                className={`flex items-start gap-3 rounded-lg border px-4 py-3 transition ${
                  t.status === 'running' ? 'border-cyan-500/30 bg-cyan-500/5' :
                  t.status === 'done' ? 'border-emerald-500/20 bg-emerald-500/5' :
                  t.status === 'failed' ? 'border-rose-500/20 bg-rose-500/5' :
                  'border-slate-700/50 bg-slate-800/30'
                }`}
              >
                <span className="mt-0.5 text-lg">
                  {t.status === 'done' ? '✓' : t.status === 'failed' ? '✗' : t.status === 'running' ? '◉' : '○'}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-sm font-medium text-slate-200">{t.tool}</span>
                    <Badge variant={badge.variant}>{badge.label}</Badge>
                  </div>
                  {t.status === 'done' && findings > 0 && (
                    <p className="mt-1 text-xs text-emerald-400/90">{findings} account(s) / finding(s)</p>
                  )}
                  {t.execution_time_ms != null && t.status === 'done' && (
                    <p className="mt-0.5 font-mono text-[10px] text-slate-500">{(t.execution_time_ms / 1000).toFixed(1)}s runtime</p>
                  )}
                  {t.error && <p className="mt-1 text-xs text-rose-400">{t.error}</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex gap-1">
        {phases.map((p, i) => {
          const active = phase === 'complete' || phase === 'finished' || i <= phaseIndex;
          return (
            <div
              key={p.id}
              className={`flex-1 rounded-md py-2 text-center text-[10px] font-semibold uppercase tracking-wider transition ${
                active ? 'bg-cyan-500/20 text-cyan-300' : 'bg-slate-800/50 text-slate-600'
              }`}
            >
              {p.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}
