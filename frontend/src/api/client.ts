import type { BackendToolHealth, GraphOutput, InvestigationResult } from '../types';
import { refreshAccessToken } from './auth';
import { authHeaders, useAuthStore } from '../store/authStore';

const API_BASE = import.meta.env.VITE_API_URL || '';

export async function apiFetch<T = unknown>(url: string, init?: RequestInit, retried = false): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers as Record<string, string> | undefined) },
  });
  if (res.status === 401 && !retried && useAuthStore.getState().refreshToken) {
    const ok = await refreshAccessToken();
    if (ok) return apiFetch<T>(url, init, true);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export function apiAssetUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `${API_BASE}${path}`;
}

export async function uploadImage(file: File): Promise<{
  image_id: string;
  image_path: string;
  filename: string;
  preview_url: string;
}> {
  const form = new FormData();
  form.append('file', file);
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/intel/image/upload`, {
    method: 'POST',
    headers,
    body: form,
  });
  if (res.status === 401 && useAuthStore.getState().refreshToken) {
    const ok = await refreshAccessToken();
    if (ok) return uploadImage(file);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Image upload failed');
  }
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function fetchToolsStatus(): Promise<Record<string, BackendToolHealth>> {
  return apiFetch('/api/tools/status');
}

export async function fetchToolStatus(toolName: string): Promise<{ tool: string; status: BackendToolHealth }> {
  return apiFetch(`/api/tools/status/${encodeURIComponent(toolName)}`);
}

export async function reloadToolsRegistry(): Promise<Record<string, unknown>> {
  return apiFetch('/api/tools/reload', { method: 'POST' });
}

export async function setToolEnabled(toolName: string, enabled: boolean): Promise<Record<string, unknown>> {
  return apiFetch(`/api/tools/${encodeURIComponent(toolName)}/enabled`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
}

export async function fetchOsintCatalog(): Promise<Record<string, unknown>> {
  return apiFetch('/api/tools');
}

export async function fetchToolRoute(inputType: string, profile = 'fast'): Promise<Record<string, unknown>> {
  return apiFetch(`/api/tools/route/${encodeURIComponent(inputType)}?profile=${encodeURIComponent(profile)}`);
}

export async function fetchInvestigation(investigationId: string): Promise<{
  id: string;
  query: string;
  query_type: string;
  status: string;
  error?: string;
  result?: InvestigationResult;
}> {
  return apiFetch(`/api/dashboard/investigations/${investigationId}`);
}

export async function fetchReviews(investigationId: string): Promise<{ investigation_id: string; reviews: import('../types').ReviewRecord[] }> {
  return apiFetch(`/api/dashboard/review/${investigationId}`);
}

export async function submitReview(payload: {
  investigation_id: string;
  cluster_id: string;
  decision: 'approve' | 'reject' | 'suspicious';
  reviewer?: string;
  notes?: string;
}) {
  return apiFetch('/api/dashboard/review', { method: 'POST', body: JSON.stringify(payload) });
}

export async function prewarmCopilot(): Promise<{ ollama_online: boolean; model: string; warmed: boolean }> {
  return apiFetch('/api/dashboard/copilot/prewarm', { method: 'POST' });
}

export async function fetchCopilotStatus(): Promise<{
  ollama_online: boolean;
  model: string;
  auto_start: boolean;
  hint: string;
}> {
  return apiFetch('/api/dashboard/copilot/status');
}

export async function copilotChat(payload: {
  message: string;
  investigation_id?: string;
  context?: Record<string, unknown>;
}): Promise<{ answer: string }> {
  return apiFetch<{ answer: string }>('/api/dashboard/copilot', { method: 'POST', body: JSON.stringify(payload) });
}

export async function copilotChatStream(
  payload: {
    message: string;
    investigation_id?: string;
    context?: Record<string, unknown>;
  },
  onEvent: (event: {
    token?: string;
    done?: boolean;
    answer?: string;
    error?: string;
    status?: string;
  }) => void,
  retried = false,
): Promise<string> {
  const API_BASE = import.meta.env.VITE_API_URL || '';
  const res = await fetch(`${API_BASE}/api/dashboard/copilot/stream`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (res.status === 401 && !retried && useAuthStore.getState().refreshToken) {
    const ok = await refreshAccessToken();
    if (ok) return copilotChatStream(payload, onEvent, true);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  if (!res.body) throw new Error('No response body');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalAnswer = '';
  let streamed = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const event = JSON.parse(line.slice(6)) as {
          token?: string;
          done?: boolean;
          answer?: string;
          error?: string;
          status?: string;
        };
        onEvent(event);
        if (event.token) streamed += event.token;
        if (event.done && event.answer) finalAnswer = event.answer;
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
  return finalAnswer || streamed;
}

/** Stream first; fall back to single-shot API if stream fails. */
export async function copilotAsk(
  payload: {
    message: string;
    investigation_id?: string;
    context?: Record<string, unknown>;
  },
  onEvent: (event: {
    token?: string;
    done?: boolean;
    answer?: string;
    error?: string;
    status?: string;
  }) => void,
): Promise<string> {
  try {
    return await copilotChatStream(payload, onEvent);
  } catch (streamErr) {
    onEvent({ status: 'thinking' });
    const res = await copilotChat(payload);
    onEvent({ token: res.answer });
    onEvent({ done: true, answer: res.answer });
    return res.answer;
  }
}

export async function exportReport(payload: {
  investigation_id: string;
  query: string;
  result: Record<string, unknown>;
  reviewer?: string;
  case_id?: string;
}): Promise<{ integrity_hash: string; html: string }> {
  return apiFetch<{ integrity_hash: string; html: string }>('/api/dashboard/export', { method: 'POST', body: JSON.stringify(payload) });
}

export async function runCorrelate(seedQuery: string, entities: Record<string, unknown>[]): Promise<NonNullable<InvestigationResult['correlation']>> {
  return apiFetch<NonNullable<InvestigationResult['correlation']>>('/api/intel/correlate', {
    method: 'POST',
    body: JSON.stringify({ seed_query: seedQuery, entities }),
  });
}

export async function runGraph(seedQuery: string, entities: Record<string, unknown>[], clusters: Record<string, unknown>[]): Promise<GraphOutput> {
  return apiFetch<GraphOutput>('/api/intel/graph', {
    method: 'POST',
    body: JSON.stringify({ seed_query: seedQuery, entities, clusters }),
  });
}

export function getWsUrl(): string {
  const base = import.meta.env.VITE_WS_URL;
  if (base) return base;
  if (import.meta.env.DEV) {
    return 'ws://127.0.0.1:8000/ws/investigate';
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${proto}//${host}/ws/investigate`;
}
