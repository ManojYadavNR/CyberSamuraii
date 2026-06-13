import { useState } from 'react';
import { exportReport } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';

export function ExportPanel() {
  const investigationId = useInvestigationStore((s) => s.investigationId);
  const query = useInvestigationStore((s) => s.query);
  const result = useInvestigationStore((s) => s.result);
  const reviews = useInvestigationStore((s) => s.reviews);
  const [hash, setHash] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleExport = async () => {
    if (!investigationId || !result) return;
    setLoading(true);
    try {
      const report = await exportReport({
        investigation_id: investigationId,
        query,
        result: result as unknown as Record<string, unknown>,
        reviewer: 'CID Investigator',
      });
      setHash(report.integrity_hash);

      const blob = new Blob([report.html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `socmint-report-${investigationId.slice(0, 8)}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert('Export failed');
    } finally {
      setLoading(false);
    }
  };

  if (!result) {
    return <div className="text-sm text-slate-500">Complete an investigation to export evidence</div>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        Generate a court-ready HTML report with SHA-256 integrity hash. Print to PDF from your browser.
      </p>

      <div className="rounded-lg bg-slate-800/60 p-3 text-sm">
        <div className="text-slate-500">Report will include:</div>
        <ul className="mt-2 list-inside list-disc text-slate-300">
          <li>Tool execution log with timestamps</li>
          <li>Identity correlation clusters + explainability</li>
          <li>{reviews.length} human review decision(s)</li>
          <li>SHA-256 evidence integrity hash</li>
        </ul>
      </div>

      <button
        onClick={handleExport}
        disabled={loading}
        className="w-full rounded-lg bg-slate-100 px-4 py-2.5 text-sm font-medium text-slate-900 hover:bg-white disabled:opacity-40"
      >
        {loading ? 'Generating…' : 'Download Court-Ready Report'}
      </button>

      {hash && (
        <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-3">
          <div className="text-xs font-semibold text-green-400">Evidence Integrity Hash (SHA-256)</div>
          <code className="mt-1 block break-all text-xs text-slate-300">{hash}</code>
        </div>
      )}
    </div>
  );
}
