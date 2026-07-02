import { useEffect, useState } from 'react';
import { LuFolderOpen, LuPlus } from 'react-icons/lu';
import {
  archiveCase, assignCase, closeCase, createCase, deleteCase, fetchCases, fetchUsers, transferCase,
} from '../api/enterprise';
import { CaseEditModal, casePriorityClass, caseStatusClass, formatCaseDate } from '../components/CaseEditModal';
import { PageSectionHeader } from '../components/PageSectionHeader';
import { useAuthStore } from '../store/authStore';
import { useUiStore } from '../store/uiStore';
import { hasPermission } from '../lib/permissions';
import { useCompactPageHeader } from '../hooks/useCompactPageHeader';
import { LoadingTransition, TableSkeleton } from '../components/loading';
import type { CaseOut } from '../types/enterprise';

interface UserRow {
  user_id: string;
  username: string;
  name: string;
  role: string;
}

export function CasesPage() {
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [title, setTitle] = useState('');
  const [editingCase, setEditingCase] = useState<CaseOut | null>(null);
  const [assignDraft, setAssignDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const { scrollRef, headerCompact } = useCompactPageHeader([loading, cases.length]);
  const openCase = useUiStore((s) => s.openCase);
  const role = useAuthStore((s) => s.user?.role || 'VIEWER');
  const canCreate = hasPermission(role, 'create_case');
  const canAssign = hasPermission(role, 'assign_case');
  const canEdit = hasPermission(role, 'edit_case');
  const canClose = hasPermission(role, 'close_case');
  const canDelete = hasPermission(role, 'delete_case');

  const reload = () => {
    setLoading(true);
    return fetchCases().then(setCases).catch(() => setCases([])).finally(() => setLoading(false));
  };

  useEffect(() => {
    reload();
    if (canAssign) {
      fetchUsers().then((rows) => setUsers(rows as UserRow[])).catch(() => setUsers([]));
    }
  }, [canAssign]);

  const handleCreate = async () => {
    if (!title.trim()) return;
    const created = await createCase({ title: title.trim(), priority: 'MEDIUM' });
    setTitle('');
    await reload();
    openCase(created.case_id, { case_number: created.case_number, title: created.title });
  };

  const handleOpen = (c: CaseOut) => {
    openCase(c.case_id, { case_number: c.case_number, title: c.title });
  };

  const initialLoad = loading && cases.length === 0;

  return (
    <div className="cases-page cases-page--contained">
      <PageSectionHeader
        title="Cases"
        subtitle={`All investigation cases (${cases.length})`}
        count={cases.length}
        compact={headerCompact}
        icon={LuFolderOpen}
        actions={canCreate ? (
          <>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void handleCreate(); }}
              placeholder="New case title"
              className="cases-input cases-input--create"
            />
            <button type="button" onClick={() => void handleCreate()} className="cases-btn cases-btn--primary cases-btn--create">
              <LuPlus className="h-4 w-4 shrink-0" aria-hidden />
              <span className="cases-btn__label">Create Case</span>
            </button>
          </>
        ) : undefined}
      />

      <LoadingTransition loading={initialLoad} fallback={<TableSkeleton rows={6} cols={6} />} className="cases-page__body">
        <LoadingTransition loading={loading && cases.length > 0} overlay overlayLabel="Refreshing cases…" fallback={null} className="cases-page__body">
          <div className="cases-panel">
            <div ref={scrollRef} className="cases-table-wrap">
              <table className="cases-table">
                <thead>
                  <tr>
                    <th>Case #</th>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Priority</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="cases-table__empty">
                        No cases yet — create one to start investigating.
                      </td>
                    </tr>
                  ) : cases.map((c) => (
                    <tr key={c.case_id}>
                      <td className="cases-table__id">{c.case_number}</td>
                      <td>
                        <div className="cases-table__title">{c.title}</div>
                        {c.description && <div className="cases-table__desc">{c.description}</div>}
                      </td>
                      <td>
                        <span className={`cases-status ${caseStatusClass(c.status)}`}>
                          {c.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td>
                        <span className={`cases-priority ${casePriorityClass(c.priority)}`}>
                          {c.priority}
                        </span>
                      </td>
                      <td className="cases-table__date">
                        <div>{formatCaseDate(c.created_at)}</div>
                        {c.updated_at && c.updated_at !== c.created_at && (
                          <div className="cases-table__updated">Updated {formatCaseDate(c.updated_at)}</div>
                        )}
                      </td>
                      <td>
                        <div className="cases-actions">
                          <button type="button" onClick={() => handleOpen(c)} className="cases-action cases-action--primary">
                            Open
                          </button>
                          {canEdit && (
                            <button type="button" onClick={() => setEditingCase(c)} className="cases-action">
                              Edit
                            </button>
                          )}
                          {canClose && c.status !== 'CLOSED' && (
                            <button type="button" onClick={() => closeCase(c.case_id).then(reload)} className="cases-action cases-action--warn">
                              Close
                            </button>
                          )}
                          {canClose && c.status !== 'ARCHIVED' && (
                            <button type="button" onClick={() => archiveCase(c.case_id).then(reload)} className="cases-action">
                              Archive
                            </button>
                          )}
                          {canDelete && (
                            <button
                              type="button"
                              onClick={() => { if (window.confirm('Delete this case?')) deleteCase(c.case_id).then(reload); }}
                              className="cases-action cases-action--danger"
                            >
                              Delete
                            </button>
                          )}
                        </div>
                        {canAssign && (
                          <div className="cases-assign">
                            <select
                              value={assignDraft[c.case_id] || ''}
                              onChange={(e) => setAssignDraft((prev) => ({ ...prev, [c.case_id]: e.target.value }))}
                              className="cases-assign__select"
                            >
                              <option value="">Assign investigator…</option>
                              {users.map((u) => <option key={u.user_id} value={u.user_id}>{u.name}</option>)}
                            </select>
                            <button
                              type="button"
                              disabled={!assignDraft[c.case_id]}
                              onClick={() => assignCase(c.case_id, assignDraft[c.case_id]).then(reload)}
                              className="cases-action"
                            >
                              Assign
                            </button>
                            <button
                              type="button"
                              disabled={!assignDraft[c.case_id]}
                              onClick={() => transferCase(c.case_id, assignDraft[c.case_id]).then(reload)}
                              className="cases-action"
                            >
                              Transfer
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </LoadingTransition>
      </LoadingTransition>

      <CaseEditModal
        caseRow={editingCase}
        onClose={() => setEditingCase(null)}
        onSaved={reload}
      />
    </div>
  );
}
