import { useEffect, useMemo, useState, type ReactNode } from 'react';
import type { IconType } from 'react-icons';
import {
  LuActivity,
  LuClipboardCheck,
  LuFolderOpen,
  LuFolderPlus,
  LuFolders,
  LuKeyRound,
  LuLogIn,
  LuLogOut,
  LuRadar,
  LuRefreshCw,
  LuSearch,
  LuTriangleAlert,
  LuUpload,
  LuUsers,
} from 'react-icons/lu';
import { fetchCases, fetchMetrics, fetchPendingApprovals, type ApprovalRecord, type DashboardMetrics } from '../api/enterprise';
import { formatCaseDate } from '../components/CaseEditModal';
import { NavIcon } from '../components/icons/NavIcons';
import { DashboardSkeleton, LoadingTransition } from '../components/loading';
import { useAuthStore } from '../store/authStore';
import { useUiStore, type AppPage } from '../store/uiStore';
import type { CaseOut } from '../types/enterprise';

type KpiTone = 'cyan' | 'blue' | 'emerald' | 'violet' | 'rose' | 'amber';

interface KpiCard {
  label: string;
  value: number;
  tone: KpiTone;
  hint: string;
  Icon: IconType;
  action?: () => void;
}

function formatActivityTime(ts?: string): string {
  if (!ts) return '—';
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return ts.slice(0, 16).replace('T', ' ');
  const diff = Date.now() - date.getTime();
  if (diff < 60_000) return 'Just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function activityIconNode(action: string): ReactNode {
  const cls = 'h-4 w-4';
  if (action.includes('login')) return <LuLogIn className={cls} />;
  if (action.includes('logout')) return <LuLogOut className={cls} />;
  if (action.includes('token')) return <LuRefreshCw className={cls} />;
  if (action.includes('case')) return <LuFolderOpen className={cls} />;
  if (action.includes('investig')) return <LuSearch className={cls} />;
  if (action.includes('export')) return <LuUpload className={cls} />;
  if (action.includes('password')) return <LuKeyRound className={cls} />;
  return <LuActivity className={cls} />;
}

function activityLabel(action: string, entity?: string): string {
  const base = action.replace(/_/g, ' ');
  return entity ? `${base} · ${entity}` : base;
}

export function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [pending, setPending] = useState<ApprovalRecord[]>([]);
  const [recentCases, setRecentCases] = useState<CaseOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [clock, setClock] = useState(() => new Date());
  const user = useAuthStore((s) => s.user);
  const openCase = useUiStore((s) => s.openCase);
  const setPage = useUiStore((s) => s.setPage);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchMetrics().then(setMetrics).catch(() => setMetrics(null)),
      fetchPendingApprovals().then((d) => setPending(d.approvals || [])).catch(() => setPending([])),
      fetchCases().then((rows) => setRecentCases(rows.slice(0, 5))).catch(() => setRecentCases([])),
    ]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  const cards: KpiCard[] = useMemo(() => metrics ? [
    { label: 'Active Cases', value: metrics.active_cases, tone: 'cyan', hint: 'Open pipeline', Icon: LuFolders, action: () => setPage('cases') },
    { label: 'Open Cases', value: metrics.open_cases, tone: 'blue', hint: 'Awaiting assignment', Icon: LuFolderPlus, action: () => setPage('cases') },
    { label: 'Investigators Online', value: metrics.investigators_online, tone: 'emerald', hint: 'Active sessions', Icon: LuUsers },
    { label: 'Investigations Today', value: metrics.investigations_today, tone: 'violet', hint: 'Runs started today', Icon: LuRadar, action: () => setPage('investigations') },
    { label: 'High Risk Targets', value: metrics.high_risk_targets, tone: 'rose', hint: 'Priority watchlist', Icon: LuTriangleAlert },
    { label: 'Pending Reviews', value: metrics.pending_reviews, tone: 'amber', hint: 'Needs supervisor action', Icon: LuClipboardCheck, action: () => setPage('pending-approvals') },
  ] : [], [metrics, setPage]);

  const quickActions: { label: string; page: AppPage }[] = [
    { label: 'New investigation', page: 'case-workspace' },
    { label: 'Cases', page: 'cases' },
    { label: 'Intel graph', page: 'graph' },
    { label: 'Audit logs', page: 'audit' },
    { label: 'Administration', page: 'admin' },
  ];

  const greeting = useMemo(() => {
    const h = clock.getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  }, [clock]);

  return (
      <LoadingTransition loading={loading || !metrics} fallback={<DashboardSkeleton />} className="dashboard-page__body">
      {metrics && (
        <div className="dashboard-page dashboard-page--contained">
          <section className="dashboard-hero dashboard-hero--fixed">
            <div className="dashboard-hero__copy">
              <p className="dashboard-hero__eyebrow">{greeting}{user?.name ? `, ${user.name.split(' ')[0]}` : ''}</p>
              <h1 className="dashboard-hero__title">Investigation Dashboard</h1>
              <p className="dashboard-hero__subtitle">CID operations overview — real-time case load, investigator activity, and approval queue.</p>
            </div>
            <div className="dashboard-hero__meta">
              <div className="dashboard-hero__clock">
                <span className="dashboard-hero__clock-label">Operations time</span>
                <span className="dashboard-hero__clock-value">
                  {clock.toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
              <div className="dashboard-hero__status">
                <span className="dashboard-hero__status-dot" />
                Systems nominal
              </div>
            </div>
          </section>

          <div className="dashboard-page__scroll">
          <section className="dashboard-kpi-grid stagger-fade-in">
            {cards.map((c, i) => {
              const Tag = c.action ? 'button' : 'div';
              const Icon = c.Icon;
              return (
                <Tag
                  key={c.label}
                  type={c.action ? 'button' : undefined}
                  onClick={c.action}
                  style={{ animationDelay: `${i * 50}ms` }}
                  className={`dashboard-kpi dashboard-kpi--${c.tone} ${c.action ? 'dashboard-kpi--clickable' : ''}`}
                >
                  <div className="dashboard-kpi__glow" aria-hidden />
                  <div className="dashboard-kpi__top">
                    <span className={`dashboard-kpi__icon-wrap dashboard-kpi__icon-wrap--${c.tone}`}>
                      <Icon className="dashboard-kpi__icon" aria-hidden />
                    </span>
                    <span className="dashboard-kpi__hint">{c.hint}</span>
                  </div>
                  <p className="dashboard-kpi__value">{c.value}</p>
                  <p className="dashboard-kpi__label">{c.label}</p>
                </Tag>
              );
            })}
          </section>

          <section className="dashboard-quick">
            <p className="dashboard-section-label">Quick launch</p>
            <div className="dashboard-quick__row">
              {quickActions.map((a) => (
                <button key={a.label} type="button" onClick={() => setPage(a.page)} className="dashboard-quick__btn">
                  <span className="dashboard-quick__icon-wrap">
                    <NavIcon page={a.page} className="h-4 w-4" />
                  </span>
                  {a.label}
                </button>
              ))}
            </div>
          </section>

          <div className="dashboard-panels">
            <section className="dashboard-panel dashboard-panel--wide">
              <div className="dashboard-panel__head">
                <div>
                  <h2 className="dashboard-panel__title">Recent activity</h2>
                  <p className="dashboard-panel__desc">Authentication, case, and investigation events</p>
                </div>
                <button type="button" onClick={() => setPage('audit')} className="dashboard-panel__link">View audit</button>
              </div>
              <ul className="dashboard-activity">
                {(metrics.recent_activity || []).length === 0 ? (
                  <li className="dashboard-activity__empty">No recent activity recorded.</li>
                ) : (metrics.recent_activity || []).slice(0, 12).map((a, i) => (
                  <li key={`${a.timestamp}-${i}`} className="dashboard-activity__row">
                    <span className="dashboard-activity__icon" aria-hidden>{activityIconNode(a.action)}</span>
                    <div className="dashboard-activity__body">
                      <p className="dashboard-activity__user">{a.user || 'system'}</p>
                      <p className="dashboard-activity__action">{activityLabel(a.action, a.entity)}</p>
                    </div>
                    <time className="dashboard-activity__time" dateTime={a.timestamp}>{formatActivityTime(a.timestamp)}</time>
                  </li>
                ))}
              </ul>
            </section>

            <div className="dashboard-panel-stack">
              <section className="dashboard-panel">
                <div className="dashboard-panel__head">
                  <div>
                    <h2 className="dashboard-panel__title">Pending approvals</h2>
                    <p className="dashboard-panel__desc">{pending.length} item{pending.length === 1 ? '' : 's'} awaiting review</p>
                  </div>
                  <button type="button" onClick={() => setPage('pending-approvals')} className="dashboard-panel__link">View all</button>
                </div>
                {pending.length === 0 && (metrics.work_queue || []).length === 0 ? (
                  <p className="dashboard-panel__empty">No pending items — queue is clear.</p>
                ) : (
                  <ul className="dashboard-queue">
                    {pending.slice(0, 5).map((w) => (
                      <li key={w.approval_id}>
                        <button type="button" onClick={() => openCase(w.case_id)} className="dashboard-queue__item">
                          <span className="dashboard-queue__badge">Approval</span>
                          <span className="dashboard-queue__text">{w.stage} — cluster {w.cluster_id?.slice(0, 10)}…</span>
                        </button>
                      </li>
                    ))}
                    {(metrics.work_queue || []).slice(0, 4).map((w) => (
                      <li key={w.id}>
                        <button type="button" onClick={() => openCase(w.case_id)} className="dashboard-queue__item">
                          <span className="dashboard-queue__badge dashboard-queue__badge--work">{w.type}</span>
                          <span className="dashboard-queue__text">Stage {w.stage || '—'}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="dashboard-panel">
                <div className="dashboard-panel__head">
                  <div>
                    <h2 className="dashboard-panel__title">Recent cases</h2>
                    <p className="dashboard-panel__desc">Latest investigation files</p>
                  </div>
                  <button type="button" onClick={() => setPage('cases')} className="dashboard-panel__link">All cases</button>
                </div>
                {recentCases.length === 0 ? (
                  <p className="dashboard-panel__empty">No cases yet — create one to begin.</p>
                ) : (
                  <ul className="dashboard-cases">
                    {recentCases.map((c) => (
                      <li key={c.case_id}>
                        <button
                          type="button"
                          onClick={() => openCase(c.case_id, { case_number: c.case_number, title: c.title })}
                          className="dashboard-cases__item"
                        >
                          <span className="dashboard-cases__id">{c.case_number}</span>
                          <span className="dashboard-cases__title">{c.title}</span>
                          <span className="dashboard-cases__meta">{formatCaseDate(c.created_at)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          </div>
          </div>
        </div>
      )}
    </LoadingTransition>
  );
}
