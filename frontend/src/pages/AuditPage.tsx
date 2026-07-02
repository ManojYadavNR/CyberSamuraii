import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LuScrollText } from 'react-icons/lu';
import {
  exportAuditCsv,
  fetchAuditDetail,
  fetchAuditLogs,
  verifyAuditChain,
  type AuditFilters,
} from '../api/enterprise';
import { PageSectionHeader } from '../components/PageSectionHeader';
import { Spinner, TableSkeleton } from '../components/loading';
import { useCompactPageHeader } from '../hooks/useCompactPageHeader';
import { useUiStore } from '../store/uiStore';
import type { AuditLogEntry } from '../types/enterprise';

const CATEGORIES = [
  'all',
  'authentication',
  'investigation',
  'evidence',
  'report',
  'export',
  'user_management',
  'administration',
  'copilot',
  'system',
];

const RISK_COLORS: Record<string, string> = {
  low: 'text-emerald-400',
  medium: 'text-amber-400',
  high: 'text-orange-400',
  critical: 'text-rose-400',
};

function riskBadge(level: string) {
  return <span className={`font-semibold uppercase ${RISK_COLORS[level] || 'text-slate-400'}`}>{level}</span>;
}

function DetailDrawer({ entry, onClose }: { entry: AuditLogEntry; onClose: () => void }) {
  const fields: { label: string; value: string }[] = [
    { label: 'Audit ID', value: entry.audit_id },
    { label: 'Timestamp', value: entry.timestamp },
    { label: 'Category', value: entry.category },
    { label: 'Action', value: entry.action },
    { label: 'User ID', value: entry.user_id },
    { label: 'Username', value: entry.username || entry.user },
    { label: 'Role', value: entry.role },
    { label: 'Session ID', value: entry.session_id },
    { label: 'Case ID', value: entry.case_id },
    { label: 'Investigation ID', value: entry.investigation_id },
    { label: 'Entity Type', value: entry.entity_type },
    { label: 'Entity ID', value: entry.entity_id || entry.entity },
    { label: 'IP Address', value: entry.ip },
    { label: 'Location', value: entry.location_approx },
    { label: 'Device', value: entry.device },
    { label: 'Browser', value: entry.browser },
    { label: 'OS', value: entry.os },
    { label: 'Status', value: entry.result },
    { label: 'Failure Reason', value: entry.failure_reason },
    { label: 'Risk Level', value: entry.risk_level },
    { label: 'Approval Required', value: entry.approval_required ? 'Yes' : 'No' },
    { label: 'Supervisor', value: entry.supervisor_id },
    { label: 'Previous Value', value: entry.previous_value },
    { label: 'New Value', value: entry.new_value },
    { label: 'Digital Signature', value: entry.digital_signature },
    { label: 'Hash Chain', value: entry.hash_chain },
  ];

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 fade-in" onClick={onClose}>
      <div
        className="drawer-enter h-full w-full max-w-lg overflow-y-auto border-l border-slate-700 bg-slate-950 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-white">Audit Entry</h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-white">Close</button>
        </div>
        {entry.suspicious && (
          <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-950/40 px-3 py-2 text-sm text-rose-300">
            Flagged as suspicious — review recommended
          </div>
        )}
        <dl className="space-y-2 text-xs">
          {fields.filter((f) => f.value).map((f) => (
            <div key={f.label} className="grid grid-cols-[140px_1fr] gap-2 border-b border-slate-800/60 py-2">
              <dt className="text-slate-500">{f.label}</dt>
              <dd className="break-all font-mono text-slate-200">{f.value}</dd>
            </div>
          ))}
        </dl>
        {Object.keys(entry.details || {}).length > 0 && (
          <pre className="mt-4 overflow-auto rounded-lg bg-slate-900 p-3 text-[10px] text-slate-400">
            {JSON.stringify(entry.details, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

function TimelineView({ logs }: { logs: AuditLogEntry[] }) {
  return (
    <div className="relative space-y-0 pl-6">
      <div className="absolute bottom-0 left-2 top-0 w-px bg-cyan-500/30" />
      {logs.map((l) => (
        <div key={l.audit_id} className="relative pb-4">
          <div className={`absolute -left-4 top-1 h-2.5 w-2.5 rounded-full ${l.suspicious ? 'bg-rose-500' : 'bg-cyan-500'}`} />
          <p className="text-[10px] text-slate-500">{l.timestamp?.slice(0, 19)}</p>
          <p className="text-sm text-white">
            <span className="text-cyan-400">{l.username || l.user}</span>
            {' · '}
            <span className="font-medium">{l.action}</span>
            {l.case_id ? <span className="text-slate-500"> · case {l.case_id.slice(0, 8)}…</span> : null}
          </p>
          <p className="text-xs text-slate-500">{l.category} · {l.result} · {l.risk_level} risk</p>
        </div>
      ))}
    </div>
  );
}

function buildInitialAuditFilters(prefill: ReturnType<typeof useUiStore.getState>['auditPrefill']): AuditFilters {
  const base: AuditFilters = { limit: 200, suspicious_only: false };
  if (!prefill) return base;
  return {
    ...base,
    user_id: prefill.user_id,
    offset: 0,
  };
}

function countActiveFilters(filters: AuditFilters): number {
  let n = 0;
  if (filters.category) n += 1;
  if (filters.search) n += 1;
  if (filters.username) n += 1;
  if (filters.case_id) n += 1;
  if (filters.user_id) n += 1;
  if (filters.risk_level) n += 1;
  if (filters.role) n += 1;
  if (filters.date_from) n += 1;
  if (filters.date_to) n += 1;
  if (filters.suspicious_only) n += 1;
  return n;
}

export function AuditPage() {
  const auditPrefill = useUiStore((s) => s.auditPrefill);
  const setAuditPrefill = useUiStore((s) => s.setAuditPrefill);
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<AuditLogEntry | null>(null);
  const [view, setView] = useState<'table' | 'timeline'>('table');
  const [chainStatus, setChainStatus] = useState<{ valid: boolean; checked: number; repaired?: number } | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [showFilters, setShowFilters] = useState(() => Boolean(useUiStore.getState().auditPrefill));
  const [filters, setFilters] = useState<AuditFilters>(() =>
    buildInitialAuditFilters(useUiStore.getState().auditPrefill),
  );
  const loadSeq = useRef(0);
  const { scrollRef, headerCompact } = useCompactPageHeader([loading, logs.length, view]);

  useEffect(() => {
    if (!auditPrefill) return;
    setFilters((f) => ({
      ...f,
      user_id: auditPrefill.user_id,
      username: '',
      offset: 0,
    }));
  }, [auditPrefill]);

  const load = useCallback(() => {
    const seq = ++loadSeq.current;
    setLoading(true);
    fetchAuditLogs(filters)
      .then((d) => {
        if (seq !== loadSeq.current) return;
        setLogs(d.logs || []);
        setTotal(d.total || 0);
      })
      .catch(() => {
        if (seq !== loadSeq.current) return;
        setLogs([]);
        setTotal(0);
      })
      .finally(() => {
        if (seq === loadSeq.current) setLoading(false);
      });
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    logs.forEach((l) => {
      counts[l.category] = (counts[l.category] || 0) + 1;
    });
    return counts;
  }, [logs]);

  const setFilter = (patch: Partial<AuditFilters>) => setFilters((f) => ({ ...f, ...patch }));

  const activeFilterCount = useMemo(() => countActiveFilters(filters), [filters]);

  const clearAllFilters = () => {
    setAuditPrefill(null);
    setFilters({ limit: 200, suspicious_only: false, offset: 0 });
  };

  const openDetail = async (entry: AuditLogEntry) => {
    try {
      const full = await fetchAuditDetail(entry.audit_id);
      setSelected(full);
    } catch {
      setSelected(entry);
    }
  };

  const initialLoad = loading && logs.length === 0;

  return (
    <div className="audit-page">
      <PageSectionHeader
        title="Audit Log"
        subtitle={`Immutable, hash-chained record of platform actions · ${total} entries`}
        count={total}
        compact={headerCompact}
        icon={LuScrollText}
        actions={(
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={verifying}
              onClick={() => {
                setVerifying(true);
                verifyAuditChain()
                  .then(setChainStatus)
                  .catch(() => setChainStatus(null))
                  .finally(() => setVerifying(false));
              }}
              className="audit-toolbar-btn audit-toolbar-btn--ghost"
            >
              {verifying ? <Spinner size="sm" variant="dots" /> : null}
              {verifying ? 'Verifying…' : 'Verify integrity'}
            </button>
            <button
              type="button"
              disabled={exporting}
              onClick={() => {
                setExporting(true);
                exportAuditCsv(filters).catch(() => undefined).finally(() => setExporting(false));
              }}
              className="audit-toolbar-btn audit-toolbar-btn--primary"
            >
              {exporting ? <Spinner size="sm" variant="dots" /> : null}
              {exporting ? 'Exporting…' : 'Export CSV'}
            </button>
          </div>
        )}
      />

      <div className="audit-page__controls">
      <div className="audit-toolbar">
        <div className="audit-toolbar__categories">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setFilter({ category: c === 'all' ? '' : c })}
              className={`audit-cat-pill ${
                (c === 'all' && !filters.category) || filters.category === c ? 'audit-cat-pill--active' : ''
              }`}
            >
              {c.replace('_', ' ')}
              {c !== 'all' && categoryCounts[c] ? ` ${categoryCounts[c]}` : ''}
            </button>
          ))}
        </div>
        <div className="audit-toolbar__actions">
          {activeFilterCount > 0 && (
            <button type="button" onClick={clearAllFilters} className="audit-toolbar-btn audit-toolbar-btn--ghost">
              Clear ({activeFilterCount})
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowFilters((v) => !v)}
            className={`audit-toolbar-btn audit-toolbar-btn--filter ${showFilters ? 'audit-toolbar-btn--active' : ''}`}
            aria-expanded={showFilters}
            aria-label="Toggle filters"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path d="M4 6h16M7 12h10M10 18h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            Filters
            {activeFilterCount > 0 && <span className="audit-filter-badge">{activeFilterCount}</span>}
          </button>
          <button
            type="button"
            onClick={() => setView(view === 'table' ? 'timeline' : 'table')}
            className="audit-toolbar-btn audit-toolbar-btn--ghost"
          >
            {view === 'table' ? 'Timeline' : 'Table'}
          </button>
        </div>
      </div>

      {auditPrefill && (
        <div className="audit-banner shrink-0">
          <span>
            Showing audit activity for <strong>{auditPrefill.label}</strong> (@{auditPrefill.username})
          </span>
          <button type="button" onClick={() => { setAuditPrefill(null); setFilters((f) => { const next = { ...f }; delete next.user_id; delete next.username; return next; }); }} className="iam-btn-sm border-cyan-500/40 text-cyan-200">
            Clear user filter
          </button>
        </div>
      )}

      {chainStatus && (
        <div className={`audit-banner shrink-0 fade-in ${chainStatus.valid ? 'text-emerald-300' : 'text-rose-300'}`}>
          Hash chain {chainStatus.valid ? 'valid' : 'BROKEN'}
          {' — '}{chainStatus.checked} entries checked
          {chainStatus.repaired ? ` · ${chainStatus.repaired} legacy entries rebuilt` : ''}
        </div>
      )}

      <div className={`audit-filters-panel ${showFilters ? 'audit-filters-panel--open' : ''}`}>
        <div className="audit-filters-panel__inner intel-panel">
          <div className="audit-filters-grid">
            <input
              value={filters.search || ''}
              onChange={(e) => setFilter({ search: e.target.value })}
              placeholder="Full-text search…"
              className="audit-filter-input"
            />
            <input
              value={filters.username || ''}
              onChange={(e) => setFilter({ username: e.target.value })}
              placeholder="Username"
              className="audit-filter-input"
            />
            <input
              value={filters.case_id || ''}
              onChange={(e) => setFilter({ case_id: e.target.value })}
              placeholder="Case ID"
              className="audit-filter-input"
            />
            <select
              value={filters.risk_level || ''}
              onChange={(e) => setFilter({ risk_level: e.target.value })}
              className="audit-filter-input"
            >
              <option value="">All risk levels</option>
              {['low', 'medium', 'high', 'critical'].map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
            <select
              value={filters.role || ''}
              onChange={(e) => setFilter({ role: e.target.value })}
              className="audit-filter-input"
            >
              <option value="">All roles</option>
              {['SUPER_ADMIN', 'CID_DIRECTOR', 'SP', 'DSP', 'INSPECTOR', 'ANALYST', 'AUDITOR'].map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
            <input
              type="date"
              value={filters.date_from || ''}
              onChange={(e) => setFilter({ date_from: e.target.value })}
              className="audit-filter-input"
            />
            <input
              type="date"
              value={filters.date_to || ''}
              onChange={(e) => setFilter({ date_to: e.target.value })}
              className="audit-filter-input"
            />
            <label className="audit-filter-check">
              <input
                type="checkbox"
                checked={Boolean(filters.suspicious_only)}
                onChange={(e) => setFilter({ suspicious_only: e.target.checked })}
              />
              Suspicious only
            </label>
          </div>
          <div className="audit-filters-actions">
            <button type="button" onClick={load} disabled={loading} className="audit-toolbar-btn audit-toolbar-btn--primary">
              {loading ? <Spinner size="sm" variant="dots" /> : null}
              Apply filters
            </button>
            <button type="button" onClick={() => setShowFilters(false)} className="audit-toolbar-btn audit-toolbar-btn--ghost">
              Close
            </button>
          </div>
        </div>
      </div>
      </div>

      <div className="audit-page__table">
        {loading && !initialLoad && (
          <div className="audit-page__loading-bar">
            <Spinner size="sm" variant="dots" />
            <span>Updating audit log…</span>
          </div>
        )}
        {initialLoad ? (
          <TableSkeleton rows={12} cols={8} />
        ) : view === 'timeline' ? (
          <div ref={scrollRef} className="audit-table-scroll intel-panel rounded-xl p-4">
            <TimelineView logs={logs} />
          </div>
        ) : (
          <div ref={scrollRef} className="audit-table-scroll intel-panel rounded-xl">
            <table className="w-full text-left text-xs">
            <thead className="audit-table-head sticky top-0 z-10 border-b border-slate-800 bg-[#0a101c] text-[10px] uppercase text-slate-500 shadow-[0_4px_12px_rgba(0,0,0,0.35)]">
              <tr>
                <th className="bg-[#0a101c] px-3 py-2">Time</th>
                <th className="bg-[#0a101c] px-3 py-2">Audit ID</th>
                <th className="bg-[#0a101c] px-3 py-2">User</th>
                <th className="bg-[#0a101c] px-3 py-2">Role</th>
                <th className="bg-[#0a101c] px-3 py-2">Category</th>
                <th className="bg-[#0a101c] px-3 py-2">Action</th>
                <th className="bg-[#0a101c] px-3 py-2">Case</th>
                <th className="bg-[#0a101c] px-3 py-2">Entity</th>
                <th className="bg-[#0a101c] px-3 py-2">Device</th>
                <th className="bg-[#0a101c] px-3 py-2">IP</th>
                <th className="bg-[#0a101c] px-3 py-2">Risk</th>
                <th className="bg-[#0a101c] px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr
                  key={l.audit_id}
                  onClick={() => openDetail(l)}
                  className={`cursor-pointer border-b border-slate-800/50 hover:bg-slate-900/40 ${
                    l.suspicious ? 'bg-rose-950/20' : ''
                  }`}
                >
                  <td className="px-3 py-2 text-slate-500">{l.timestamp?.slice(0, 19)}</td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-600">{l.audit_id?.slice(0, 8)}…</td>
                  <td className="px-3 py-2">{l.username || l.user}</td>
                  <td className="px-3 py-2 text-slate-500">{l.role || '—'}</td>
                  <td className="px-3 py-2 text-slate-400">{l.category}</td>
                  <td className="px-3 py-2 text-cyan-400">{l.action}</td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-500">{l.case_id ? `${l.case_id.slice(0, 8)}…` : '—'}</td>
                  <td className="px-3 py-2 font-mono text-slate-400">{l.entity_type || l.entity}</td>
                  <td className="px-3 py-2 text-slate-500">{l.device || '—'} / {l.browser || '—'}</td>
                  <td className="px-3 py-2 text-slate-600">{l.ip}</td>
                  <td className="px-3 py-2">{riskBadge(l.risk_level)}</td>
                  <td className={`px-3 py-2 ${l.result !== 'success' ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {l.suspicious ? '⚠ ' : ''}{l.result}
                  </td>
                </tr>
              ))}
            </tbody>
              </table>
          </div>
        )}
      </div>

      {selected && <DetailDrawer entry={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
