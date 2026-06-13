import type { BackendToolHealth, InvestigationResult } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '';

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function fetchToolsStatus(): Promise<Record<string, BackendToolHealth>> {
  const res = await fetch(`${API_BASE}/api/tools/status`);
  if (!res.ok) throw new Error('Failed to fetch tool status');
  return res.json();
}

export async function fetchToolStatus(toolName: string): Promise<{ tool: string; status: BackendToolHealth }> {
  const res = await fetch(`${API_BASE}/api/tools/status/${encodeURIComponent(toolName)}`);
  if (!res.ok) throw new Error('Failed to fetch tool status');
  return res.json();
}

export async function fetchInvestigation(investigationId: string): Promise<{
  id: string;
  query: string;
  query_type: string;
  status: string;
  result?: InvestigationResult;
}> {
  const res = await fetch(`${API_BASE}/api/dashboard/investigations/${investigationId}`);
  if (!res.ok) throw new Error('Investigation not found');
  return res.json();
}

export async function fetchReviews(investigationId: string): Promise<{ investigation_id: string; reviews: import('../types').ReviewRecord[] }> {
  const res = await fetch(`${API_BASE}/api/dashboard/review/${investigationId}`);
  if (!res.ok) throw new Error('Failed to fetch reviews');
  return res.json();
}

export async function submitReview(payload: {
  investigation_id: string;
  cluster_id: string;
  decision: 'approve' | 'reject' | 'suspicious';
  reviewer?: string;
  notes?: string;
}) {
  const res = await fetch(`${API_BASE}/api/dashboard/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Review submission failed');
  return res.json();
}

export async function copilotChat(payload: {
  message: string;
  investigation_id?: string;
  context?: Record<string, unknown>;
}) {
  const res = await fetch(`${API_BASE}/api/dashboard/copilot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Copilot request failed');
  return res.json();
}

export async function exportReport(payload: {
  investigation_id: string;
  query: string;
  result: Record<string, unknown>;
  reviewer?: string;
}) {
  const res = await fetch(`${API_BASE}/api/dashboard/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Export failed');
  return res.json();
}

export async function runCorrelate(seedQuery: string, entities: Record<string, unknown>[]) {
  const res = await fetch(`${API_BASE}/api/intel/correlate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seed_query: seedQuery, entities }),
  });
  if (!res.ok) throw new Error('Correlation failed');
  return res.json();
}

export async function runGraph(seedQuery: string, entities: Record<string, unknown>[], clusters: Record<string, unknown>[]) {
  const res = await fetch(`${API_BASE}/api/intel/graph`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seed_query: seedQuery, entities, clusters }),
  });
  if (!res.ok) throw new Error('Graph rebuild failed');
  return res.json();
}

export function getWsUrl(): string {
  const base = import.meta.env.VITE_WS_URL;
  if (base) return base;
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${proto}//${host}/ws/investigate`;
}
