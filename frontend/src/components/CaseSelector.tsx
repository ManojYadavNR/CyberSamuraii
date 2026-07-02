import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { createCase, fetchCases } from '../api/enterprise';
import { useAuthStore } from '../store/authStore';
import { useUiStore } from '../store/uiStore';
import { hasPermission } from '../lib/permissions';
import type { CaseOut } from '../types/enterprise';
import { caseStatusClass, formatCaseDate } from './CaseEditModal';

export function CaseSelector() {
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [loading, setLoading] = useState(false);
  const activeCaseId = useAuthStore((s) => s.activeCaseId);
  const selectedCaseId = useUiStore((s) => s.selectedCaseId);
  const selectedCaseMeta = useUiStore((s) => s.selectedCaseMeta);
  const setSelectedCase = useUiStore((s) => s.setSelectedCase);
  const role = useAuthStore((s) => s.user?.role || 'VIEWER');
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<{ top: number; left: number; width: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const currentId = activeCaseId || selectedCaseId;

  const updateMenuPosition = () => {
    const el = rootRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setMenuStyle({
      top: rect.bottom + 6,
      left: rect.left,
      width: Math.max(rect.width, 280),
    });
  };

  const reload = () => {
    setLoading(true);
    return fetchCases()
      .then((rows) => {
        setCases(rows);
        if (currentId) {
          const match = rows.find((c) => c.case_id === currentId);
          if (match) {
            setSelectedCase(currentId, { case_number: match.case_number, title: match.title });
          }
        }
      })
      .catch(() => setCases([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    reload();
  }, []);

  useEffect(() => {
    if (!open) return;
    reload();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    updateMenuPosition();
    const onScroll = () => updateMenuPosition();
    const onResize = () => updateMenuPosition();
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onResize);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const active = cases.find((c) => c.case_id === currentId);
  const label = active?.case_number || selectedCaseMeta?.case_number;
  const subtitle = active?.title || selectedCaseMeta?.title;

  const handleCreate = async () => {
    const title = window.prompt('Case title:');
    if (!title?.trim()) return;
    const row = await createCase({ title: title.trim(), priority: 'MEDIUM' });
    await reload();
    setSelectedCase(row.case_id, { case_number: row.case_number, title: row.title });
    setOpen(false);
  };

  const select = (c: CaseOut) => {
    setSelectedCase(c.case_id, { case_number: c.case_number, title: c.title });
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="case-selector">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`case-selector__trigger ${open ? 'case-selector__trigger--open' : ''}`}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span className="case-selector__icon" aria-hidden>📁</span>
        <span className="case-selector__text">
          <span className="case-selector__label">{label || 'Select case'}</span>
          {subtitle && <span className="case-selector__hint">{subtitle}</span>}
        </span>
        <svg className={`case-selector__chevron ${open ? 'case-selector__chevron--open' : ''}`} viewBox="0 0 20 20" fill="currentColor" aria-hidden>
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>

      {open && menuStyle && createPortal(
        <div
          ref={menuRef}
          className="case-selector__menu case-selector__menu--enter"
          style={{
            top: menuStyle.top,
            left: menuStyle.left,
            width: menuStyle.width,
          }}
          role="listbox"
        >
          {hasPermission(role, 'create_case') && (
            <button type="button" onClick={handleCreate} className="case-selector__new">
              + New case
            </button>
          )}
          <div className="case-selector__list">
            {loading && cases.length === 0 && (
              <p className="case-selector__empty">Loading cases…</p>
            )}
            {!loading && cases.length === 0 && (
              <p className="case-selector__empty">No cases yet</p>
            )}
            {cases.map((c) => {
              const selected = c.case_id === currentId;
              return (
                <button
                  key={c.case_id}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => select(c)}
                  className={`case-selector__option ${selected ? 'case-selector__option--active' : ''}`}
                >
                  <span className="case-selector__option-top">
                    <span className="case-selector__option-id">{c.case_number}</span>
                    <span className={`cases-status cases-status--compact ${caseStatusClass(c.status)}`}>
                      {c.status.replace(/_/g, ' ')}
                    </span>
                  </span>
                  <span className="case-selector__option-title">{c.title}</span>
                  <span className="case-selector__option-date">Created {formatCaseDate(c.created_at)}</span>
                </button>
              );
            })}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
