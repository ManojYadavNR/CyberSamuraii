import type { IntelSelectOption } from '../ui/IntelSelect';
import type { AuditLogEntry } from '../../types/enterprise';
import type { IamUser } from './iamTypes';

export const IAM_ROLES = [
  'ANALYST',
  'INSPECTOR',
  'DSP',
  'SP',
  'VIEWER',
  'AUDITOR',
  'CID_DIRECTOR',
  'SUPER_ADMIN',
] as const;

export function roleSelectOptions(): IntelSelectOption[] {
  return IAM_ROLES.map((role) => ({
    value: role,
    label: role.replace(/_/g, ' '),
  }));
}

export function agencySelectOptions(
  agencies: { id: string; name: string; code?: string }[],
): IntelSelectOption[] {
  if (agencies.length === 0) return [{ value: 'CID', label: 'CID' }];
  return agencies.map((agency) => ({
    value: agency.code || agency.name,
    label: agency.name,
  }));
}

const ROLE_STYLES: Record<string, string> = {
  SUPER_ADMIN: 'iam-role--critical',
  CID_DIRECTOR: 'iam-role--director',
  SP: 'iam-role--sp',
  DSP: 'iam-role--dsp',
  INSPECTOR: 'iam-role--inspector',
  SUB_INSPECTOR: 'iam-role--inspector',
  ANALYST: 'iam-role--analyst',
  INTELLIGENCE_OFFICER: 'iam-role--analyst',
  FORENSICS_OFFICER: 'iam-role--analyst',
  VIEWER: 'iam-role--viewer',
  AUDITOR: 'iam-role--viewer',
};

export function userInitials(user: Pick<IamUser, 'name' | 'username'>): string {
  const base = (user.name || user.username || 'U').trim();
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return base.slice(0, 2).toUpperCase();
}

export function roleBadgeClass(role: string): string {
  return ROLE_STYLES[role] || 'iam-role--analyst';
}

export function userStatus(user: IamUser): { label: string; className: string } {
  if (!user.active) return { label: 'Disabled', className: 'iam-status--disabled' };
  if (user.must_change_password) return { label: 'Suspended', className: 'iam-status--suspended' };
  return { label: 'Active', className: 'iam-status--active' };
}

export function exportUsersCsv(users: IamUser[]) {
  const header = 'name,username,email,role,department,designation,active,last_login';
  const rows = users.map((u) =>
    [u.name, u.username, u.email, u.role, u.department, u.designation, u.active, u.last_login || '']
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(','),
  );
  const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `iam_users_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function securityEventsFromAudit(logs: AuditLogEntry[]) {
  const map: Record<string, { icon: string; label: string; severity: string }> = {
    create_user: { icon: '👤', label: 'User Created', severity: 'medium' },
    update_user: { icon: '✏️', label: 'User Updated', severity: 'medium' },
    password_reset_admin_approve: { icon: '🔑', label: 'Password Reset', severity: 'high' },
    password_reset_admin_deny: { icon: '🔑', label: 'Password Reset Denied', severity: 'medium' },
    password_reset_supervisor_approve: { icon: '✓', label: 'Supervisor Approved Reset', severity: 'medium' },
    password_reset_supervisor_deny: { icon: '✗', label: 'Supervisor Denied Reset', severity: 'medium' },
    password_reset_workflow_request: { icon: '🔑', label: 'Password Reset Request', severity: 'medium' },
    password_change: { icon: '🔐', label: 'Password Changed', severity: 'medium' },
    login: { icon: '🔐', label: 'Login', severity: 'low' },
    logout: { icon: '⎋', label: 'Session Terminated', severity: 'low' },
  };
  return logs.map((log) => {
    const meta = map[log.action] || { icon: '📋', label: log.action, severity: 'low' };
    const sev = log.result === 'failed' || log.result === 'denied' ? 'high' : meta.severity;
    return {
      id: log.audit_id,
      icon: log.result === 'failed' ? '⚠️' : meta.icon,
      timestamp: log.timestamp,
      user: log.username || log.user,
      description: `${meta.label} — ${log.entity || log.entity_id || 'system'}`,
      severity: sev,
      result: log.result,
    };
  });
}

export function sessionsFromAudit(logs: AuditLogEntry[], users: IamUser[]) {
  const byUser = new Map(users.map((u) => [u.username, u]));
  return logs
    .filter((l) => l.action === 'login' && l.result === 'success')
    .slice(0, 12)
    .map((l, i) => {
      const u = byUser.get(l.username);
      return {
        id: l.audit_id || `sess-${i}`,
        user: l.username || l.user,
        name: u?.name || l.username,
        device: l.device || 'Desktop',
        os: l.os || '—',
        browser: l.browser || '—',
        location: l.location_approx || l.ip || '—',
        ip: l.ip,
        loginTime: l.timestamp,
        lastActivity: l.timestamp,
        current: i === 0,
      };
    });
}
