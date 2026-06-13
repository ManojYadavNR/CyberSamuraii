import { useState } from 'react';
import { runCorrelate } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';

export function EvidencePanel() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const updateResult = useInvestigationStore((s) => s.updateResult);
  const [section, setSection] = useState<'entities' | 'tools' | 'email' | 'provenance'>('entities');
  const [reloading, setReloading] = useState(false);

  if (!result) {
    return <div className="flex h-64 items-center justify-center text-sm text-slate-500">Evidence appears after investigation</div>;
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
            className={`rounded px-3 py-1 text-xs ${section === s.id ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
          >
            {s.label}
          </button>
        ))}
        <button
          onClick={handleRecorrelate}
          disabled={reloading || !entities.length}
          className="ml-auto rounded border border-slate-600 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
          title="POST /api/intel/correlate"
        >
          {reloading ? 'Re-correlating…' : 'Re-correlate'}
        </button>
      </div>

      {section === 'entities' && (
        <div className="max-h-96 space-y-2 overflow-y-auto">
          {entities.map((ent) => (
            <div key={ent.entity_id ?? ent.value} className="rounded-lg border border-slate-700 bg-slate-800/40 p-3 text-sm">
              <div className="flex justify-between">
                <span className="font-mono text-blue-300">{ent.canonical_value || ent.value}</span>
                <span className="text-xs text-slate-500">{ent.type}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-400">
                {ent.entity_id && <span>ID: {ent.entity_id.slice(0, 8)}…</span>}
                <span>Fusion: {((ent.fusion_score ?? 0) * 100).toFixed(0)}%</span>
                <span>Sources: {(ent.sources ?? []).join(', ')}</span>
              </div>
              {ent.aliases && ent.aliases.length > 0 && (
                <div className="mt-1 text-xs text-slate-500">Aliases: {ent.aliases.join(', ')}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {section === 'tools' && (
        <div className="max-h-96 space-y-3 overflow-y-auto">
          {result.tool_results.map((tr) => (
            <div key={tr.tool} className="rounded-lg border border-slate-700 p-3 text-sm">
              <div className="flex justify-between">
                <span className="font-mono text-slate-200">{tr.tool}</span>
                <span className={tr.success ? 'text-green-400' : 'text-red-400'}>{tr.success ? 'OK' : 'FAIL'}</span>
              </div>
              {tr.error && <p className="mt-1 text-xs text-red-400">{tr.error}</p>}
              {(tr.data ?? []).length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs text-slate-400">{tr.data!.length} raw hit(s)</summary>
                  <pre className="mt-1 max-h-32 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-400">
                    {JSON.stringify(tr.data, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))}
          {result.merged_results && result.merged_results.length > 0 && (
            <div>
              <h4 className="mb-1 text-xs font-semibold text-slate-400">Merged Results</h4>
              <pre className="max-h-40 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-400">
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
            <div className="rounded-lg border border-slate-700 p-3">
              <h4 className="text-xs font-semibold text-slate-400">Scan Summary</h4>
              <pre className="mt-1 text-xs text-slate-300">{JSON.stringify(result.scan_summary, null, 2)}</pre>
            </div>
          )}
        </div>
      )}

      {section === 'provenance' && (
        <div className="max-h-96 overflow-y-auto">
          <pre className="rounded bg-slate-900 p-3 text-xs text-slate-400">
            {JSON.stringify(evidenceMap, null, 2)}
          </pre>
          {result.fusion?.raw_evidence_index && (
            <div className="mt-3">
              <h4 className="text-xs font-semibold text-slate-400">Raw Evidence Index</h4>
              <pre className="mt-1 rounded bg-slate-900 p-2 text-xs text-slate-500">
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
  const border = color === 'green' ? 'border-green-500/30' : color === 'amber' ? 'border-amber-500/30' : 'border-blue-500/30';
  if (!items.length) return null;
  return (
    <div className={`rounded-lg border ${border} p-3`}>
      <h4 className="text-xs font-semibold text-slate-400">{title} ({items.length})</h4>
      <div className="mt-2 space-y-2">
        {items.map((item, i) => (
          <pre key={i} className="rounded bg-slate-900 p-2 text-xs text-slate-300">{JSON.stringify(item, null, 2)}</pre>
        ))}
      </div>
    </div>
  );
}
