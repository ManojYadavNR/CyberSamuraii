import { useEffect, useState } from 'react';
import { fetchReviews, submitReview } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';

export function ReviewPanel() {
  const investigationId = useInvestigationStore((s) => s.investigationId);
  const selectedClusterId = useInvestigationStore((s) => s.selectedClusterId);
  const reviews = useInvestigationStore((s) => s.reviews);
  const addReview = useInvestigationStore((s) => s.addReview);
  const setReviews = useInvestigationStore((s) => s.setReviews);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

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
    return <div className="text-sm text-slate-500">Complete an investigation to submit human review</div>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        Reviewing: <span className="font-mono text-slate-200">{selectedClusterId ?? '—'}</span>
        <span className="ml-2 text-xs text-slate-500">POST /api/dashboard/review</span>
      </p>

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Investigator notes (optional)…"
        rows={3}
        className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-blue-500"
      />

      <div className="flex gap-2">
        <ReviewButton color="green" label="Approve" onClick={() => handleReview('approve')} disabled={loading} />
        <ReviewButton color="red" label="Reject" onClick={() => handleReview('reject')} disabled={loading} />
        <ReviewButton color="amber" label="Suspicious" onClick={() => handleReview('suspicious')} disabled={loading} />
      </div>

      {reviews.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-400">
            Review History (GET /api/dashboard/review/{investigationId.slice(0, 8)}…)
          </h3>
          <div className="space-y-2">
            {reviews.map((r) => (
              <div key={r.review_id} className="rounded-lg bg-slate-800/60 px-3 py-2 text-sm">
                <span className={`font-medium capitalize ${
                  r.decision === 'approve' ? 'text-green-400' : r.decision === 'reject' ? 'text-red-400' : 'text-amber-400'
                }`}>{r.decision}</span>
                <span className="text-slate-500"> · {r.cluster_id}</span>
                <span className="text-xs text-slate-600"> · {new Date(r.timestamp).toLocaleString()}</span>
                {r.notes && <p className="mt-1 text-slate-400">{r.notes}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewButton({ color, label, onClick, disabled }: {
  color: 'green' | 'red' | 'amber'; label: string; onClick: () => void; disabled?: boolean;
}) {
  const colors = { green: 'bg-green-600 hover:bg-green-500', red: 'bg-red-600 hover:bg-red-500', amber: 'bg-amber-600 hover:bg-amber-500' };
  return (
    <button onClick={onClick} disabled={disabled} className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium text-white transition disabled:opacity-40 ${colors[color]}`}>
      {label}
    </button>
  );
}
