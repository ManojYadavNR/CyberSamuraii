import { useInvestigationStore } from '../store/investigationStore';

const STATUS_ICON: Record<string, string> = {
  pending: '○',
  running: '◉',
  done: '✓',
  failed: '✗',
};

const STATUS_COLOR: Record<string, string> = {
  pending: 'text-slate-500',
  running: 'text-blue-400 animate-pulse',
  done: 'text-green-400',
  failed: 'text-red-400',
};

export function ProgressTracker() {
  const status = useInvestigationStore((s) => s.status);
  const toolProgress = useInvestigationStore((s) => s.toolProgress);
  const phase = useInvestigationStore((s) => s.phase);
  const queryType = useInvestigationStore((s) => s.queryType);

  if (status === 'idle') return null;

  const phases = ['tool', 'fusion', 'correlation', 'graph'];
  const phaseIndex = phases.indexOf(phase);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
      <div className="mb-3 flex items-center justify-between text-xs text-slate-400">
        <span>Live Progress · {queryType}</span>
        <span className="capitalize">{status}</span>
      </div>

      {toolProgress.length > 0 && (
        <div className="mb-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {toolProgress.map((t) => (
            <div key={t.tool} className="flex items-center gap-2 rounded-lg bg-slate-800/80 px-3 py-2 text-sm">
              <span className={STATUS_COLOR[t.status]}>{STATUS_ICON[t.status]}</span>
              <span className="flex-1 truncate font-mono text-slate-300">{t.tool}</span>
              {t.execution_time_ms != null && (
                <span className="text-xs text-slate-500">{(t.execution_time_ms / 1000).toFixed(1)}s</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-1">
        {['Tools', 'Fusion', 'Correlation', 'Graph'].map((label, i) => (
          <div
            key={label}
            className={`flex-1 rounded py-1 text-center text-xs ${
              phase === 'complete' || i <= phaseIndex
                ? 'bg-blue-600/30 text-blue-300'
                : 'bg-slate-800 text-slate-500'
            }`}
          >
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}
