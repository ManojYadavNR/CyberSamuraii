import { useEffect, useState } from 'react';
import { fetchReviews, submitReview } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';
import { ConfidenceBar } from './ui/ConfidenceBar';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

export function ReviewPanel() {
  const investigationId = useInvestigationStore((s) => s.investigationId);
  const selectedClusterId = useInvestigationStore((s) => s.selectedClusterId);
  const result = useInvestigationStore((s) => s.result);
  const reviews = useInvestigationStore((s) => s.reviews);
  const addReview = useInvestigationStore((s) => s.addReview);
  const setReviews = useInvestigationStore((s) => s.setReviews);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  const cluster = result?.correlation?.clusters?.find((c) => c.account_cluster_id === selectedClusterId);

  useEffect(() => {
    if (!investigationId) return;
    fetchReviews(investigationId).then((d) => setReviews(d.reviews)).catch(() => {});
  }, [investigationId, setReviews]);

  const handleReview = async (decision: 'approve' | 'reject' | 'suspicious') => {
    if (!investigationId || !selectedClusterId) return;
    setLoading(true);
    try {
      const record = await submitReview({
        investigation_id: investigationId,
        cluster_id: selectedClusterId,
        decision,
        reviewer: 'CID Investigator',
        notes,
      });
      addReview(record);
      setNotes('');
    } catch {
      alert('Review submission failed');
    } finally {
      setLoading(false);
    }
  };

  if (!investigationId) {
    return <EmptyState icon="📋" title="Human review" description="Complete an investigation to accept, reject, or flag identity links for manual review." />;
  }

  return (
    <div className="space-y-5">
      <div className="intel-card p-4">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Reviewing Cluster</p>
        <p className="mt-1 font-mono text-sm text-cyan-300">{selectedClusterId ?? '—'}</p>
        {cluster && (
          <div className="mt-4">
            <div className="mb-2 flex justify-between text-sm">
              <span className="text-slate-400">Link confidence</span>
              <span className="font-bold">{cluster.confidence_score.toFixed(1)}%</span>
            </div>
            <ConfidenceBar score={cluster.confidence_score} showLabel />
            <div className="mt-3 flex flex-wrap gap-1">
              {cluster.evidence.map((e) => (
                <Badge key={e.type} variant={e.conflicting ? 'warn' : 'muted'}>{e.type} {(e.score * 100).toFixed(0)}%</Badge>
              ))}
            </div>
          </div>
        )}
      </div>

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Investigator notes for case file…"
        rows={3}
        className="intel-input w-full resize-none"
      />

      <div className="grid grid-cols-3 gap-3">
        <button onClick={() => handleReview('approve')} disabled={loading} className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 py-4 text-sm font-semibold text-emerald-300 transition hover:bg-emerald-500/20 disabled:opacity-40">
          ✓ Accept Link
        </button>
        <button onClick={() => handleReview('suspicious')} disabled={loading} className="rounded-xl border border-amber-500/30 bg-amber-500/10 py-4 text-sm font-semibold text-amber-300 transition hover:bg-amber-500/20 disabled:opacity-40">
          ⚠ Needs Review
        </button>
        <button onClick={() => handleReview('reject')} disabled={loading} className="rounded-xl border border-rose-500/30 bg-rose-500/10 py-4 text-sm font-semibold text-rose-300 transition hover:bg-rose-500/20 disabled:opacity-40">
          ✗ Reject Link
        </button>
      </div>

      {reviews.length > 0 && (
        <div>
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">Review History</h3>
          <div className="space-y-2">
            {reviews.map((r) => (
              <div key={r.review_id} className="intel-card p-3 text-sm">
                <div className="flex items-center gap-2">
                  <Badge variant={r.decision === 'approve' ? 'success' : r.decision === 'reject' ? 'danger' : 'warn'}>
                    {r.decision === 'approve' ? 'Accepted' : r.decision === 'reject' ? 'Rejected' : 'Needs Review'}
                  </Badge>
                  <span className="font-mono text-xs text-slate-500">{r.cluster_id.slice(0, 16)}…</span>
                </div>
                {r.notes && <p className="mt-2 text-xs text-slate-400">{r.notes}</p>}
                <p className="mt-1 text-[10px] text-slate-600">{new Date(r.timestamp).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
