import { useEffect, useMemo, useState } from 'react';
import {
  fetchCaseAssignments, fetchMyPermissions, fetchUsers, setCaseAssignments, type CaseAssignmentRow,
} from '../api/enterprise';
import { IntelSelect } from './ui/IntelSelect';
import {
  caseRelationshipOptions, hasPermission, loadRbacConfig, permissionLabel, relationshipLabel, resolveRank,
} from '../lib/permissions';
import { useAuthStore } from '../store/authStore';

interface UserRow {
  user_id: string;
  name: string;
  username: string;
  role: string;
  rank_code?: string;
  department?: string;
}

interface CaseTeamPanelProps {
  caseId: string;
}

export function CaseTeamPanel({ caseId }: CaseTeamPanelProps) {
  const role = useAuthStore((s) => s.user?.role || 'VIEWER');
  const canAssign = hasPermission(role, 'assign_case');
  const [assignments, setAssignments] = useState<CaseAssignmentRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [permSummary, setPermSummary] = useState<string[]>([]);
  const [pickUser, setPickUser] = useState('');
  const [pickRel, setPickRel] = useState('assistant_investigator');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const relOptions = useMemo(
    () => caseRelationshipOptions().map((r) => ({ value: r.code, label: r.label })),
    [],
  );

  const userOptions = useMemo(
    () => users.map((u) => ({
      value: u.user_id,
      label: u.name,
      hint: `${resolveRank(u.role)} · ${u.role.replace(/_/g, ' ')}`,
    })),
    [users],
  );

  const reload = () => {
    setLoading(true);
    Promise.all([
      fetchCaseAssignments(caseId),
      fetchMyPermissions(caseId),
      canAssign ? fetchUsers() : Promise.resolve([]),
    ])
      .then(([rows, summary, userRows]) => {
        setAssignments(rows);
        setPermSummary(summary.effective_on_case || []);
        setUsers(userRows as UserRow[]);
      })
      .catch(() => setError('Failed to load case team'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    void loadRbacConfig();
    reload();
  }, [caseId]);

  const handleAdd = async () => {
    if (!pickUser || !pickRel) return;
    setError('');
    try {
      await setCaseAssignments(caseId, [{ user_id: pickUser, relationship: pickRel }]);
      setPickUser('');
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Assignment failed');
    }
  };

  const grouped = useMemo(() => {
    const map = new Map<string, CaseAssignmentRow[]>();
    for (const row of assignments) {
      const list = map.get(row.relationship) || [];
      list.push(row);
      map.set(row.relationship, list);
    }
    return map;
  }, [assignments]);

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-800/80 bg-slate-950/40 p-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400">Your permissions on this case</h3>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {permSummary.length === 0 ? (
            <span className="text-xs text-slate-500">No case-scoped permissions</span>
          ) : permSummary.slice(0, 12).map((p) => (
            <span key={p} className="rounded-full border border-cyan-500/20 bg-cyan-950/30 px-2 py-0.5 text-[10px] text-cyan-200">
              {permissionLabel(p)}
            </span>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-slate-800/80 bg-slate-950/40 p-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">Investigation team</h3>
        {loading ? (
          <p className="mt-2 text-xs text-slate-500">Loading team…</p>
        ) : (
          <div className="mt-3 space-y-3">
            {Array.from(grouped.entries()).map(([rel, rows]) => (
              <div key={rel}>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-300/90">
                  {relationshipLabel(rel)} ({rows.length})
                </p>
                <ul className="mt-1 space-y-1">
                  {rows.map((row) => {
                    const u = users.find((x) => x.user_id === row.user_id);
                    return (
                      <li key={row.assignment_id} className="flex items-center justify-between rounded border border-slate-800/60 px-2 py-1.5 text-xs">
                        <span className="text-slate-200">{u?.name || row.user_id.slice(0, 8)}</span>
                        <span className="text-slate-500">{row.rank_code || row.org_role}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
            {assignments.length === 0 && (
              <p className="text-xs text-slate-500">No team members assigned yet.</p>
            )}
          </div>
        )}

        {canAssign && (
          <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-slate-800/60 pt-3">
            <div className="min-w-[10rem] flex-1">
              <p className="mb-1 text-[10px] uppercase text-slate-500">Officer</p>
              <IntelSelect value={pickUser} onChange={setPickUser} options={userOptions} placeholder="Select user…" size="sm" />
            </div>
            <div className="min-w-[10rem] flex-1">
              <p className="mb-1 text-[10px] uppercase text-slate-500">Case relationship</p>
              <IntelSelect value={pickRel} onChange={setPickRel} options={relOptions} size="sm" />
            </div>
            <button type="button" onClick={() => void handleAdd()} disabled={!pickUser} className="cases-action cases-action--primary">
              Add to team
            </button>
          </div>
        )}
        {error && <p className="mt-2 text-xs text-rose-400">{error}</p>}
      </div>
    </div>
  );
}
