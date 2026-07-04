import type { IntelSelectOption } from '../ui/IntelSelect';
import type { AuditLogEntry } from '../../types/enterprise';
import type { IamUser } from './iamTypes';
import { getCachedRbacConfig, organizationalRankOptions } from '../../lib/permissions';

export function rankSelectOptions(): IntelSelectOption[] {
  return organizationalRankOptions().map((rank) => ({
    value: rank.code,
    label: rank.label,
  }));
}

export function roleSelectOptions(): IntelSelectOption[] {
  return rankSelectOptions();
}

export function agencySelectOptions(
  agencies: { id: string; name: string; code?: string }[],
): IntelSelectOption[] {
  if (agencies.length === 0) return [{ value: 'HQ', label: 'Agency Headquarters' }];
  return agencies.map((agency) => ({
    value: agency.code || agency.name,
    label: agency.name,
  }));
}

const ROLE_STYLES: Record<string, string> = {
  SUPER_ADMIN: 'iam-role--critical',
  DGP: 'iam-role--director',
  ADGP: 'iam-role--director',
  IGP: 'iam-role--director',
  DIG: 'iam-role--dsp',
  SP: 'iam-role--sp',
  DSP: 'iam-role--dsp',
  PI: 'iam-role--inspector',
  PSI: 'iam-role--inspector',
  HC: 'iam-role--analyst',
  PC: 'iam-role--viewer',
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

export function supervisorRolesFromConfig(): Set<string> {
  const wf = getCachedRbacConfig()?.workflow as { supervisor_ranks?: string[] } | undefined;
  const ranks = wf?.supervisor_ranks || ['SP', 'DSP', 'PI', 'DIG', 'IGP', 'ADGP', 'DGP'];
  return new Set([...ranks, 'SUPER_ADMIN']);
}

export function adminRolesFromConfig(): Set<string> {
  const wf = getCachedRbacConfig()?.workflow as { admin_ranks?: string[] } | undefined;
  const ranks = wf?.admin_ranks || ['DGP', 'ADGP'];
  return new Set([...ranks, 'SUPER_ADMIN']);
}

export function exportUsersCsv(users: IamUser[]) {
  const header = 'name,username,email,role,rank_code,department,designation,active,last_login';
  const rows = users.map((u) =>
    [u.name, u.username, u.email, u.role, u.rank_code || u.role, u.department, u.designation, u.active, u.last_login || '']
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
