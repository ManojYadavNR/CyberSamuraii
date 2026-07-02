import { useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { useAuthStore } from '../store/authStore';
import { useUiStore } from '../store/uiStore';
import { DashboardPage } from '../pages/DashboardPage';
import { CasesPage } from '../pages/CasesPage';
import { CaseWorkspacePage } from '../pages/CaseWorkspacePage';
import { InvestigationHubPage } from '../pages/InvestigationHubPage';
import { AdminPage } from '../pages/AdminPage';
import { AuditPage } from '../pages/AuditPage';
import { PasswordResetPage } from '../pages/PasswordResetPage';
import { PasswordChangePage } from '../pages/PasswordChangePage';
import { PendingApprovalsPage } from '../pages/PendingApprovalsPage';
import { IntelApiPage } from '../pages/IntelApiPage';
import { ToolsPage } from '../pages/ToolsPage';
import { InvestigatorDashboard } from '../components/InvestigatorDashboard';
import { OsintFrameworkPage } from '../components/OsintFrameworkPage';
import { PageTransition } from '../components/loading';

const SESSION_TIMEOUT_MS = 60 * 60 * 1000;

export function AppShell() {
  const page = useUiStore((s) => s.page);
  const enterpriseAuth = useAuthStore((s) => s.enterpriseAuth);

  useEffect(() => {
    const persisted = useUiStore.getState().selectedCaseId;
    if (persisted && !useAuthStore.getState().activeCaseId) {
      useAuthStore.getState().setActiveCase(persisted);
    }
  }, []);

  useEffect(() => {
    if (!enterpriseAuth) return;
    const check = () => {
      const raw = localStorage.getItem('socmint-auth');
      if (!raw) return;
      try {
        const data = JSON.parse(raw);
        const last = data?.state?.lastActivity as number | undefined;
        if (last && Date.now() - last > SESSION_TIMEOUT_MS) {
          import('../api/auth').then(({ logoutSession }) => logoutSession());
        }
      } catch { /* ignore */ }
    };
    const bump = () => useAuthStore.setState({ lastActivity: Date.now() });
    bump();
    window.addEventListener('click', bump);
    window.addEventListener('keydown', bump);
    const t = setInterval(check, 60000);
    return () => { window.removeEventListener('click', bump); window.removeEventListener('keydown', bump); clearInterval(t); };
  }, [enterpriseAuth]);

  let content;
  switch (page) {
    case 'dashboard': content = <DashboardPage />; break;
    case 'investigator-dashboard': content = <div className="intel-panel rounded-xl p-4"><InvestigatorDashboard /></div>; break;
    case 'cases': content = <CasesPage />; break;
    case 'case-workspace': content = <CaseWorkspacePage />; break;
    case 'investigations':
    case 'graph':
    case 'evidence':
    case 'reports':
      content = <InvestigationHubPage mode={page} />; break;
    case 'osint-framework': content = <OsintFrameworkPage />; break;
    case 'tools': content = <ToolsPage />; break;
    case 'intel-api': content = <IntelApiPage />; break;
    case 'pending-approvals': content = <PendingApprovalsPage />; break;
    case 'admin': content = <AdminPage />; break;
    case 'audit': content = <AuditPage />; break;
    case 'password-reset': content = <PasswordResetPage />; break;
    case 'change-password': content = <PasswordChangePage />; break;
    default: content = <DashboardPage />;
  }

  const scrollContained = page === 'audit' || page === 'admin' || page === 'case-workspace' || page === 'dashboard' || page === 'cases'
    || page === 'pending-approvals' || page === 'intel-api' || page === 'tools' || page === 'osint-framework';

  return (
    <div className="h-screen overflow-hidden bg-[#070b14] text-slate-200">
      <Sidebar />
      <div className="flex h-screen min-w-0 flex-col pl-64">
        <TopBar />
        <main
          className={`theme-shell-scroll min-h-0 flex-1 px-5 pb-6 pt-2 scroll-smooth ${
            scrollContained ? 'flex flex-col overflow-hidden' : 'overflow-y-auto overflow-x-hidden'
          }`}
        >
          <PageTransition pageKey={page} contained={scrollContained}>{content}</PageTransition>
        </main>
      </div>
    </div>
  );
}
