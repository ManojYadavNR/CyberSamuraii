import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { updateCase } from '../api/enterprise';
import { IntelSelect } from './ui/IntelSelect';
import type { CaseOut } from '../types/enterprise';

const STATUSES = ['OPEN', 'ACTIVE', 'UNDER_REVIEW', 'ESCALATED', 'CLOSED', 'ARCHIVED'] as const;
const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const;

interface CaseEditModalProps {
  caseRow: CaseOut | null;
  onClose: () => void;
  onSaved: () => void;
}

export function CaseEditModal({ caseRow, onClose, onSaved }: CaseEditModalProps) {
  const [form, setForm] = useState({
    title: '',
    description: '',
    priority: 'MEDIUM',
    status: 'OPEN',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!caseRow) return;
    setForm({
      title: caseRow.title,
      description: caseRow.description || '',
      priority: caseRow.priority,
      status: caseRow.status,
    });
    setError('');
  }, [caseRow]);

  if (!caseRow) return null;

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      await updateCase(caseRow.case_id, form);
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update case');
    } finally {
      setSaving(false);
    }
  };

  const modal = (
    <div className="cases-modal-backdrop" onClick={onClose}>
      <div className="cases-modal" onClick={(e) => e.stopPropagation()}>
        <div className="cases-modal__header">
          <div>
            <p className="cases-modal__eyebrow">Edit case</p>
            <h2 className="cases-modal__title">{caseRow.case_number}</h2>
            <p className="cases-modal__subtitle">{caseRow.title}</p>
          </div>
          <button type="button" onClick={onClose} className="cases-modal__close" aria-label="Close">✕</button>
        </div>

        <div className="cases-modal__body">
          <label className="cases-field">
            <span className="cases-field__label">Title</span>
            <input
              className="cases-input"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </label>
          <label className="cases-field">
            <span className="cases-field__label">Description</span>
            <textarea
              className="cases-input cases-input--textarea"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              rows={3}
              placeholder="Case summary, scope, or operational notes"
            />
          </label>
          <div className="cases-modal__grid">
            <IntelSelect
              label="Status"
              value={form.status}
              options={STATUSES.map((s) => ({ value: s, label: s.replace(/_/g, ' ') }))}
              onChange={(status) => setForm({ ...form, status })}
              className="cases-intel-select"
              size="sm"
            />
            <IntelSelect
              label="Priority"
              value={form.priority}
              options={PRIORITIES.map((p) => ({ value: p, label: p }))}
              onChange={(priority) => setForm({ ...form, priority })}
              className="cases-intel-select"
              size="sm"
            />
          </div>
          <dl className="cases-modal__meta">
            <div><dt>Created</dt><dd>{formatCaseDate(caseRow.created_at)}</dd></div>
            <div><dt>Last updated</dt><dd>{formatCaseDate(caseRow.updated_at || caseRow.created_at)}</dd></div>
          </dl>
          {error && <p className="cases-modal__error">{error}</p>}
        </div>

        <div className="cases-modal__footer">
          <button type="button" onClick={onClose} className="cases-btn cases-btn--ghost">Cancel</button>
          <button type="button" onClick={handleSave} disabled={saving || !form.title.trim()} className="cases-btn cases-btn--primary">
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}

export function formatCaseDate(iso?: string | null): string {
  if (!iso) return '—';
  return iso.slice(0, 16).replace('T', ' ');
}

export function caseStatusClass(status: string): string {
  const map: Record<string, string> = {
    OPEN: 'cases-status--open',
    ACTIVE: 'cases-status--active',
    UNDER_REVIEW: 'cases-status--review',
    ESCALATED: 'cases-status--escalated',
    CLOSED: 'cases-status--closed',
    ARCHIVED: 'cases-status--archived',
  };
  return map[status] || 'cases-status--open';
}

export function casePriorityClass(priority: string): string {
  const map: Record<string, string> = {
    LOW: 'cases-priority--low',
    MEDIUM: 'cases-priority--medium',
    HIGH: 'cases-priority--high',
    CRITICAL: 'cases-priority--critical',
  };
  return map[priority] || 'cases-priority--medium';
}
