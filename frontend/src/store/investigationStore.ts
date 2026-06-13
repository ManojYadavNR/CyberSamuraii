import { create } from 'zustand';
import type { BackendToolHealth, ChatMessage, InvestigationResult, ReviewRecord, ToolProgress } from '../types';

type Tab = 'results' | 'evidence' | 'graph' | 'investigator' | 'review' | 'export' | 'tools';

export interface RecentInvestigation {
  id: string;
  query: string;
  queryType: string;
  completedAt: string;
}

interface InvestigationState {
  query: string;
  queryType: string;
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
  setBackendHealth: (h: 'ok' | 'down' | 'checking') => void;
  setToolsHealth: (tools: Record<string, BackendToolHealth>) => void;
  updateResult: (partial: Partial<InvestigationResult>) => void;
  loadFromServer: (id: string, query: string, queryType: string, result: InvestigationResult) => void;
  addRecent: (entry: RecentInvestigation) => void;
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
  activeTab: 'results',
  backendHealth: 'checking',
  toolsHealth: {},

  setQuery: (q) => set({ query: q }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  selectCluster: (id) => set({ selectedClusterId: id }),
  openEntityDrawer: (entityId) => set({ selectedEntityId: entityId, drawerOpen: true }),
  closeDrawer: () => set({ drawerOpen: false }),
  reset: () =>
    set({
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
    }),
  setRunning: () =>
    set({
      status: 'running',
      error: null,
      toolProgress: [],
      result: null,
      drawerOpen: false,
      activeTab: 'results',
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
    set({
      investigationId: id,
      status: 'complete',
      result,
      selectedClusterId: firstCluster,
      phase: 'complete',
      activeTab: 'results',
    });
  },
  setError: (msg) => set({ status: 'error', error: msg }),
  setReviews: (reviews) => set({ reviews }),
  addReview: (review) => set((s) => ({ reviews: [...s.reviews, review] })),
  addChatMessage: (msg) => set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  setBackendHealth: (h) => set({ backendHealth: h }),
  setToolsHealth: (tools) => set({ toolsHealth: tools }),
  updateResult: (partial) =>
    set((s) => ({ result: s.result ? { ...s.result, ...partial } : null })),
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
      activeTab: 'results',
    });
  },
    addRecent: (entry) =>
    set((s) => {
      const filtered = s.recentInvestigations.filter((r) => r.id !== entry.id);
      const next = [entry, ...filtered].slice(0, 12);
      saveRecent(next);
      return { recentInvestigations: next };
    }),
}));
