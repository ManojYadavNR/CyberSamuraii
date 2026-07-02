import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createUser,
  decidePasswordResetAdmin,
  decidePasswordResetSupervisor,
  fetchAgencies,
  fetchAuditLogs,
  fetchMetrics,
  fetchPasswordResetRequests,
  fetchPendingApprovals,
  fetchUsers,
} from '../api/enterprise';
import type { AuditLogEntry, PasswordResetRequestRow } from '../types/enterprise';
import { LoadingTransition } from '../components/loading';
import { useAuthStore } from '../store/authStore';
import { IamPageHeader } from '../components/admin/IamPageHeader';
import { IamKpiStrip, type IamKpi } from '../components/admin/IamKpiStrip';
import { IamSectionNav } from '../components/admin/IamSectionNav';
import { CreateUserWizard } from '../components/admin/CreateUserWizard';
import { UserGrid } from '../components/admin/UserGrid';
import { PasswordResetWorkflow } from '../components/admin/PasswordResetWorkflow';
import { ActiveSessionsTable } from '../components/admin/ActiveSessionsTable';
import { AuditActivityFeed } from '../components/admin/AuditActivityFeed';
import { OrganizationPanel, PlaceholderCards } from '../components/admin/OrganizationPanel';
import { RolePermissionsPanel } from '../components/admin/RolePermissionsPanel';
import { UserDetailModal } from '../components/admin/UserDetailModal';
import { exportUsersCsv, sessionsFromAudit } from '../components/admin/iamHelpers';
import type { IamSection, IamUser } from '../components/admin/iamTypes';

const SUPERVISOR_ROLES = new Set(['SP', 'DSP', 'INSPECTOR', 'CID_DIRECTOR', 'SUPER_ADMIN']);
const ADMIN_ROLES = new Set(['SUPER_ADMIN', 'CID_DIRECTOR']);

function normalizeUser(raw: Record<string, unknown>): IamUser {
  return {
    user_id: String(raw.user_id || ''),
    username: String(raw.username || ''),
    name: String(raw.name || ''),
    email: String(raw.email || ''),
    role: String(raw.role || ''),
    department: String(raw.department || ''),
    designation: String(raw.designation || ''),
    employee_id: String(raw.employee_id || ''),
    badge_number: String(raw.badge_number || ''),
    active: raw.active !== false,
    last_login: raw.last_login ? String(raw.last_login) : null,
    must_change_password: Boolean(raw.must_change_password),
    mfa_enabled: Boolean(raw.mfa_enabled),
  };
}

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

export function AdminPage() {
  const user = useAuthStore((s) => s.user);
  const [activeSection, setActiveSection] = useState<IamSection>('identity');
  const [users, setUsers] = useState<IamUser[]>([]);
  const [agencies, setAgencies] = useState<{ id: string; name: string; code?: string }[]>([]);
  const [resetRequests, setResetRequests] = useState<PasswordResetRequestRow[]>([]);
  const [authLogs, setAuthLogs] = useState<AuditLogEntry[]>([]);
  const [securityLogs, setSecurityLogs] = useState<AuditLogEntry[]>([]);
  const [auditTodayTotal, setAuditTodayTotal] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [pendingApprovals, setPendingApprovals] = useState(0);
  const [investigatorsOnline, setInvestigatorsOnline] = useState(0);
  const [loading, setLoading] = useState(true);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [viewUser, setViewUser] = useState<IamUser | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [lastTempPassword, setLastTempPassword] = useState('');

  const canSupervise = Boolean(user && SUPERVISOR_ROLES.has(user.role));
  const canAdmin = Boolean(user && ADMIN_ROLES.has(user.role));

  const reload = useCallback(() => {
    setLoading(true);
    setLoadError('');
    const todayStart = `${todayIsoDate()}T00:00:00`;
    const tasks: Promise<void>[] = [
      fetchUsers()
        .then((u) => setUsers((u as Record<string, unknown>[]).map(normalizeUser)))
        .catch(() => { setUsers([]); setLoadError('Unable to load users'); }),
      fetchAgencies()
        .then((a) => setAgencies(a.agencies || []))
        .catch(() => setAgencies([])),
      fetchAuditLogs({ limit: 80, category: 'authentication' })
        .then((r) => setAuthLogs(r.logs || []))
        .catch(() => setAuthLogs([])),
      fetchAuditLogs({ limit: 120, date_from: todayStart })
        .then((r) => setAuditTodayTotal(r.total ?? (r.logs || []).length))
        .catch(() => setAuditTodayTotal(0)),
      fetchAuditLogs({ limit: 60, category: 'user_management' })
        .then((userMgmt) =>
          fetchAuditLogs({ limit: 40, category: 'authentication' }).then((auth) => {
            const merged = [...(userMgmt.logs || []), ...(auth.logs || [])];
            const seen = new Set<string>();
            const unique = merged
              .filter((l) => {
                if (!l.audit_id || seen.has(l.audit_id)) return false;
                seen.add(l.audit_id);
                return true;
              })
              .sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));
            setSecurityLogs(unique);
          }),
        )
        .catch(() => setSecurityLogs([])),
      fetchMetrics()
        .then((m) => setInvestigatorsOnline(m.investigators_online || 0))
        .catch(() => setInvestigatorsOnline(0)),
      fetchPendingApprovals()
        .then((r) => setPendingApprovals((r.approvals || []).length))
        .catch(() => setPendingApprovals(0)),
    ];
    if (canSupervise || canAdmin) {
      tasks.push(
        fetchPasswordResetRequests()
          .then((r) => setResetRequests(r.requests || []))
          .catch(() => setResetRequests([])),
      );
    }
    void Promise.all(tasks).finally(() => setLoading(false));
  }, [canSupervise, canAdmin]);

  useEffect(() => {
    reload();
  }, [reload]);

  const pendingResets = useMemo(
    () => resetRequests.filter((r) => r.status === 'pending_supervisor' || r.status === 'pending_admin').length,
    [resetRequests],
  );

  const lockedAccounts = useMemo(
    () => users.filter((u) => !u.active || u.must_change_password).length,
    [users],
  );

  const activeSessions = useMemo(
    () => sessionsFromAudit(authLogs, users).length,
    [authLogs, users],
  );

  const kpis: IamKpi[] = useMemo(
    () => [
      { id: 'users', icon: '👥', label: 'Total Users', value: users.length, description: 'Provisioned investigator accounts' },
      { id: 'sessions', icon: '📡', label: 'Active Sessions', value: activeSessions, description: 'From recent auth events', trend: activeSessions > 0 ? 'Live' : undefined },
      { id: 'locked', icon: '🔒', label: 'Locked Accounts', value: lockedAccounts, description: 'Disabled or restricted' },
      { id: 'resets', icon: '🔑', label: 'Pending Resets', value: pendingResets, description: 'Awaiting approval workflow' },
      { id: 'approvals', icon: '✓', label: 'Pending Approvals', value: pendingApprovals, description: 'Investigation review queue' },
      { id: 'audit', icon: '📋', label: 'Audit Events Today', value: auditTodayTotal, description: 'Platform-wide audit events' },
      { id: 'online', icon: '🟢', label: 'Online Investigators', value: investigatorsOnline, description: 'Currently active in platform' },
    ],
    [users.length, activeSessions, lockedAccounts, pendingResets, pendingApprovals, auditTodayTotal, investigatorsOnline],
  );

  const mfaEnabled = users.filter((u) => u.mfa_enabled).length;
  const failedLogins = authLogs.filter((l) => l.action === 'login' && l.result === 'failed').length;

  const handleCreate = async (payload: Record<string, string>) => {
    await createUser(payload);
    reload();
  };

  const handleSupervisor = async (requestId: string, approve: boolean) => {
    await decidePasswordResetSupervisor(requestId, approve, notes[requestId] || '');
    reload();
  };

  const handleAdmin = async (requestId: string, approve: boolean) => {
    const r = await decidePasswordResetAdmin(requestId, approve, notes[requestId] || '');
    if (r.temporary_password) setLastTempPassword(r.temporary_password);
    reload();
  };

  return (
    <div className="iam-console iam-console--viewport">
      <div className="iam-console__head">
        <div className="iam-page-top">
          <IamPageHeader
            onCreateUser={() => setWizardOpen(true)}
            onExport={() => exportUsersCsv(users)}
          />
          <IamSectionNav active={activeSection} onSelect={setActiveSection} />
        </div>

        {loadError && (
          <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-950/30 px-4 py-2 text-sm text-rose-200">
            {loadError}
          </div>
        )}
      </div>

      <div className="iam-console__body">
        <IamKpiStrip kpis={kpis} loading={loading && users.length === 0} />
      <LoadingTransition loading={loading && users.length === 0} fallback={null}>
        <>
          {/* Identity & Access */}
          <section id="iam-section-identity" className="iam-section">
            <div className="iam-section-head">
              <h2 className="iam-section-title">Identity & Access</h2>
              <p className="iam-section-desc">Manage investigator identities, roles, sessions, and account status.</p>
            </div>
            <div className="iam-card iam-card--users mb-6 overflow-hidden">
              <h3 className="mb-1 shrink-0 text-sm font-semibold text-white">Users</h3>
              <p className="mb-4 shrink-0 text-xs text-slate-500">
                Enterprise user directory. Use pagination and role filters to browse all accounts. Click a row to view role and permissions.
              </p>
              <UserGrid users={users} onView={setViewUser} />
            </div>
            <RolePermissionsPanel users={users} onCreateUser={() => setWizardOpen(true)} />
            <div className="iam-card-grid mt-6">
              <div className="iam-card col-span-full">
                <h3 className="mb-1 text-sm font-semibold text-white">Active Sessions</h3>
                <p className="mb-4 text-xs text-slate-500">Live authentication sessions derived from the audit trail.</p>
                <ActiveSessionsTable auditLogs={authLogs} users={users} />
              </div>
              <div className="iam-card">
                <h3 className="mb-3 text-sm font-semibold text-white">Locked Accounts</h3>
                <p className="text-3xl font-bold text-white">{lockedAccounts}</p>
                <p className="mt-1 text-xs text-slate-500">Accounts marked inactive or restricted.</p>
              </div>
            </div>
          </section>

          {/* Organization */}
          <section id="iam-section-organization" className="iam-section">
            <div className="iam-section-head">
              <h2 className="iam-section-title">Organization</h2>
              <p className="iam-section-desc">Agencies, departments, districts, and jurisdictional boundaries.</p>
            </div>
            <OrganizationPanel agencies={agencies} users={users} />
          </section>

          {/* Security */}
          <section id="iam-section-security" className="iam-section">
            <div className="iam-section-head">
              <h2 className="iam-section-title">Security</h2>
              <p className="iam-section-desc">Password workflows, MFA posture, authentication monitoring, and lockouts.</p>
            </div>
            <div className="iam-card mb-6">
              <h3 className="mb-1 text-sm font-semibold text-white">Password Reset Requests</h3>
              <p className="mb-4 text-xs text-slate-500">
                CID workflow: investigator requests → supervisor verifies → admin issues temporary password → forced change on login.
              </p>
              {(canSupervise || canAdmin) ? (
                <PasswordResetWorkflow
                  requests={resetRequests}
                  canSupervise={canSupervise}
                  canAdmin={canAdmin}
                  notes={notes}
                  onNotesChange={(id, v) => setNotes({ ...notes, [id]: v })}
                  onSupervisor={handleSupervisor}
                  onAdmin={handleAdmin}
                  lastTempPassword={lastTempPassword}
                />
              ) : (
                <div className="iam-empty">
                  <p className="iam-empty-desc">Supervisor or administrator role required to manage password reset workflow.</p>
                </div>
              )}
            </div>
            <PlaceholderCards
              items={[
                { title: 'MFA Status', desc: `${mfaEnabled} of ${users.length} accounts have MFA enabled`, icon: '🛡️', status: 'Policy managed' },
                { title: 'Login Attempts', desc: `${failedLogins} failed attempts in recent auth audit window`, icon: '🔐' },
                { title: 'Account Lockouts', desc: 'Derived from authentication policy and failed login thresholds', icon: '⛔', status: 'Monitor via audit' },
              ]}
            />
          </section>

          {/* System */}
          <section id="iam-section-system" className="iam-section">
            <div className="iam-section-head">
              <h2 className="iam-section-title">System</h2>
              <p className="iam-section-desc">Audit visibility, API access, integrations, and platform configuration.</p>
            </div>
            <PlaceholderCards
              items={[
                { title: 'Audit Logs', desc: 'Full tamper-evident audit trail with hash chain verification', icon: '📜', status: 'Available' },
                { title: 'API Keys', desc: 'Intel API credentials and service accounts', icon: '🔑', status: 'Coming soon' },
                { title: 'Integrations', desc: 'External OSINT tools and enterprise connectors', icon: '🔗', status: 'Configure in Tools' },
                { title: 'Configuration', desc: 'Platform-wide security and investigation policies', icon: '⚙️', status: 'Admin only' },
              ]}
            />
            <div className="iam-card mt-6">
              <AuditActivityFeed logs={securityLogs.length > 0 ? securityLogs : authLogs} />
            </div>
          </section>
        </>
      </LoadingTransition>
      </div>

      <CreateUserWizard
        open={wizardOpen}
        agencies={agencies}
        onClose={() => setWizardOpen(false)}
        onSubmit={handleCreate}
      />
      <UserDetailModal user={viewUser} onClose={() => setViewUser(null)} onUpdated={reload} />
    </div>
  );
}
