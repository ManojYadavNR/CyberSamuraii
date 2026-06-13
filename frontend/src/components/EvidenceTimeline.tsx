import { useInvestigationStore } from '../store/investigationStore';
import { buildTimeline } from '../lib/uiHelpers';

export function EvidenceTimeline() {
  const result = useInvestigationStore((s) => s.result);
  const toolProgress = useInvestigationStore((s) => s.toolProgress);
  const phase = useInvestigationStore((s) => s.phase);
  const status = useInvestigationStore((s) => s.status);

  if (status === 'idle') return null;

  const events = buildTimeline(result, toolProgress, phase, status);

  return (
    <div className="intel-panel p-4">
      <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">Investigation Timeline</h3>
      <div className="relative space-y-0">
        {events.map((ev, i) => (
          <div key={ev.id} className="relative flex gap-4 pb-4 last:pb-0">
            {i < events.length - 1 && (
              <div className="absolute left-[11px] top-6 h-full w-px bg-slate-700/80" />
            )}
            <div
              className={`relative z-10 mt-1 h-[22px] w-[22px] shrink-0 rounded-full border-2 flex items-center justify-center text-[10px] ${
                ev.status === 'done' ? 'border-emerald-500 bg-emerald-500/20 text-emerald-400' :
                ev.status === 'failed' ? 'border-rose-500 bg-rose-500/20 text-rose-400' :
                'border-cyan-500 bg-cyan-500/20 text-cyan-400 animate-pulse-glow'
              }`}
            >
              {ev.status === 'done' ? '✓' : ev.status === 'failed' ? '!' : '…'}
            </div>
            <div className="min-w-0 flex-1 pt-0.5">
              <p className="text-sm text-slate-200">{ev.label}</p>
              {ev.detail && <p className="mt-0.5 text-xs text-slate-500">{ev.detail}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
