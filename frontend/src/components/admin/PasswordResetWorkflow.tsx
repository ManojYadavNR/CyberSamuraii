import { useMemo, useState } from 'react';
import type { PasswordResetRequestRow } from '../../types/enterprise';
import type { PasswordResetTab } from './iamTypes';

const TABS: { id: PasswordResetTab; label: string }[] = [
  { id: 'pending', label: 'Pending Requests' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'completed', label: 'Completed' },
];

function tabForRequest(r: PasswordResetRequestRow): PasswordResetTab {
  if (r.status === 'approved') return 'approved';
  if (r.status === 'denied') return 'rejected';
  if (r.status === 'pending_supervisor' || r.status === 'pending_admin') return 'pending';
  return 'completed';
}

interface PasswordResetWorkflowProps {
  requests: PasswordResetRequestRow[];
  canSupervise: boolean;
  canAdmin: boolean;
  notes: Record<string, string>;
  onNotesChange: (id: string, value: string) => void;
  onSupervisor: (id: string, approve: boolean) => void;
  onAdmin: (id: string, approve: boolean) => void;
  lastTempPassword: string;
}

export function PasswordResetWorkflow({
  requests,
  canSupervise,
  canAdmin,
  notes,
  onNotesChange,
  onSupervisor,
  onAdmin,
  lastTempPassword,
}: PasswordResetWorkflowProps) {
  const [tab, setTab] = useState<PasswordResetTab>('pending');

  const grouped = useMemo(() => {
    const m: Record<PasswordResetTab, PasswordResetRequestRow[]> = {
      pending: [], approved: [], rejected: [], completed: [],
    };
    requests.forEach((r) => m[tabForRequest(r)].push(r));
    return m;
  }, [requests]);

  const visible = grouped[tab];

  return (
    <div>
      <div className="iam-reset-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`iam-section-pill ${tab === t.id ? 'iam-section-pill--active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            <span className="ml-1.5 rounded-full bg-slate-800 px-1.5 py-0.5 text-[9px]">{grouped[t.id].length}</span>
          </button>
        ))}
      </div>

      {lastTempPassword && (
        <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-950/30 px-4 py-3 text-sm text-amber-200">
          Temporary password issued — deliver via secure channel:{' '}
          <span className="font-mono font-semibold">{lastTempPassword}</span>
        </div>
      )}

      {visible.length === 0 ? (
        <div className="iam-empty">
          <div className="iam-empty-icon">🔐</div>
          <p className="iam-empty-title">No {tab} password reset requests</p>
          <p className="iam-empty-desc">
            Investigator requests flow through supervisor verification, then administrator approval before a temporary password is issued.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {visible.map((req) => (
            <div key={req.request_id} className="iam-reset-card fade-in">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-white">{req.employee_name || req.employee_id}</p>
                  <p className="text-[11px] text-slate-500">
                    {req.employee_id} · CID · {req.requested_at?.slice(0, 19).replace('T', ' ')}
                  </p>
                </div>
                <span className="rounded-full bg-cyan-950/60 px-2 py-0.5 text-[10px] font-semibold uppercase text-cyan-400">
                  {req.status.replace(/_/g, ' ')}
                </span>
              </div>
              {req.reason && <p className="mt-2 text-xs text-slate-400">Reason: {req.reason}</p>}
              {req.supervisor_id && (
                <p className="mt-1 text-[11px] text-slate-500">Verified by supervisor: {req.supervisor_id}</p>
              )}
              {(canSupervise || canAdmin) && (req.status === 'pending_supervisor' || req.status === 'pending_admin') && (
                <textarea
                  value={notes[req.request_id] || ''}
                  onChange={(e) => onNotesChange(req.request_id, e.target.value)}
                  placeholder="Decision notes"
                  rows={2}
                  className="iam-input mt-3 text-xs"
                />
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                {canSupervise && req.status === 'pending_supervisor' && (
                  <>
                    <button type="button" onClick={() => onSupervisor(req.request_id, true)} className="iam-btn-primary text-xs">Approve</button>
                    <button type="button" onClick={() => onSupervisor(req.request_id, false)} className="iam-btn-ghost text-xs text-rose-300">Reject</button>
                  </>
                )}
                {canAdmin && req.status === 'pending_admin' && (
                  <>
                    <button type="button" onClick={() => onAdmin(req.request_id, true)} className="iam-btn-primary text-xs">Issue Temporary Password</button>
                    <button type="button" onClick={() => onAdmin(req.request_id, false)} className="iam-btn-ghost text-xs text-rose-300">Reject</button>
                  </>
                )}
                {req.status === 'approved' && req.temp_password_issued && (
                  <span className="text-xs text-emerald-400">✓ Temporary password issued</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
