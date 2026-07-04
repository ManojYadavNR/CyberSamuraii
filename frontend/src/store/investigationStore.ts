import { create } from 'zustand';
import type { BackendToolHealth, ChatMessage, InvestigationResult, ReviewRecord, ToolProgress } from '../types';

type Tab = 'intelligence' | 'osint' | 'results' | 'evidence' | 'graph' | 'discovery' | 'investigator' | 'review' | 'export' | 'tools';

export interface RecentInvestigation {
  id: string;
  query: string;
  queryType: string;
  completedAt: string;
  caseId?: string;
}

interface InvestigationState {
  query: string;
  queryType: string;
  investigationMode: 'standard' | 'fast' | 'deep' | 'samurai';
  investigationId: string | null;
  status: 'idle' | 'running' | 'complete' | 'error';
  error: string | null;
  toolProgress: ToolProgress[];
  phase: string;
  result: InvestigationResult | null;
  selectedClusterId: string | null;
  selectedEntityId: string | null;
  drawerOpen: boolean;
  reviews: ReviewRecord[];
  chatMessages: ChatMessage[];
  recentInvestigations: RecentInvestigation[];
  activeTab: Tab;
  backendHealth: 'ok' | 'down' | 'checking';
  toolsHealth: Record<string, BackendToolHealth>;
  uploadedImagePreview: string | null;
  uploadedImageName: string | null;
  liveFindings: Array<{ id: string; type: string; value: string; confidence?: number; source?: string }>;
  scanPhase: number;
  sitesChecked: number;
  sitesTotal: number;
  setQuery: (q: string) => void;
  setActiveTab: (tab: Tab) => void;
  selectCluster: (id: string | null) => void;
  openEntityDrawer: (entityId: string) => void;
  closeDrawer: () => void;
  reset: () => void;
  setRunning: () => void;
  updateToolProgress: (tool: string, update: Partial<ToolProgress>) => void;
  setPhase: (phase: string) => void;
  setComplete: (id: string, result: InvestigationResult) => void;
  setError: (msg: string) => void;
  setReviews: (reviews: ReviewRecord[]) => void;
  addReview: (review: ReviewRecord) => void;
  addChatMessage: (msg: ChatMessage) => void;
  updateChatMessage: (id: string, content: string) => void;
  clearChatMessages: () => void;
  setBackendHealth: (h: 'ok' | 'down' | 'checking') => void;
  setToolsHealth: (tools: Record<string, BackendToolHealth>) => void;
  setUploadedImage: (previewUrl: string | null, filename: string | null) => void;
  updateResult: (partial: Partial<InvestigationResult>) => void;
  setPartialResult: (partial: Partial<InvestigationResult>, meta?: { scanPhase?: number; sitesChecked?: number; sitesTotal?: number }) => void;
  loadFromServer: (id: string, query: string, queryType: string, result: InvestigationResult) => void;
  addRecent: (entry: RecentInvestigation) => void;
  addLiveFinding: (finding: { type: string; value: string; confidence?: number; source?: string }) => void;
}

const RECENT_KEY = 'socmint_recent_investigations';

function loadRecent(): RecentInvestigation[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveRecent(list: RecentInvestigation[]) {
  localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 12)));
}

export const useInvestigationStore = create<InvestigationState>((set) => ({
  query: '',
  queryType: 'auto',
  investigationMode: 'standard',
  investigationId: null,
  status: 'idle',
  error: null,
  toolProgress: [],
  phase: '',
  result: null,
  selectedClusterId: null,
  selectedEntityId: null,
  drawerOpen: false,
  reviews: [],
  chatMessages: [],
  recentInvestigations: loadRecent(),
  activeTab: 'intelligence',
  backendHealth: 'checking',
  toolsHealth: {},
  uploadedImagePreview: null,
  uploadedImageName: null,
  liveFindings: [],
  scanPhase: 0,
  sitesChecked: 0,
  sitesTotal: 0,

  setQuery: (q) => set({ query: q }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  selectCluster: (id) => set({ selectedClusterId: id }),
  openEntityDrawer: (entityId) => set({ selectedEntityId: entityId, drawerOpen: true }),
  closeDrawer: () => set({ drawerOpen: false }),
  reset: () =>
    set({
      investigationId: null,
      investigationMode: 'standard',
      status: 'idle',
      error: null,
      toolProgress: [],
      phase: '',
      result: null,
      selectedClusterId: null,
      selectedEntityId: null,
      drawerOpen: false,
      reviews: [],
      uploadedImagePreview: null,
      uploadedImageName: null,
      liveFindings: [],
      scanPhase: 0,
      sitesChecked: 0,
      sitesTotal: 0,
    }),
  setRunning: () =>
    set({
      status: 'running',
      error: null,
      toolProgress: [],
      liveFindings: [],
      scanPhase: 0,
      sitesChecked: 0,
      sitesTotal: 0,
      result: null,
      drawerOpen: false,
      activeTab: 'intelligence',
    }),
  updateToolProgress: (tool, update) =>
    set((s) => {
      const existing = s.toolProgress.find((t) => t.tool === tool);
      if (existing) {
        return { toolProgress: s.toolProgress.map((t) => (t.tool === tool ? { ...t, ...update } : t)) };
      }
      return { toolProgress: [...s.toolProgress, { tool, status: 'pending', ...update }] };
    }),
  setPhase: (phase) => set({ phase }),
  setComplete: (id, result) => {
    const firstCluster = result.correlation?.clusters?.[0]?.account_cluster_id ?? null;
    set((s) => ({
      investigationId: id,
      status: 'complete',
      error: null,
      result,
      selectedClusterId: firstCluster,
      phase: 'complete',
      activeTab: 'intelligence',
      // Never leave tools stuck on RUNNING after the investigation finishes.
      toolProgress: s.toolProgress.map((t) =>
        t.status === 'running' || t.status === 'pending'
          ? { ...t, status: 'done' as const, success: t.success ?? true }
          : t,
      ),
    }));
  },
  setError: (msg) => set({ status: 'error', error: msg }),
  setReviews: (reviews) => set({ reviews }),
  addReview: (review) => set((s) => ({ reviews: [...s.reviews, review] })),
  addChatMessage: (msg) => set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  updateChatMessage: (id, content) =>
    set((s) => ({
      chatMessages: s.chatMessages.map((m) => (m.id === id ? { ...m, content } : m)),
    })),
  clearChatMessages: () => set({ chatMessages: [] }),
  setBackendHealth: (h) => set({ backendHealth: h }),
  setToolsHealth: (tools) => set({ toolsHealth: tools }),
  setUploadedImage: (previewUrl, filename) =>
    set({ uploadedImagePreview: previewUrl, uploadedImageName: filename }),
  updateResult: (partial) =>
    set((s) => {
      if (!s.result) return s;
      const mergedTools = Array.isArray(partial.tool_results) && partial.tool_results.length > 0
        ? partial.tool_results
        : s.result.tool_results;
      return {
        result: {
          ...s.result,
          ...partial,
          tool_results: mergedTools,
          evidence_extraction: partial.evidence_extraction ?? s.result.evidence_extraction,
          fusion: partial.fusion ?? s.result.fusion,
          identity_profile: partial.identity_profile ?? s.result.identity_profile,
        },
      };
    }),
  setPartialResult: (partial, meta) =>
    set((s) => {
      // Never reopen a finished investigation as RUNNING.
      if (s.status === 'complete' || s.status === 'error' || s.status === 'idle') {
        return s;
      }
      const defaultFeature =
        s.queryType === 'email' ? 'email_intel'
        : s.queryType === 'image' ? 'image_intel'
        : 'username_search';
      const hasPartialTools = Array.isArray(partial.tool_results) && partial.tool_results.length > 0;
      const prev = s.result;
      // Never clobber Samurai/tool payloads with null/empty fields from a later partial.
      const mergedTools = hasPartialTools
        ? partial.tool_results!
        : (prev?.tool_results ?? []);
      const mergedEvidence = partial.evidence_extraction ?? prev?.evidence_extraction;
      const mergedFusion = partial.fusion ?? prev?.fusion;
      const mergedConfirmed = Array.isArray(partial.confirmed_findings) && partial.confirmed_findings.length > 0
        ? partial.confirmed_findings
        : (prev?.confirmed_findings ?? partial.confirmed_findings);
      const mergedPublic = Array.isArray(partial.public_profile_data) && partial.public_profile_data.length > 0
        ? partial.public_profile_data
        : (prev?.public_profile_data ?? partial.public_profile_data);
      const mergedLeads = Array.isArray(partial.investigation_leads) && partial.investigation_leads.length > 0
        ? partial.investigation_leads
        : (prev?.investigation_leads ?? partial.investigation_leads);
      const mergedScanSummary = partial.scan_summary
        ? { ...(prev?.scan_summary ?? {}), ...partial.scan_summary }
        : prev?.scan_summary;
      return {
      status: 'running',
      phase: meta?.scanPhase === 1 ? 'tool' : (s.phase && s.phase !== 'start' ? s.phase : 'tool'),
      scanPhase: meta?.scanPhase ?? s.scanPhase,
      sitesChecked: meta?.sitesChecked ?? s.sitesChecked,
      sitesTotal: meta?.sitesTotal ?? s.sitesTotal,
      result: {
        feature: prev?.feature ?? defaultFeature,
        query: s.query,
        tool_results: mergedTools,
        ...prev,
        ...partial,
        tool_results: mergedTools,
        evidence_extraction: mergedEvidence,
        fusion: mergedFusion,
        identity_profile: partial.identity_profile ?? prev?.identity_profile,
        confirmed_findings: mergedConfirmed,
        public_profile_data: mergedPublic,
        investigation_leads: mergedLeads,
        scan_summary: mergedScanSummary,
      } as InvestigationResult,
      activeTab: meta?.scanPhase === 1 || hasPartialTools ? 'intelligence' : s.activeTab,
    };
    }),
  loadFromServer: (id, query, queryType, result) => {
    const firstCluster = result.correlation?.clusters?.[0]?.account_cluster_id ?? null;
    set({
      investigationId: id,
      query,
      queryType,
      status: 'complete',
      result,
      selectedClusterId: firstCluster,
      phase: 'loaded',
      error: null,
      activeTab: 'intelligence',
    });
  },
    addRecent: (entry: RecentInvestigation) =>
    set((s) => {
      const filtered = s.recentInvestigations.filter((r) => r.id !== entry.id);
      const next = [entry, ...filtered].slice(0, 12);
      saveRecent(next);
      return { recentInvestigations: next };
    }),
  addLiveFinding: (finding) =>
    set((s) => ({
      liveFindings: [
        ...s.liveFindings,
        { id: `${finding.type}_${s.liveFindings.length}`, ...finding },
      ].slice(-50),
    })),
}));
