import { create } from 'zustand';
import type { BackendToolHealth, ChatMessage, InvestigationResult, ReviewRecord, ToolProgress } from '../types';

type Tab = 'results' | 'evidence' | 'graph' | 'investigator' | 'review' | 'export' | 'tools';

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
  reviews: ReviewRecord[];
  chatMessages: ChatMessage[];
  activeTab: Tab;
  backendHealth: 'ok' | 'down' | 'checking';
  toolsHealth: Record<string, BackendToolHealth>;
  setQuery: (q: string) => void;
  setActiveTab: (tab: Tab) => void;
  selectCluster: (id: string | null) => void;
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
  reviews: [],
  chatMessages: [],
  activeTab: 'results',
  backendHealth: 'checking',
  toolsHealth: {},

  setQuery: (q) => set({ query: q }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  selectCluster: (id) => set({ selectedClusterId: id }),
  reset: () =>
    set({
      investigationId: null,
      status: 'idle',
      error: null,
      toolProgress: [],
      phase: '',
      result: null,
      selectedClusterId: null,
      reviews: [],
    }),
  setRunning: () => set({ status: 'running', error: null, toolProgress: [], result: null }),
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
    });
  },
}));
