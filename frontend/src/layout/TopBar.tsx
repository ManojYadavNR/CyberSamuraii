import { useEffect, useMemo, useState } from 'react';
import { fetchCases, fetchNotifications, markAllNotificationsRead, markNotificationRead, type NotificationItem } from '../api/enterprise';
import { useAuthStore } from '../store/authStore';
import { useInvestigationStore } from '../store/investigationStore';
import { useUiStore } from '../store/uiStore';
import { CaseSelector } from '../components/CaseSelector';
import { SystemStatus } from '../components/SystemStatus';
import { UserProfileMenu } from '../components/UserProfileMenu';
import type { CaseOut } from '../types/enterprise';

export function TopBar() {
  const user = useAuthStore((s) => s.user);
  const activeCaseId = useAuthStore((s) => s.activeCaseId);
  const selectedCaseId = useUiStore((s) => s.selectedCaseId);
  const currentCaseId = activeCaseId || selectedCaseId;
  const openCase = useUiStore((s) => s.openCase);
  const setPage = useUiStore((s) => s.setPage);
  const setCaseWorkspaceTab = useUiStore((s) => s.setCaseWorkspaceTab);
  const setPrefillSearch = useUiStore((s) => s.setPrefillSearch);
  const setQuery = useInvestigationStore((s) => s.setQuery);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [showNotes, setShowNotes] = useState(false);
  const [search, setSearch] = useState('');
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [showSearch, setShowSearch] = useState(false);

  useEffect(() => {
    if (!user) return;
    fetchCases().then(setCases).catch(() => setCases([]));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    const token = useAuthStore.getState().accessToken;
    const base = import.meta.env.VITE_API_URL || '';
    let es: EventSource | null = null;
    if (token) {
      es = new EventSource(`${base}/api/notifications/stream?token=${encodeURIComponent(token)}`);
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          setNotifications(data.notifications || []);
        } catch { /* ignore */ }
      };
    }
    const poll = () => fetchNotifications().then((d) => setNotifications(d.notifications.filter((n) => !n.read))).catch(() => {});
    poll();
    const t = setInterval(poll, 60000);
    return () => { es?.close(); clearInterval(t); };
  }, [user]);

  const searchHits = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [];
    return cases.filter((c) =>
      c.title.toLowerCase().includes(q)
      || c.case_number.toLowerCase().includes(q)
      || c.case_id.toLowerCase().includes(q),
    ).slice(0, 8);
  }, [search, cases]);

  const unread = notifications.length;

  const handleSearchAction = (action: 'investigate' | string) => {
    if (action === 'investigate') {
      setQuery(search.trim());
      setPrefillSearch(search.trim());
      setPage('case-workspace');
      setCaseWorkspaceTab('investigate');
      setShowSearch(false);
      return;
    }
    openCase(action);
    setSearch('');
    setShowSearch(false);
  };

  return (
    <header className="z-30 flex h-16 shrink-0 items-center justify-between border-b border-slate-800/80 bg-[#070b14] px-5">
      <div className="relative flex items-center gap-3">
        <input
          type="search"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setShowSearch(true); }}
          onFocus={() => setShowSearch(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && search.trim()) handleSearchAction('investigate');
          }}
          placeholder="Search cases, targets…"
          className="w-72 rounded-lg border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500"
        />
        {showSearch && search.trim() && (
          <div className="absolute left-0 top-full z-50 mt-1 w-80 rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-xl">
            {searchHits.map((c) => (
              <button key={c.case_id} type="button" onClick={() => handleSearchAction(c.case_id)} className="block w-full rounded px-2 py-2 text-left text-xs hover:bg-slate-800">
                <span className="font-mono text-cyan-400">{c.case_number}</span> — {c.title}
              </button>
            ))}
            <button type="button" onClick={() => handleSearchAction('investigate')} className="mt-1 block w-full rounded bg-cyan-900/30 px-2 py-2 text-left text-xs text-cyan-300 hover:bg-cyan-900/50">
              Investigate target: <strong>{search.trim()}</strong>
            </button>
          </div>
        )}
        <CaseSelector />
        {currentCaseId && (
          <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-cyan-300">
            Case active
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <SystemStatus />
        <div className="relative">
          <button type="button" onClick={() => setShowNotes(!showNotes)} className="relative rounded-lg border border-slate-700 px-2.5 py-1.5 text-sm text-slate-300 hover:bg-slate-800">
            🔔
            {unread > 0 && <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[9px] font-bold text-white">{unread}</span>}
          </button>
          {showNotes && (
            <div className="absolute right-0 top-full z-50 mt-1 w-80 rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-xl">
              <div className="mb-2 flex justify-between px-2">
                <span className="text-[10px] uppercase text-slate-500">Notifications</span>
                {unread > 0 && (
                  <button type="button" onClick={() => markAllNotificationsRead().then(() => setNotifications([]))} className="text-[10px] text-cyan-400">Mark all read</button>
                )}
              </div>
              {notifications.length === 0 ? (
                <p className="p-3 text-xs text-slate-500">No new notifications</p>
              ) : (
                notifications.map((n) => (
                  <button
                    key={n.notification_id}
                    type="button"
                    className="block w-full rounded-lg p-2 text-left hover:bg-slate-800"
                    onClick={() => { markNotificationRead(n.notification_id); setNotifications((prev) => prev.filter((x) => x.notification_id !== n.notification_id)); if (n.case_id) openCase(n.case_id); }}
                  >
                    <p className="text-xs font-semibold text-white">{n.title}</p>
                    <p className="text-[10px] text-slate-400">{n.body}</p>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
        {user && <UserProfileMenu user={user} />}
      </div>
    </header>
  );
}
