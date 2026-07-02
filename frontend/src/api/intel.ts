import { apiFetch } from './client';
import type { InvestigationResult } from '../types';

export async function usernameSearch(username: string, timeout = 120, tools?: string[]) {
  return apiFetch<Record<string, unknown>>('/api/intel/username-search', {
    method: 'POST',
    body: JSON.stringify({ username, timeout_per_tool: timeout, tools }),
  });
}

export async function emailIntel(email: string, timeout = 120, tools?: string[]) {
  return apiFetch<Record<string, unknown>>('/api/intel/email', {
    method: 'POST',
    body: JSON.stringify({ email, timeout_per_tool: timeout, tools }),
  });
}

export async function domainIntel(domain: string, timeout = 120, tools?: string[]) {
  return apiFetch<Record<string, unknown>>('/api/intel/domain', {
    method: 'POST',
    body: JSON.stringify({ domain, timeout_per_tool: timeout, tools }),
  });
}

export async function infraIntel(query: string, timeout = 120, tools?: string[]) {
  return apiFetch<Record<string, unknown>>('/api/intel/infra', {
    method: 'POST',
    body: JSON.stringify({ query, timeout_per_tool: timeout, tools }),
  });
}

export async function imageIntel(source: { image_path?: string; image_url?: string }, timeout = 120) {
  return apiFetch<Record<string, unknown>>('/api/intel/image', {
    method: 'POST',
    body: JSON.stringify({ ...source, timeout_per_tool: timeout }),
  });
}

export async function investigateSync(body: {
  query: string;
  query_type?: string;
  case_id?: string;
  timeout_per_tool?: number;
  discovery?: Record<string, unknown>;
}): Promise<{ investigation_id: string; query_type: string; result: InvestigationResult }> {
  return apiFetch('/api/dashboard/investigate', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
