import { confidenceTier } from '../../lib/uiHelpers';

export function ConfidenceBar({ score, showLabel }: { score: number; showLabel?: boolean }) {
  const tier = confidenceTier(score);
  const color =
    tier === 'high' ? 'bg-emerald-500' : tier === 'medium' ? 'bg-amber-500' : 'bg-rose-500';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${Math.min(score, 100)}%` }}
        />
      </div>
      {showLabel && <span className="w-10 text-right font-mono text-xs text-slate-400">{score.toFixed(0)}%</span>}
    </div>
  );
}
