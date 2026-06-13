import { useState } from 'react';
import { exportReport } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';
import { investigationSummary } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

export function ExportPanel() {
  const investigationId = useInvestigationStore((s) => s.investigationId);
  const query = useInvestigationStore((s) => s.query);
  const queryType = useInvestigationStore((s) => s.queryType);
  const result = useInvestigationStore((s) => s.result);
  const reviews = useInvestigationStore((s) => s.reviews);
  const [hash, setHash] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [format, setFormat] = useState<'pdf' | 'json' | 'csv'>('pdf');

  const handleExport = async () => {
    if (!investigationId || !result) return;
    setLoading(true);
    try {
      if (format === 'json') {
        const blob = new Blob([JSON.stringify({ investigation_id: investigationId, query, result, reviews }, null, 2)], { type: 'application/json' });
        download(blob, `socmint-${investigationId.slice(0, 8)}.json`);
        setLoading(false);
        return;
      }
      if (format === 'csv') {
        const accounts = result.correlation?.clusters?.flatMap((c) =>
          c.linked_account_refs.map((ref) => `${ref},${c.confidence_score},${c.account_cluster_id}`),
        ) ?? [];
        const csv = 'account_ref,confidence,cluster_id\n' + accounts.join('\n');
        download(new Blob([csv], { type: 'text/csv' }), `socmint-${investigationId.slice(0, 8)}.csv`);
        setLoading(false);
        return;
      }

      const report = await exportReport({
        investigation_id: investigationId,
        query,
        result: result as unknown as Record<string, unknown>,
        reviewer: 'CID Investigator',
      });
      setHash(report.integrity_hash);
      download(new Blob([report.html], { type: 'text/html' }), `socmint-report-${investigationId.slice(0, 8)}.html`);
    } catch {
      alert('Export failed');
    } finally {
      setLoading(false);
    }
  };

  if (!result) {
    return <EmptyState icon="📄" title="Export evidence" description="Generate court-ready reports after investigation completes." />;
  }

  const summary = investigationSummary(result, query, queryType);

  return (
    <div className="space-y-5">
      <div className="intel-card p-5">
        <p className="text-[10px] font-bold uppercase tracking-wider text-cyan-500">Export Summary</p>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MiniStat label="Target" value={summary.target} />
          <MiniStat label="Accounts" value={String(summary.accountsFound)} />
          <MiniStat label="Clusters" value={String(summary.clusters)} />
          <MiniStat label="Reviews" value={String(reviews.length)} />
        </div>
      </div>

      <div>
        <p className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">Export Format</p>
        <div className="grid grid-cols-3 gap-3">
          {(['pdf', 'json', 'csv'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFormat(f)}
              className={`intel-card p-4 text-center transition ${
                format === f ? 'border-cyan-500/40 bg-cyan-500/10' : 'hover:border-slate-600'
              }`}
            >
              <p className="text-2xl">{f === 'pdf' ? '📑' : f === 'json' ? '{ }' : '📊'}</p>
              <p className="mt-2 text-sm font-semibold uppercase text-slate-300">{f}</p>
              <p className="mt-1 text-[10px] text-slate-500">
                {f === 'pdf' ? 'Court-ready HTML/PDF' : f === 'json' ? 'Full case data' : 'Account list'}
              </p>
            </button>
          ))}
        </div>
      </div>

      <button onClick={handleExport} disabled={loading} className="intel-btn-primary w-full py-3">
        {loading ? 'Generating export…' : `Export ${format.toUpperCase()} Report`}
      </button>

      {hash && format === 'pdf' && (
        <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-4">
          <div className="flex items-center gap-2">
            <Badge variant="success">SHA-256 Verified</Badge>
          </div>
          <code className="mt-2 block break-all font-mono text-[10px] text-slate-400">{hash}</code>
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase text-slate-500">{label}</p>
      <p className="mt-1 truncate font-mono text-sm font-semibold text-white">{value}</p>
    </div>
  );
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
