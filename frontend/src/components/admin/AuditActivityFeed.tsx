import { securityEventsFromAudit } from './iamHelpers';
import type { AuditLogEntry } from '../../types/enterprise';
import { useUiStore } from '../../store/uiStore';

export function AuditActivityFeed({ logs }: { logs: AuditLogEntry[] }) {
  const setPage = useUiStore((s) => s.setPage);
  const events = securityEventsFromAudit(logs).slice(0, 12);

  if (events.length === 0) {
    return (
      <div className="iam-empty">
        <div className="iam-empty-icon">📋</div>
        <p className="iam-empty-title">No recent security activity</p>
        <p className="iam-empty-desc">Authentication and user management events will appear here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Recent Security Activity</h3>
        <button type="button" className="iam-btn-sm" onClick={() => setPage('audit')}>View all audit logs</button>
      </div>
      {events.map((ev) => (
        <div key={ev.id} className="iam-activity-item fade-in">
          <div className="text-xl">{ev.icon}</div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-200">{ev.description}</span>
              <span className={`iam-severity iam-severity--${ev.severity}`}>{ev.severity}</span>
              {ev.result === 'failed' && <span className="text-[10px] text-rose-400">FAILED</span>}
            </div>
            <p className="mt-0.5 text-xs text-slate-500">
              {ev.timestamp?.slice(0, 19).replace('T', ' ')} · {ev.user || 'system'}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
