import { useEffect, useState } from 'react';
import { LuClipboardCheck, LuRefreshCw } from 'react-icons/lu';
import { decideApproval, fetchPendingApprovals, type ApprovalRecord } from '../api/enterprise';
import { PageSectionHeader } from '../components/PageSectionHeader';
import { CardSkeleton, LoadingTransition } from '../components/loading';
import { useCompactPageHeader } from '../hooks/useCompactPageHeader';
import { useUiStore } from '../store/uiStore';
import { hasPermission } from '../lib/permissions';
import { useAuthStore } from '../store/authStore';

export function PendingApprovalsPage() {
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const { scrollRef, headerCompact } = useCompactPageHeader([loading, approvals.length]);
  const openCase = useUiStore((s) => s.openCase);
  const role = useAuthStore((s) => s.user?.role || 'VIEWER');
  const canDecide = hasPermission(role, 'approve_evidence');

  const reload = () => {
    setLoading(true);
    fetchPendingApprovals().then((d) => setApprovals(d.approvals || [])).catch(() => setApprovals([])).finally(() => setLoading(false));
  };

  useEffect(() => { reload(); }, []);

  const decide = async (approvalId: string, decision: string) => {
    await decideApproval(approvalId, decision, notes[approvalId] || '');
    await reload();
  };

  return (
    <div className="intel-page--contained">
      <PageSectionHeader
        title="Pending Approvals"
        subtitle={`${approvals.length} item(s) awaiting review`}
        count={approvals.length}
        compact={headerCompact}
        icon={LuClipboardCheck}
        actions={(
          <button type="button" onClick={reload} className="audit-toolbar-btn audit-toolbar-btn--ghost">
            <LuRefreshCw className="h-3.5 w-3.5" aria-hidden />
            Refresh
          </button>
        )}
      />
      <div ref={scrollRef} className="intel-page__scroll">
        <LoadingTransition loading={loading} fallback={<CardSkeleton count={3} />}>
          {approvals.length === 0 ? (
            <div className="intel-panel rounded-xl p-8 text-center text-slate-500">No pending approvals</div>
          ) : (
            <ul className="space-y-3 pb-2">
              {approvals.map((a) => (
                <li key={a.approval_id} className="intel-panel rounded-xl p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-white">Stage: {a.stage}</p>
                      <p className="font-mono text-xs text-cyan-400">Cluster {a.cluster_id?.slice(0, 20)}…</p>
                      <p className="text-xs text-slate-500">Investigation {a.investigation_id?.slice(0, 12)}…</p>
                      {a.notes && <p className="mt-1 text-xs text-slate-400">{a.notes}</p>}
                    </div>
                    <button type="button" onClick={() => openCase(a.case_id)} className="text-xs text-cyan-400 hover:underline">Open case</button>
                  </div>
                  {canDecide && (
                    <>
                      <textarea
                        value={notes[a.approval_id] || ''}
                        onChange={(e) => setNotes((prev) => ({ ...prev, [a.approval_id]: e.target.value }))}
                        placeholder="Reviewer notes…"
                        rows={2}
                        className="mt-3 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
                      />
                      <div className="mt-2 flex gap-2">
                        <button type="button" onClick={() => decide(a.approval_id, 'approved')} className="rounded bg-emerald-600/20 px-3 py-1 text-xs text-emerald-300">Approve</button>
                        <button type="button" onClick={() => decide(a.approval_id, 'clarification')} className="rounded bg-amber-600/20 px-3 py-1 text-xs text-amber-300">Clarification</button>
                        <button type="button" onClick={() => decide(a.approval_id, 'rejected')} className="rounded bg-rose-600/20 px-3 py-1 text-xs text-rose-300">Reject</button>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </LoadingTransition>
      </div>
    </div>
  );
}
