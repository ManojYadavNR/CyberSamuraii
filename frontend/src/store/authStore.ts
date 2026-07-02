import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface AuthUser {
  user_id: string;
  username: string;
  name: string;
  email: string;
  role: string;
  department: string;
  designation: string;
  active: boolean;
  last_login?: string | null;
  avatar_url?: string | null;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  enterpriseAuth: boolean;
  activeCaseId: string | null;
  lastActivity: number;
  setSession: (access: string, refresh: string, user: AuthUser) => void;
  clearSession: () => void;
  setEnterpriseAuth: (enabled: boolean) => void;
  setActiveCase: (caseId: string | null) => void;
  updateUserProfile: (patch: Partial<AuthUser>) => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      enterpriseAuth: true,
      activeCaseId: null,
      lastActivity: Date.now(),
      setSession: (access, refresh, user) => set({ accessToken: access, refreshToken: refresh, user, lastActivity: Date.now() }),
      clearSession: () => set({
        accessToken: null,
        refreshToken: null,
        user: null,
        activeCaseId: null,
        lastActivity: 0,
      }),
      setEnterpriseAuth: (enabled) => set({ enterpriseAuth: enabled }),
      setActiveCase: (caseId) => set({ activeCaseId: caseId }),
      updateUserProfile: (patch) => {
        const user = get().user;
        if (!user) return;
        set({ user: { ...user, ...patch } });
      },
      isAuthenticated: () => {
        const s = get();
        if (!s.enterpriseAuth) return true;
        return Boolean(s.accessToken && s.user);
      },
    }),
    { name: 'socmint-auth' },
  ),
);

export function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  if (!token) return { 'Content-Type': 'application/json' };
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}
