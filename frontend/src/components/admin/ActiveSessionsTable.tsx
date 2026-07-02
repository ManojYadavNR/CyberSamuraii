import { sessionsFromAudit } from './iamHelpers';
import type { AuditLogEntry } from '../../types/enterprise';
import type { IamUser } from './iamTypes';

interface ActiveSessionsTableProps {
  auditLogs: AuditLogEntry[];
  users: IamUser[];
}

export function ActiveSessionsTable({ auditLogs, users }: ActiveSessionsTableProps) {
  const sessions = sessionsFromAudit(auditLogs, users);

  if (sessions.length === 0) {
    return (
      <div className="iam-empty">
        <div className="iam-empty-icon">📡</div>
        <p className="iam-empty-title">No active sessions detected</p>
        <p className="iam-empty-desc">Sessions are derived from recent successful authentication events in the audit trail.</p>
      </div>
    );
  }

  return (
    <div className="iam-user-grid-wrap max-h-[400px] overflow-auto">
      <table className="iam-user-grid">
        <thead>
          <tr>
            <th>User</th>
            <th>Device</th>
            <th>OS</th>
            <th>Browser</th>
            <th>Location</th>
            <th>IP</th>
            <th>Login Time</th>
            <th>Last Activity</th>
            <th>Session</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.id}>
              <td>
                <div className="font-medium text-slate-200">{s.name}</div>
                <div className="text-[11px] text-slate-500">@{s.user}</div>
              </td>
              <td>{s.device}</td>
              <td>{s.os}</td>
              <td>{s.browser}</td>
              <td>{s.location}</td>
              <td className="font-mono text-xs">{s.ip || '—'}</td>
              <td className="text-xs">{s.loginTime?.slice(0, 16).replace('T', ' ')}</td>
              <td className="text-xs">{s.lastActivity?.slice(0, 16).replace('T', ' ')}</td>
              <td>
                {s.current ? (
                  <span className="iam-status iam-status--active">Current</span>
                ) : (
                  <span className="text-xs text-slate-500">Historical</span>
                )}
              </td>
              <td>
                <button type="button" className="iam-btn-sm opacity-50" disabled title="Session termination API not available">
                  Terminate
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
