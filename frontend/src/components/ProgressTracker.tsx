import { useInvestigationStore } from '../store/investigationStore';
import { toolEmptyLabel, toolLiveFindingsCount, toolScanStats, toolVerifiedFindingsCount } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';

const STATUS_BADGE = {
  pending: { label: 'Pending', variant: 'muted' as const },
  running: { label: 'Running', variant: 'info' as const },
  done: { label: 'Completed', variant: 'success' as const },
  failed: { label: 'Failed', variant: 'danger' as const },
};

export function ProgressTracker({ compact = false, technical = false }: { compact?: boolean; technical?: boolean }) {
  const status = useInvestigationStore((s) => s.status);
  const error = useInvestigationStore((s) => s.error);
  const investigationId = useInvestigationStore((s) => s.investigationId);
  const toolProgress = useInvestigationStore((s) => s.toolProgress);
  const phase = useInvestigationStore((s) => s.phase);
  const queryType = useInvestigationStore((s) => s.queryType);
  const investigationMode = useInvestigationStore((s) => s.investigationMode);
  const result = useInvestigationStore((s) => s.result);
  const liveFindings = useInvestigationStore((s) => s.liveFindings);
  const scanPhase = useInvestigationStore((s) => s.scanPhase);
  const sitesChecked = useInvestigationStore((s) => s.sitesChecked);
  const sitesTotal = useInvestigationStore((s) => s.sitesTotal);

  if (status === 'idle') return null;

  const phases = queryType === 'image'
    ? [
        { id: 'tool', label: 'Collection' },
        { id: 'image_intelligence', label: 'Image Intel' },
        { id: 'reverse_image_discovery', label: 'Reverse Search' },
        { id: 'fusion', label: 'Fusion' },
        { id: 'evidence_extraction', label: 'Extraction' },
        { id: 'correlation', label: 'Correlation' },
        { id: 'graph', label: 'Graph Intel' },
        { id: 'discovery', label: 'Discovery' },
      ]
    : [
        { id: 'multi_input', label: 'Multi-input' },
        { id: 'tool', label: 'Collection' },
        { id: 'fusion', label: 'Fusion' },
        { id: 'evidence_extraction', label: 'Extraction' },
        { id: 'correlation', label: 'Correlation' },
        { id: 'graph', label: 'Graph Intel' },
        { id: 'discovery', label: 'Discovery' },
      ];
  const INTERNAL_TOOLS = new Set([
    'pillow', 'exiftool', 'insightface', 'tesseract', 'easyocr', 'clip', 'imagehash',
  ]);

  const investigatorProgress = toolProgress.filter((t) => {
    if (technical) return true;
    return !INTERNAL_TOOLS.has(t.tool);
  });

  const showInternalTools = technical || toolProgress.some((t) => INTERNAL_TOOLS.has(t.tool));

  const investigatorPhases = queryType === 'image'
    ? [
        { id: 'tool', label: 'Discover' },
        { id: 'reverse_image_discovery', label: 'Search Web' },
        { id: 'fusion', label: 'Profile' },
        { id: 'discovery', label: 'Expand' },
        { id: 'correlation', label: 'Correlate' },
        { id: 'graph', label: 'Graph' },
      ]
    : [
        ...(queryType === 'phone' || queryType === 'infra'
          ? [{ id: 'tool', label: 'Collect' }]
          : [{ id: 'multi_input', label: 'Username+Email' }, { id: 'tool', label: 'Collect' }]),
        { id: 'fusion', label: 'Profile' },
        { id: 'discovery', label: 'Expand' },
        { id: 'correlation', label: 'Correlate' },
        { id: 'graph', label: 'Graph' },
      ];

  const activePhases = technical ? phases : investigatorPhases;
  const activePhaseIndex = activePhases.findIndex((p) => p.id === phase);

  if (compact && !technical && status !== 'running') return null;

  return (
    <div className={compact ? '' : 'intel-panel p-5'}>
      {!compact && (
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Live Investigation</h3>
          <p className="text-xs text-slate-500">
            Type: {queryType} · Mode: {
              investigationMode === 'samurai' ? 'Social (Samurai)'
              : investigationMode === 'fast' ? 'Quick'
              : investigationMode === 'deep' ? 'Deep'
              : 'Standard'
            }
            {sitesTotal > 0 ? ` · Sites ${sitesChecked}/${sitesTotal}` : ''} · Phase: {phase || 'initializing'}
          </p>
        </div>
        <Badge variant={status === 'running' ? 'info' : status === 'complete' ? 'success' : status === 'error' ? 'danger' : 'muted'}>
          {status === 'running' && error ? 'processing' : status}
        </Badge>
      </div>
      )}

      {!compact && error && status === 'error' && (
        <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
          {investigationId && status === 'error' && (
            <p className="mt-2 font-mono text-xs text-rose-300/80">
              Investigation ID: {investigationId}
            </p>
          )}
        </div>
      )}

      {status === 'running' && !error && (
        <p className="mb-3 text-xs text-cyan-300/90">
          {scanPhase === 1 && sitesTotal > 0
            ? `Phase 1 — priority sites scanning (live verified cards update below)…`
            : scanPhase === 2 && sitesTotal > 0
              ? `Phase 2 — full worldwide scan in progress…`
              : phase === 'discovery' || phase === 'hop_started' || phase === 'hop_completed'
            ? 'Expanding leads — investigating discovered usernames, emails, domains, and profiles…'
            : queryType === 'image' && (phase === 'tool' || phase === 'image_intelligence')
              ? 'Discovering entities from your photo (face, text, metadata)…'
              : queryType === 'image' && phase === 'reverse_image_discovery'
                ? 'Searching the public web for matching profiles and accounts…'
                : phase === 'evidence_extraction'
                  ? 'Building person profile from discovered intelligence…'
                  : 'Investigating person — entities become leads automatically'}
        </p>
      )}

      {liveFindings.length > 0 && status === 'running' && (
        <div className="mb-4 max-h-56 overflow-y-auto rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-cyan-400">
            Live discoveries ({liveFindings.length})
          </p>
          <ul className="flex flex-col gap-2">
            {[...liveFindings].reverse().slice(0, 12).map((f) => (
              <li
                key={f.id}
                className="flex flex-col gap-1 rounded-md border border-cyan-500/10 bg-slate-900/50 px-2.5 py-2"
              >
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-cyan-400">{f.type}</span>
                  {f.source ? (
                    <span className="text-[10px] text-slate-500">· {f.source}</span>
                  ) : null}
                </div>
                <p className="break-words text-xs leading-relaxed text-slate-200">{f.value}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {investigatorProgress.length > 0 && (
        <div className="mb-4 grid gap-2 sm:grid-cols-2">
          {investigatorProgress.map((t) => {
            const findings = toolLiveFindingsCount(result, t.tool, t.detail);
            const verified = result ? toolVerifiedFindingsCount(result, t.tool) : 0;
            const scan = result ? toolScanStats(result, t.tool) : null;
            const badge = STATUS_BADGE[t.status] ?? STATUS_BADGE.pending;
            const isActive = t.status === 'running';
            const isDone = t.status === 'done';
            const isFailed = t.status === 'failed';
            const label = t.tool === 'reverse_image_search'
              ? 'Reverse image search'
              : t.tool === 'image_intelligence'
                ? 'Entity extraction'
                : t.tool.startsWith('hop:')
                  ? `Investigating → ${t.tool.slice(4)}`
                  : INTERNAL_TOOLS.has(t.tool)
                    ? t.tool
                    : t.tool;
            return (
              <div
                key={t.tool}
                className={`flex items-start gap-3 rounded-lg border px-4 py-3 transition ${
                  isActive ? 'border-cyan-500/30 bg-cyan-500/5' :
                  isDone ? 'border-emerald-500/20 bg-emerald-500/5' :
                  isFailed ? 'border-rose-500/20 bg-rose-500/5' :
                  'border-slate-700/50 bg-slate-800/30'
                }`}
              >
                <span className="mt-0.5 text-lg">
                  {isDone ? '✓' : isFailed ? '✗' : isActive ? '◉' : '○'}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-slate-200">{label}</span>
                    <Badge variant={badge.variant}>{badge.label}</Badge>
                  </div>
                  {t.detail && (
                    <p className="mt-1 text-xs text-slate-400">{t.detail}</p>
                  )}
                  {t.status === 'done' && (
                    <div className="mt-1 space-y-0.5">
                      {scan && scan.sitesChecked > 0 && (
                        <p className="text-xs text-slate-400">
                          {scan.sitesChecked.toLocaleString()} sites checked · {findings} hit{findings === 1 ? '' : 's'}
                          {verified > 0 && verified < findings ? ` · ${verified} verified` : ''}
                        </p>
                      )}
                      {!scan && findings > 0 && (
                        <p className="text-xs text-emerald-400/90">{findings} finding(s)</p>
                      )}
                      {!scan && findings === 0 && !t.error && (
                        <p className="text-xs text-slate-400">{toolEmptyLabel(t.tool)}</p>
                      )}
                      {scan?.note && (
                        <p className="text-[10px] text-slate-500">{scan.note}</p>
                      )}
                    </div>
                  )}
                  {t.execution_time_ms != null && t.status === 'done' && showInternalTools && (
                    <p className="mt-0.5 font-mono text-[10px] text-slate-500">{(t.execution_time_ms / 1000).toFixed(1)}s</p>
                  )}
                  {t.error && <p className="mt-1 text-xs text-rose-400">{t.error}</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex gap-1">
        {activePhases.map((p, i) => {
          const active = phase === 'complete' || phase === 'finished' || i <= activePhaseIndex;
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
