import { useAuthStore } from '../store/authStore';
import { useUiStore, type AppPage } from '../store/uiStore';
import { hasPermission } from '../lib/permissions';
import { NavIcon } from '../components/icons/NavIcons';
import { LuShield } from 'react-icons/lu';

const NAV: { id: AppPage; label: string; permission?: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'investigator-dashboard', label: 'Intel Overview', permission: 'view_investigations' },
  { id: 'cases', label: 'Cases', permission: 'view_cases' },
  { id: 'case-workspace', label: 'Workspace', permission: 'view_cases' },
  { id: 'investigations', label: 'Investigations', permission: 'view_investigations' },
  { id: 'graph', label: 'Intelligence Graph', permission: 'view_investigations' },
  { id: 'evidence', label: 'Evidence', permission: 'view_cases' },
  { id: 'reports', label: 'Reports', permission: 'export_evidence' },
  { id: 'osint-framework', label: 'OSINT Framework', permission: 'view_investigations' },
  { id: 'tools', label: 'Tools', permission: 'view_investigations' },
  { id: 'intel-api', label: 'Intel API', permission: 'start_investigation' },
  { id: 'pending-approvals', label: 'Approvals', permission: 'approve_evidence' },
  { id: 'audit', label: 'Audit Logs', permission: 'view_audit_logs' },
  { id: 'admin', label: 'Administration', permission: 'manage_users' },
];

export function Sidebar() {
  const page = useUiStore((s) => s.page);
  const setPage = useUiStore((s) => s.setPage);
  const role = useAuthStore((s) => s.user?.role || 'VIEWER');

  return (
    <aside className="sidebar-shell">
      <div className="sidebar-shell__brand">
        <div className="sidebar-shell__logo">
          <LuShield className="h-5 w-5 text-white" aria-hidden />
        </div>
        <div>
          <p className="text-sm font-bold text-white">SOCMINT</p>
          <p className="text-[9px] uppercase tracking-widest text-slate-500">CID Platform</p>
        </div>
      </div>
      <nav className="sidebar-shell__nav">
        {NAV.filter((n) => !n.permission || hasPermission(role, n.permission)).map((item) => {
          const active = page === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setPage(item.id)}
              className={`sidebar-nav-item ${active ? 'sidebar-nav-item--active' : ''}`}
            >
              <span className={`sidebar-nav-item__icon ${active ? 'sidebar-nav-item__icon--active' : ''}`}>
                <NavIcon page={item.id} className="h-4 w-4" />
              </span>
              <span className="sidebar-nav-item__label">{item.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="sidebar-shell__footer">Law Enforcement Investigation System</div>
    </aside>
  );
}
