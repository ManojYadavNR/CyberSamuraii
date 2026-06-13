import { useState } from 'react';
import { runCorrelate } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

export function EvidencePanel() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const updateResult = useInvestigationStore((s) => s.updateResult);
  const [section, setSection] = useState<'entities' | 'tools' | 'email' | 'provenance'>('entities');
  const [reloading, setReloading] = useState(false);

  if (!result) {
    return <EmptyState icon="📁" title="Evidence vault" description="Fusion entities, tool hits, and provenance appear after investigation completes." />;
  }

  const entities = result.fusion?.deduplicated_entities ?? [];
  const evidenceMap = result.fusion?.evidence_map ?? {};
  const isEmail = result.feature === 'email_intel';

  const handleRecorrelate = async () => {
    setReloading(true);
    try {
      const correlation = await runCorrelate(
        query,
        entities.map((e) => ({ ...e } as Record<string, unknown>)),
      );
      updateResult({ correlation });
    } catch {
      alert('Re-correlation failed');
    } finally {
      setReloading(false);
    }
  };

  const sections = [
    { id: 'entities' as const, label: `Entities (${entities.length})` },
    { id: 'tools' as const, label: `Tool Hits (${result.tool_results.length})` },
    ...(isEmail ? [{ id: 'email' as const, label: 'Email Intel' }] : []),
    { id: 'provenance' as const, label: 'Provenance' },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {sections.map((s) => (
          <button
            key={s.id}
            onClick={() => setSection(s.id)}
            className={`rounded-md px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider transition ${
              section === s.id ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' : 'bg-slate-800/50 text-slate-500 border border-transparent hover:text-slate-300'
            }`}
          >
            {s.label}
          </button>
        ))}
        <button
          onClick={handleRecorrelate}
          disabled={reloading || !entities.length}
          className="intel-btn-ghost ml-auto text-xs disabled:opacity-40"
        >
          {reloading ? 'Re-correlating…' : 'Re-correlate'}
        </button>
      </div>

      {section === 'entities' && (
        <div className="max-h-[480px] space-y-2 overflow-y-auto">
          {entities.map((ent) => (
            <div key={ent.entity_id ?? ent.value} className="intel-card p-4 text-sm">
              <div className="flex justify-between gap-3">
                <span className="font-mono text-cyan-300">{ent.canonical_value || ent.value}</span>
                <Badge variant="muted">{ent.type}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
                {ent.entity_id && <span className="font-mono">ID: {ent.entity_id.slice(0, 8)}…</span>}
                <span>Fusion: {((ent.fusion_score ?? 0) * 100).toFixed(0)}%</span>
                <span>Sources: {(ent.sources ?? []).join(', ') || '—'}</span>
              </div>
              {ent.aliases && ent.aliases.length > 0 && (
                <div className="mt-2 text-xs text-slate-500">Aliases: {ent.aliases.join(', ')}</div>
              )}
            </div>
          ))}
          {!entities.length && <p className="py-8 text-center text-sm text-slate-500">No fused entities</p>}
        </div>
      )}

      {section === 'tools' && (
        <div className="max-h-[480px] space-y-3 overflow-y-auto">
          {result.tool_results.map((tr) => (
            <div key={tr.tool} className="intel-card p-4 text-sm">
              <div className="flex justify-between">
                <span className="font-mono font-medium text-slate-200">{tr.tool}</span>
                <Badge variant={tr.success ? 'success' : 'danger'}>{tr.success ? 'OK' : 'FAIL'}</Badge>
              </div>
              {tr.error && <p className="mt-2 text-xs text-rose-400">{tr.error}</p>}
              {(tr.data ?? []).length > 0 && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-slate-400">{tr.data!.length} raw hit(s)</summary>
                  <pre className="mt-2 max-h-32 overflow-auto rounded-lg bg-slate-900/80 p-3 font-mono text-xs text-slate-400">
                    {JSON.stringify(tr.data, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))}
          {result.merged_results && result.merged_results.length > 0 && (
            <div className="intel-card p-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Merged Results</h4>
              <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-900/80 p-3 font-mono text-xs text-slate-400">
                {JSON.stringify(result.merged_results, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {section === 'email' && isEmail && (
        <div className="space-y-3">
          <EmailSection title="Confirmed Findings" items={result.confirmed_findings ?? []} color="green" />
          <EmailSection title="Public Profiles" items={result.public_profile_data ?? []} color="blue" />
          <EmailSection title="Investigation Leads" items={result.investigation_leads ?? []} color="amber" />
          {result.scan_summary && (
            <div className="intel-card p-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Scan Summary</h4>
              <pre className="mt-2 font-mono text-xs text-slate-300">{JSON.stringify(result.scan_summary, null, 2)}</pre>
            </div>
          )}
        </div>
      )}

      {section === 'provenance' && (
        <div className="max-h-[480px] overflow-y-auto">
          <pre className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 font-mono text-xs text-slate-400">
            {JSON.stringify(evidenceMap, null, 2)}
          </pre>
          {result.fusion?.raw_evidence_index && (
            <div className="mt-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Raw Evidence Index</h4>
              <pre className="mt-2 rounded-xl border border-slate-800 bg-slate-900/60 p-3 font-mono text-xs text-slate-500">
                {JSON.stringify(result.fusion.raw_evidence_index, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EmailSection({ title, items, color }: { title: string; items: Record<string, unknown>[]; color: string }) {
  const border = color === 'green' ? 'border-emerald-500/30' : color === 'amber' ? 'border-amber-500/30' : 'border-cyan-500/30';
  if (!items.length) return null;
  return (
    <div className={`intel-card border ${border} p-4`}>
      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">{title} ({items.length})</h4>
      <div className="mt-3 space-y-2">
        {items.map((item, i) => (
          <pre key={i} className="rounded-lg bg-slate-900/80 p-3 font-mono text-xs text-slate-300">{JSON.stringify(item, null, 2)}</pre>
        ))}
      </div>
    </div>
  );
}
