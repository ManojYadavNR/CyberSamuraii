import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { useAuthStore } from './authStore';

export type AppPage =
  | 'dashboard'
  | 'investigator-dashboard'
  | 'cases'
  | 'case-workspace'
  | 'investigations'
  | 'graph'
  | 'evidence'
  | 'reports'
  | 'osint-framework'
  | 'tools'
  | 'intel-api'
  | 'pending-approvals'
  | 'admin'
  | 'audit'
  | 'password-reset'
  | 'change-password';

interface UiState {
  page: AppPage;
  selectedCaseId: string | null;
  selectedCaseMeta: { case_id: string; case_number: string; title: string } | null;
  caseWorkspaceTab: string;
  prefillSearch: string | null;
  auditPrefill: { user_id: string; username: string; label: string } | null;
  setPage: (page: AppPage) => void;
  setSelectedCase: (caseId: string, meta?: { case_number: string; title: string }) => void;
  openCase: (caseId: string, meta?: { case_number: string; title: string }) => void;
  setCaseWorkspaceTab: (tab: string) => void;
  setPrefillSearch: (query: string | null) => void;
  setAuditPrefill: (prefill: { user_id: string; username: string; label: string } | null) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set, get) => ({
      page: 'dashboard',
      selectedCaseId: null,
      selectedCaseMeta: null,
      caseWorkspaceTab: 'overview',
      prefillSearch: null,
      auditPrefill: null,
      setPage: (page) => set({ page }),
      setSelectedCase: (caseId, meta) => {
        useAuthStore.getState().setActiveCase(caseId);
        set({
          selectedCaseId: caseId,
          selectedCaseMeta: meta
            ? { case_id: caseId, case_number: meta.case_number, title: meta.title }
            : get().selectedCaseMeta?.case_id === caseId
              ? get().selectedCaseMeta
              : null,
        });
      },
      openCase: (caseId, meta) => {
        useAuthStore.getState().setActiveCase(caseId);
        set({
          selectedCaseId: caseId,
          selectedCaseMeta: meta
            ? { case_id: caseId, case_number: meta.case_number, title: meta.title }
            : get().selectedCaseMeta?.case_id === caseId
              ? get().selectedCaseMeta
              : null,
          page: 'case-workspace',
          caseWorkspaceTab: 'investigate',
        });
      },
      setCaseWorkspaceTab: (tab) => set({ caseWorkspaceTab: tab }),
      setPrefillSearch: (query) => set({ prefillSearch: query }),
      setAuditPrefill: (prefill) => set({ auditPrefill: prefill }),
    }),
    { name: 'socmint-ui', partialize: (s) => ({
      page: s.page,
      caseWorkspaceTab: s.caseWorkspaceTab,
      selectedCaseId: s.selectedCaseId,
      selectedCaseMeta: s.selectedCaseMeta,
    }) },
  ),
);
