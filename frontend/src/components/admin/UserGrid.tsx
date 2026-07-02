import { useMemo, useState } from 'react';
import type { IamUser } from './iamTypes';
import { roleBadgeClass, userInitials, userStatus } from './iamHelpers';
import { getRolePermissions, permissionLabel } from '../../lib/permissions';
import { useUiStore } from '../../store/uiStore';

interface UserGridProps {
  users: IamUser[];
  onView: (user: IamUser) => void;
}

const PAGE_SIZE = 8;

export function UserGrid({ users, onView }: UserGridProps) {
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [page, setPage] = useState(1);
  const setAppPage = useUiStore((s) => s.setPage);
  const setAuditPrefill = useUiStore((s) => s.setAuditPrefill);

  const roles = useMemo(() => [...new Set(users.map((u) => u.role))].sort(), [users]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return users.filter((u) => {
      if (roleFilter && u.role !== roleFilter) return false;
      if (!q) return true;
      return [u.name, u.username, u.email, u.role, u.department, u.employee_id, u.badge_number]
        .some((v) => String(v).toLowerCase().includes(q));
    });
  }, [users, query, roleFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const paged = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const openUserAudit = (u: IamUser) => {
    setAuditPrefill({ user_id: u.user_id, username: u.username, label: u.name });
    setAppPage('audit');
  };

  if (users.length === 0) {
    return (
      <div className="iam-empty">
        <div className="iam-empty-icon">👥</div>
        <p className="iam-empty-title">No users provisioned</p>
        <p className="iam-empty-desc">Create the first investigator account to begin identity management.</p>
      </div>
    );
  }

  return (
    <div className="iam-user-directory flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-center gap-2 rounded-lg border border-slate-800/80 bg-slate-950/60 p-3">
        <input
          className="iam-input max-w-xs"
          placeholder="Search users…"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setPage(1); }}
        />
        <select
          className="iam-input iam-select max-w-[180px]"
          value={roleFilter}
          onChange={(e) => { setRoleFilter(e.target.value); setPage(1); }}
        >
          <option value="">All roles</option>
          {roles.map((r) => <option key={r} value={r}>{r.replace(/_/g, ' ')}</option>)}
        </select>
        <span className="iam-badge-soft">{filtered.length} of {users.length} accounts</span>
      </div>

      <div className="iam-user-table-scroll">
        <table className="iam-user-grid iam-user-grid--fit">
          <thead>
            <tr>
              <th>User</th>
              <th>Credentials</th>
              <th>Role</th>
              <th>Status</th>
              <th>Last Login</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((u) => {
              const status = userStatus(u);
              const perms = getRolePermissions(u.role);
              const permTip = perms.includes('*')
                ? 'Full platform access'
                : perms.map(permissionLabel).join(', ');

              return (
                <tr key={u.user_id} className="cursor-pointer" onClick={() => onView(u)}>
                  <td>
                    <div className="flex items-center gap-2.5">
                      <div className="iam-avatar iam-avatar--sm shrink-0">{userInitials(u)}</div>
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-slate-100">{u.name}</div>
                        <div className="truncate font-mono text-[10px] text-slate-500">@{u.username}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="min-w-0 text-[11px] leading-relaxed text-slate-400">
                      <div className="truncate" title={u.employee_id || undefined}>
                        <span className="text-slate-600">Emp:</span> {u.employee_id || '—'}
                      </div>
                      <div className="truncate" title={u.badge_number || undefined}>
                        <span className="text-slate-600">Badge:</span> {u.badge_number || '—'}
                      </div>
                    </div>
                  </td>
                  <td>
                    <span
                      className={`iam-role ${roleBadgeClass(u.role)}`}
                      title={permTip}
                    >
                      {u.role.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td>
                    <span className={`iam-status ${status.className}`}>{status.label}</span>
                  </td>
                  <td className="text-[11px] text-slate-500">
                    {u.last_login ? u.last_login.slice(0, 10) : 'Never'}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="iam-user-actions">
                      <button type="button" className="iam-btn-sm" onClick={() => onView(u)}>View</button>
                      <button type="button" className="iam-btn-sm" onClick={() => openUserAudit(u)}>Audit</button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="iam-pagination shrink-0">
        <p className="text-xs text-slate-500">
          Showing {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length}
        </p>
        <div className="flex items-center gap-2">
          <button type="button" className="iam-btn-sm" disabled={currentPage === 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <span className="text-xs text-slate-500">Page {currentPage} / {totalPages}</span>
          <button type="button" className="iam-btn-sm" disabled={currentPage === totalPages} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      </div>
    </div>
  );
}
