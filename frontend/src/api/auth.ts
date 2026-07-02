import { authHeaders, useAuthStore, type AuthUser } from '../store/authStore';
import { useUiStore } from '../store/uiStore';

const API_BASE = import.meta.env.VITE_API_URL || '';

export interface DemoAccountsResponse {
  accounts: { username: string; role: string; name: string }[];
  admin_username?: string;
  demo_password?: string;
  admin_password_hint?: string;
}

export async function refreshAccessToken(): Promise<boolean> {
  const { refreshToken, setSession, clearSession } = useAuthStore.getState();
  if (!refreshToken) return false;
  const res = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) {
    clearSession();
    return false;
  }
  const data = await res.json();
  setSession(data.access_token, data.refresh_token || refreshToken, data.user);
  return true;
}

export async function logoutSession(): Promise<void> {
  const { refreshToken } = useAuthStore.getState();
  try {
    if (refreshToken) {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const access = useAuthStore.getState().accessToken;
      if (access) headers.Authorization = `Bearer ${access}`;
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    }
  } catch {
    /* best-effort server logout */
  } finally {
    useAuthStore.getState().clearSession();
    useUiStore.setState({
      page: 'dashboard',
      selectedCaseId: null,
      selectedCaseMeta: null,
      auditPrefill: null,
      prefillSearch: null,
    });
  }
}

export async function fetchMe(): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/api/auth/me`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Session invalid');
  return res.json();
}

export async function fetchDemoAccounts(): Promise<DemoAccountsResponse> {
  const res = await fetch(`${API_BASE}/api/auth/demo-accounts`);
  if (!res.ok) return { accounts: [] };
  return res.json();
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/enterprise/users/me/password`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Password change failed');
  }
}
