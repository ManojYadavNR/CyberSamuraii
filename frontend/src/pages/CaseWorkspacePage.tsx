import { useEffect, useRef, useState } from 'react';
import { SearchBar } from '../components/SearchBar';
import { ProgressTracker } from '../components/ProgressTracker';
import { ResultsPanel } from '../components/ResultsPanel';
import { EvidencePanel } from '../components/EvidencePanel';
import { GraphView } from '../components/GraphView';
import { DiscoveryChainPanel } from '../components/DiscoveryChainPanel';
import { PersonInvestigationPanel } from '../components/PersonInvestigationPanel';
import { ReviewPanel } from '../components/ReviewPanel';
import { ExportPanel } from '../components/ExportPanel';
import { FloatingCopilot } from '../components/FloatingCopilot';
import { EntityDetailDrawer } from '../components/EntityDetailDrawer';
import { Spinner } from '../components/loading';
import { useInvestigationStore } from '../store/investigationStore';
import { useAuthStore } from '../store/authStore';
import { useUiStore } from '../store/uiStore';
import { loadInvestigationById } from '../api/investigate';
import {
  addBookmark, addCaseComment, addCaseNote, addPin, archiveEvidence, createCaseTask,
  decideApproval, fetchBookmarks, fetchCaseActivity, fetchCaseApprovals, fetchCaseComments,
  fetchCaseDetail, fetchCaseEvidence, fetchCaseNotes, fetchCaseTasks, fetchPins,
  markEvidenceImportant, updateTaskStatus, type ApprovalRecord, type CaseDetail,
} from '../api/enterprise';
import { hasPermission } from '../lib/permissions';

const INV_TABS = [
  { id: 'intelligence', label: 'Intelligence' },
  { id: 'results', label: 'Accounts' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'graph', label: 'Graph' },
  { id: 'discovery', label: 'Discovery' },
  { id: 'review', label: 'Review' },
  { id: 'export', label: 'Export' },
] as const;

const WS_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'investigate', label: 'Investigate' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'notes', label: 'Notes' },
  { id: 'collaboration', label: 'Collaboration' },
  { id: 'bookmarks', label: 'Bookmarks' },
  { id: 'governance', label: 'Evidence Chain' },
  { id: 'approvals', label: 'Approvals' },
];

interface TaskRow { task_id: string; title: string; status: string; assigned_to?: string }
interface CommentRow { comment_id: string; content: string; author_name?: string; created_at?: string }
interface BookmarkRow { bookmark_id: string; entity_id: string; entity_label: string; entity_type: string }
interface PinRow { pin_id: string; finding_key: string; finding_label: string }
interface EvidenceRow { evidence_id: string; sha256: string; source: string; important?: boolean; archived?: boolean }

export function CaseWorkspacePage() {
  const selectedCaseId = useUiStore((s) => s.selectedCaseId);
  const tab = useUiStore((s) => s.caseWorkspaceTab);
  const setTab = useUiStore((s) => s.setCaseWorkspaceTab);
  const activeTab = useInvestigationStore((s) => s.activeTab);
  const setActiveTab = useInvestigationStore((s) => s.setActiveTab);
  const error = useInvestigationStore((s) => s.error);
  const investigationId = useInvestigationStore((s) => s.investigationId);
  const selectedEntityId = useInvestigationStore((s) => s.selectedEntityId);
  const activeCaseId = useAuthStore((s) => s.activeCaseId);
  const setActiveCase = useAuthStore((s) => s.setActiveCase);
  const role = useAuthStore((s) => s.user?.role || 'VIEWER');
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [activity, setActivity] = useState<{ type?: string; timestamp?: string; user?: string; summary?: string }[]>([]);
  const [evidence, setEvidence] = useState<EvidenceRow[]>([]);
  const [notes, setNotes] = useState<{ note_id: string; content: string }[]>([]);
  const [comments, setComments] = useState<CommentRow[]>([]);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [bookmarks, setBookmarks] = useState<BookmarkRow[]>([]);
  const [pins, setPins] = useState<PinRow[]>([]);
  const [comment, setComment] = useState('');
  const [noteText, setNoteText] = useState('');
  const [taskTitle, setTaskTitle] = useState('');
  const [bookmarkLabel, setBookmarkLabel] = useState('');
  const [pinLabel, setPinLabel] = useState('');
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([]);
  const [caseLoading, setCaseLoading] = useState(false);
  const [investigationLoading, setInvestigationLoading] = useState(false);
  const [headerCompact, setHeaderCompact] = useState(false);
  const prevCaseIdRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const caseId = selectedCaseId || activeCaseId;
  const canInvestigate = hasPermission(role, 'start_investigation');
  const canApprove = hasPermission(role, 'approve_evidence');
  const canEdit = hasPermission(role, 'edit_case');

  const reloadEvidence = () => {
    if (!caseId) return;
    fetchCaseEvidence(caseId).then((d) => setEvidence(d.evidence || [])).catch(() => setEvidence([]));
  };

  useEffect(() => {
    if (caseId) setActiveCase(caseId);
  }, [caseId, setActiveCase]);

  useEffect(() => {
    if (!caseId) return;

    const caseChanged = prevCaseIdRef.current !== caseId;
    if (caseChanged) {
      prevCaseIdRef.current = caseId;
      setDetail(null);
      setCaseLoading(true);
      setInvestigationLoading(false);
      useInvestigationStore.getState().reset();
    }

    fetchCaseDetail(caseId)
      .then(async (d) => {
        setDetail(d);
        if (caseChanged && d.investigations?.length) {
          setInvestigationLoading(true);
          try {
            await loadInvestigationById(d.investigations[0].investigation_id);
          } catch {
            /* case may have linked investigations without stored results yet */
          } finally {
            setInvestigationLoading(false);
          }
        }
      })
      .catch(() => setDetail(null))
      .finally(() => setCaseLoading(false));
    fetchCaseNotes(caseId).then(setNotes).catch(() => setNotes([]));
    fetchCaseActivity(caseId).then((d) => setActivity(d.activity || [])).catch(() => setActivity([]));
    reloadEvidence();
    fetchCaseApprovals(caseId).then((d) => setApprovals(d.approvals || [])).catch(() => setApprovals([]));
    fetchCaseComments(caseId).then((d) => setComments(d.comments || [])).catch(() => setComments([]));
    fetchCaseTasks(caseId).then((d) => setTasks(d.tasks || [])).catch(() => setTasks([]));
    fetchBookmarks(caseId).then((d) => setBookmarks(d.bookmarks || [])).catch(() => setBookmarks([]));
    fetchPins(caseId).then((d) => setPins(d.pins || [])).catch(() => setPins([]));
  }, [caseId]);

  useEffect(() => {
    setHeaderCompact(false);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [caseId, tab]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !caseId) return;

    const onScroll = () => setHeaderCompact(el.scrollTop > 32);
    onScroll();
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, [caseId, tab]);

  if (!caseId) {
    return (
      <div className="intel-panel rounded-xl p-8 text-center">
        <p className="text-slate-400">Select a case from the Cases page to open the investigation workspace.</p>
      </div>
    );
  }

  const addBookmarkFromSelection = () => {
    const entityId = selectedEntityId || investigationId;
    if (!entityId) return;
    addBookmark(caseId, { entity_id: entityId, entity_label: bookmarkLabel || entityId, entity_type: 'entity' })
      .then(() => fetchBookmarks(caseId).then((d) => setBookmarks(d.bookmarks || [])));
    setBookmarkLabel('');
  };

  const addPinFromFinding = () => {
    if (!pinLabel.trim()) return;
    addPin(caseId, { finding_key: pinLabel.trim(), finding_label: pinLabel.trim() })
      .then(() => fetchPins(caseId).then((d) => setPins(d.pins || [])));
    setPinLabel('');
  };

  return (
    <div className="workspace-page h-full min-h-0">
      <div className={`workspace-head ${headerCompact ? 'workspace-head--compact' : ''}`}>
        {caseLoading && !detail ? (
          <div className="workspace-case-skeleton h-24" />
        ) : detail ? (
          <div className="workspace-case-banner intel-panel rounded-xl">
            <div className="workspace-case-banner__full">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-sm text-cyan-400">{detail.case_number}</p>
                  <h1 className="text-lg font-bold text-white">{detail.title}</h1>
                  <p className="mt-1 text-sm text-slate-400">{detail.description}</p>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="rounded border border-slate-700 px-2 py-1">{detail.status}</span>
                  <span className="rounded border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-rose-300">{detail.priority}</span>
                  <span className="rounded border border-slate-700 px-2 py-1">{detail.investigation_count} investigations</span>
                </div>
              </div>
            </div>
            <div className="workspace-case-banner__compact">
              <span className="shrink-0 font-mono text-[10px] text-cyan-500">{detail.case_number}</span>
              <h1 className="min-w-0 truncate text-sm font-semibold text-white">{detail.title}</h1>
            </div>
          </div>
        ) : null}

        <nav className="workspace-tabs">
          {WS_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`workspace-tab ${tab === t.id ? 'workspace-tab--active' : ''}`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      <div ref={scrollRef} className="workspace-scroll">
        <div className="workspace-content">
      {tab === 'overview' && (
        <div key="overview" className="workspace-tab-panel intel-panel rounded-xl p-4">
          <h2 className="mb-2 text-sm font-semibold">Recent investigations</h2>
          {caseLoading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
              <Spinner size="sm" variant="ring" />
              Loading case data…
            </div>
          ) : (
            <ul className="space-y-1 text-sm">
              {(detail?.investigations || []).map((inv) => (
                <li key={inv.investigation_id} className="text-slate-300">{inv.query} <span className="text-slate-600">({inv.created_at?.slice(0, 10)})</span></li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === 'investigate' && canInvestigate && (
        <div key="investigate" className="workspace-tab-panel space-y-4">
          <SearchBar
            caseInvestigations={detail?.case_id === caseId ? detail.investigations : undefined}
            investigationsLoading={caseLoading}
          />
          <ProgressTracker />
          {error && <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>}
          <div className="grid gap-6 xl:grid-cols-12">
            <section className="min-w-0 xl:col-span-12">
              <div className="intel-panel workspace-loading min-w-0 overflow-hidden">
                {(caseLoading || investigationLoading) && (
                  <div className="workspace-loading__overlay rounded-xl">
                    <Spinner size="lg" variant="ring" />
                    <p className="workspace-loading__label">
                      {caseLoading ? 'Loading case workspace…' : 'Loading investigation results…'}
                    </p>
                  </div>
                )}
                <nav className="flex overflow-x-auto border-b border-slate-800/80">
                  {INV_TABS.map((t) => (
                    <button key={t.id} onClick={() => setActiveTab(t.id)} className={`shrink-0 px-4 py-3 text-sm transition-colors ${activeTab === t.id ? 'intel-tab-active' : 'text-slate-500 hover:text-slate-300'}`}>{t.label}</button>
                  ))}
                </nav>
                <div className={`p-5 content-transition ${caseLoading || investigationLoading ? 'is-loading' : ''}`}>
                  {activeTab === 'intelligence' && <PersonInvestigationPanel />}
                  {activeTab === 'results' && <ResultsPanel />}
                  {activeTab === 'evidence' && <EvidencePanel />}
                  {activeTab === 'graph' && <GraphView />}
                  {activeTab === 'discovery' && <DiscoveryChainPanel />}
                  {activeTab === 'review' && <ReviewPanel />}
                  {activeTab === 'export' && <ExportPanel />}
                </div>
              </div>
            </section>
          </div>
          <FloatingCopilot />
          <EntityDetailDrawer />
        </div>
      )}

      {tab === 'timeline' && (
        <div key="timeline" className="workspace-tab-panel intel-panel space-y-2 rounded-xl p-4">
          {activity.map((a, i) => (
            <div key={i} className="border-b border-slate-800 py-2 text-xs"><span className="text-cyan-400">{a.type}</span> — {a.summary} <span className="text-slate-600">by {a.user}</span></div>
          ))}
        </div>
      )}

      {tab === 'notes' && (
        <div key="notes" className="workspace-tab-panel intel-panel rounded-xl p-4">
          <div className="mb-3 flex gap-2">
            <input value={noteText} onChange={(e) => setNoteText(e.target.value)} className="flex-1 rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" placeholder="Add pinned note…" />
            <button type="button" onClick={() => addCaseNote(caseId, noteText, true).then(() => fetchCaseNotes(caseId).then(setNotes))} className="rounded bg-cyan-600 px-3 py-2 text-xs text-white">Add</button>
          </div>
          <ul className="space-y-2">{notes.map((n) => <li key={n.note_id} className="rounded border border-slate-800 p-2 text-sm">{n.content}</li>)}</ul>
        </div>
      )}

      {tab === 'collaboration' && (
        <div key="collaboration" className="workspace-tab-panel grid gap-4 lg:grid-cols-2">
          <div className="intel-panel rounded-xl p-4">
            <h3 className="mb-2 text-sm font-semibold">Comments</h3>
            <ul className="mb-3 max-h-40 space-y-2 overflow-y-auto text-xs">
              {comments.map((c) => (
                <li key={c.comment_id} className="rounded border border-slate-800 p-2">
                  <span className="text-cyan-400">{c.author_name}</span>: {c.content}
                </li>
              ))}
            </ul>
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} className="mb-2 w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm" rows={3} />
            <button type="button" onClick={() => addCaseComment(caseId, comment).then(() => fetchCaseComments(caseId).then((d) => setComments(d.comments || []))).then(() => setComment(''))} className="rounded bg-slate-700 px-3 py-1 text-xs">Post</button>
          </div>
          <div className="intel-panel rounded-xl p-4">
            <h3 className="mb-2 text-sm font-semibold">Tasks</h3>
            <ul className="mb-3 space-y-2 text-xs">
              {tasks.map((t) => (
                <li key={t.task_id} className="flex items-center justify-between rounded border border-slate-800 p-2">
                  <span>{t.title}</span>
                  {canEdit ? (
                    <select value={t.status} onChange={(e) => updateTaskStatus(caseId, t.task_id, e.target.value).then(() => fetchCaseTasks(caseId).then((d) => setTasks(d.tasks || [])))} className="rounded border border-slate-700 bg-slate-900 px-1 text-[10px]">
                      {['open', 'in_progress', 'done', 'cancelled'].map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  ) : <span className="text-slate-500">{t.status}</span>}
                </li>
              ))}
            </ul>
            <input value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} className="mb-2 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm" placeholder="Task title" />
            <button type="button" onClick={() => createCaseTask(caseId, { title: taskTitle }).then(() => fetchCaseTasks(caseId).then((d) => setTasks(d.tasks || []))).then(() => setTaskTitle(''))} className="rounded bg-slate-700 px-3 py-1 text-xs">Assign task</button>
          </div>
        </div>
      )}

      {tab === 'bookmarks' && (
        <div key="bookmarks" className="workspace-tab-panel grid gap-4 lg:grid-cols-2">
          <div className="intel-panel rounded-xl p-4">
            <h3 className="mb-2 text-sm font-semibold">Bookmarks</h3>
            {canEdit && (
              <div className="mb-3 flex gap-2">
                <input value={bookmarkLabel} onChange={(e) => setBookmarkLabel(e.target.value)} placeholder="Label (optional)" className="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs" />
                <button type="button" onClick={addBookmarkFromSelection} className="rounded bg-cyan-700 px-2 py-1 text-xs text-white">Bookmark selection</button>
              </div>
            )}
            <ul className="space-y-1 text-xs">{bookmarks.map((b) => <li key={b.bookmark_id} className="rounded border border-slate-800 p-2">{b.entity_label || b.entity_id}</li>)}</ul>
          </div>
          <div className="intel-panel rounded-xl p-4">
            <h3 className="mb-2 text-sm font-semibold">Pinned findings</h3>
            {canEdit && (
              <div className="mb-3 flex gap-2">
                <input value={pinLabel} onChange={(e) => setPinLabel(e.target.value)} placeholder="Finding key" className="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs" />
                <button type="button" onClick={addPinFromFinding} className="rounded bg-cyan-700 px-2 py-1 text-xs text-white">Pin</button>
              </div>
            )}
            <ul className="space-y-1 text-xs">{pins.map((p) => <li key={p.pin_id} className="rounded border border-slate-800 p-2">{p.finding_label || p.finding_key}</li>)}</ul>
          </div>
        </div>
      )}

      {tab === 'governance' && (
        <div key="governance" className="workspace-tab-panel intel-panel rounded-xl p-4">
          <h3 className="mb-3 text-sm font-semibold">Evidence chain (SHA256)</h3>
          <table className="w-full text-xs">
            <thead><tr className="text-slate-500"><th className="py-1 text-left">ID</th><th className="py-1 text-left">Hash</th><th className="py-1 text-left">Source</th><th className="py-1 text-left">Actions</th></tr></thead>
            <tbody>
              {evidence.map((e) => (
                <tr key={e.evidence_id} className="border-t border-slate-800">
                  <td className="py-2 font-mono text-cyan-400">{e.evidence_id.slice(0, 8)}</td>
                  <td className="py-2 font-mono text-slate-400">{e.sha256.slice(0, 20)}…</td>
                  <td className="py-2">{e.source}{e.important ? ' ⭐' : ''}{e.archived ? ' 📦' : ''}</td>
                  <td className="py-2">
                    {canApprove && (
                      <>
                        <button type="button" onClick={() => markEvidenceImportant(caseId, e.evidence_id, !e.important).then(reloadEvidence)} className="mr-2 text-cyan-400">{e.important ? 'Unmark' : '⭐ Important'}</button>
                        {!e.archived && <button type="button" onClick={() => archiveEvidence(caseId, e.evidence_id).then(reloadEvidence)} className="text-amber-400">Archive</button>}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'approvals' && (
        <div key="approvals" className="workspace-tab-panel intel-panel rounded-xl p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Approval chain</h3>
            <button type="button" onClick={() => fetchCaseApprovals(caseId).then((d) => setApprovals(d.approvals || []))} className="text-xs text-cyan-400">Refresh</button>
          </div>
          {approvals.length === 0 ? (
            <p className="text-xs text-slate-500">No approvals yet — submit from Review tab after investigation.</p>
          ) : (
            <ul className="space-y-2">
              {approvals.map((a) => (
                <li key={a.approval_id} className="rounded border border-slate-800 p-2 text-xs">
                  <span className="text-cyan-400">{a.stage}</span> — {a.decision} {a.notes && <span className="text-slate-500">({a.notes})</span>}
                  {canApprove && a.decision === 'pending' && (
                    <div className="mt-2 flex gap-2">
                      <button type="button" onClick={() => decideApproval(a.approval_id, 'approved').then(() => fetchCaseApprovals(caseId).then((d) => setApprovals(d.approvals || [])))} className="text-emerald-400">Approve</button>
                      <button type="button" onClick={() => decideApproval(a.approval_id, 'clarification').then(() => fetchCaseApprovals(caseId).then((d) => setApprovals(d.approvals || [])))} className="text-amber-400">Clarify</button>
                      <button type="button" onClick={() => decideApproval(a.approval_id, 'rejected').then(() => fetchCaseApprovals(caseId).then((d) => setApprovals(d.approvals || [])))} className="text-rose-400">Reject</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
        </div>
      </div>
    </div>
  );
}
