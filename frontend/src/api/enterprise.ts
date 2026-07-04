import { apiFetch } from './client';
import type { AuditLogEntry, CaseOut, PasswordResetRequestRow } from '../types/enterprise';
import { authHeaders, useAuthStore, type AuthUser } from '../store/authStore';

const API_BASE = import.meta.env.VITE_API_URL || '';

export interface DashboardMetrics {
  active_cases: number;
  open_cases: number;
  investigations_today: number;
  pending_reviews: number;
  high_risk_targets: number;
  investigators_online: number;
  recent_activity: { timestamp: string; user: string; action: string; entity: string }[];
  work_queue: { type: string; id: string; case_id: string; stage?: string }[];
}

export interface CaseDetail extends CaseOut {
  investigation_count: number;
  investigations: { investigation_id: string; query: string; created_at: string }[];
}

export interface NotificationItem {
  notification_id: string;
  title: string;
  body: string;
  kind: string;
  case_id: string;
  read: boolean;
  created_at: string;
}

export async function fetchMetrics(): Promise<DashboardMetrics> {
  return apiFetch('/api/enterprise/dashboard/metrics');
}

export async function uploadProfileAvatar(file: File): Promise<AuthUser> {
  const form = new FormData();
  form.append('file', file);
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/enterprise/users/me/avatar`, {
    method: 'POST',
    headers,
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Avatar upload failed');
  }
  return res.json();
}

export async function fetchCases(): Promise<CaseOut[]> {
  return apiFetch('/api/enterprise/cases');
}

export async function fetchCaseDetail(caseId: string): Promise<CaseDetail> {
  return apiFetch(`/api/enterprise/cases/${caseId}/detail`);
}

export async function createCase(body: { title: string; description?: string; priority?: string }): Promise<CaseOut> {
  return apiFetch('/api/enterprise/cases', { method: 'POST', body: JSON.stringify(body) });
}

export async function assignCase(caseId: string, assignedTo: string, relationship = 'investigating_officer'): Promise<CaseOut> {
  return apiFetch(`/api/enterprise/cases/${caseId}/assign`, {
    method: 'POST',
    body: JSON.stringify({ assigned_to: assignedTo, relationship }),
  });
}

export async function transferCase(caseId: string, assignedTo: string, relationship = 'investigating_officer'): Promise<CaseOut> {
  return apiFetch(`/api/enterprise/cases/${caseId}/transfer`, {
    method: 'POST',
    body: JSON.stringify({ assigned_to: assignedTo, relationship }),
  });
}

export interface CaseAssignmentRow {
  assignment_id: string;
  case_id: string;
  user_id: string;
  relationship: string;
  org_role: string;
  rank_code: string;
  assigned_by: string;
  active: boolean;
  notes: string;
  assigned_at: string;
}

export interface PermissionsSummary {
  role: string;
  rank: string;
  relationships: string[];
  global_permissions: string[];
  case_permissions: string[];
  effective_on_case: string[];
}

export async function fetchRbacConfig() {
  return apiFetch('/api/enterprise/rbac/config');
}

export async function fetchMyPermissions(caseId?: string): Promise<PermissionsSummary> {
  const q = caseId ? `?case_id=${encodeURIComponent(caseId)}` : '';
  return apiFetch(`/api/enterprise/rbac/permissions/me${q}`);
}

export async function fetchCaseAssignments(caseId: string): Promise<CaseAssignmentRow[]> {
  return apiFetch(`/api/enterprise/cases/${caseId}/assignments`);
}

export async function setCaseAssignments(
  caseId: string,
  assignments: { user_id: string; relationship: string; notes?: string }[],
): Promise<CaseAssignmentRow[]> {
  return apiFetch(`/api/enterprise/cases/${caseId}/assignments`, {
    method: 'POST',
    body: JSON.stringify({ assignments }),
  });
}

export async function closeCase(caseId: string): Promise<CaseOut> {
  return apiFetch(`/api/enterprise/cases/${caseId}/close`, { method: 'POST' });
}

export async function archiveCase(caseId: string): Promise<CaseOut> {
  return apiFetch(`/api/enterprise/cases/${caseId}/archive`, { method: 'POST' });
}

export async function updateCase(caseId: string, body: { title?: string; description?: string; priority?: string; status?: string }): Promise<CaseOut> {
  return apiFetch(`/api/enterprise/cases/${caseId}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export async function deleteCase(caseId: string): Promise<{ ok: boolean }> {
  return apiFetch(`/api/enterprise/cases/${caseId}`, { method: 'DELETE' });
}

export async function fetchBookmarks(caseId: string) {
  return apiFetch<{ bookmarks: { bookmark_id: string; entity_id: string; entity_label: string; entity_type: string }[] }>(`/api/enterprise/cases/${caseId}/bookmarks`);
}

export async function addBookmark(caseId: string, body: { entity_id: string; entity_label?: string; entity_type?: string }) {
  return apiFetch(`/api/enterprise/cases/${caseId}/bookmarks`, { method: 'POST', body: JSON.stringify(body) });
}

export async function fetchPins(caseId: string) {
  return apiFetch<{ pins: { pin_id: string; finding_key: string; finding_label: string }[] }>(`/api/enterprise/cases/${caseId}/pins`);
}

export async function addPin(caseId: string, body: { finding_key: string; finding_label?: string; finding_data?: Record<string, unknown> }) {
  return apiFetch(`/api/enterprise/cases/${caseId}/pins`, { method: 'POST', body: JSON.stringify(body) });
}

export async function updateTaskStatus(caseId: string, taskId: string, status: string) {
  return apiFetch(`/api/enterprise/cases/${caseId}/tasks/${taskId}?status=${encodeURIComponent(status)}`, { method: 'PATCH' });
}

export async function markEvidenceImportant(caseId: string, evidenceId: string, important: boolean) {
  return apiFetch(`/api/enterprise/cases/${caseId}/evidence/${evidenceId}/important`, {
    method: 'POST',
    body: JSON.stringify({ important }),
  });
}

export async function archiveEvidence(caseId: string, evidenceId: string) {
  return apiFetch(`/api/enterprise/cases/${caseId}/evidence/${evidenceId}/archive`, { method: 'POST' });
}

export async function fetchPendingApprovals() {
  return apiFetch<{ approvals: ApprovalRecord[] }>('/api/enterprise/approvals/pending');
}

export async function markAllNotificationsRead() {
  return apiFetch<{ count: number }>('/api/notifications/read-all', { method: 'POST' });
}

export async function fetchAgencies() {
  return apiFetch<{ agencies: { id: string; name: string; code?: string }[] }>('/api/enterprise/agencies');
}

export interface ApprovalRecord {
  approval_id: string;
  case_id: string;
  investigation_id: string;
  cluster_id: string;
  stage: string;
  decision: string;
  notes: string;
  reviewer_name?: string;
  created_at?: string;
}

export interface AuditFilters {
  limit?: number;
  offset?: number;
  user_id?: string;
  username?: string;
  role?: string;
  case_id?: string;
  investigation_id?: string;
  category?: string;
  action?: string;
  risk_level?: string;
  result?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
  suspicious_only?: boolean;
}

export async function fetchAuditLogs(filters: AuditFilters = {}): Promise<{ logs: AuditLogEntry[]; total: number; categories: string[] }> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== false) params.set(k, String(v));
  });
  if (!params.has('limit')) params.set('limit', '200');
  return apiFetch(`/api/enterprise/audit?${params.toString()}`);
}

export async function fetchAuditDetail(logId: string): Promise<AuditLogEntry> {
  return apiFetch(`/api/enterprise/audit/${logId}`);
}

export async function verifyAuditChain(limit = 500): Promise<{ valid: boolean; checked: number; broken_at: string | null; repaired?: number }> {
  return apiFetch(`/api/enterprise/audit/verify/chain?limit=${limit}`);
}

export async function exportAuditCsv(filters: AuditFilters = {}): Promise<void> {
  const base = import.meta.env.VITE_API_URL || '';
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== false) params.set(k, String(v));
  });
  const res = await fetch(`${base}/api/enterprise/audit/export/csv?${params.toString()}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Export failed');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `audit_report_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function submitPasswordResetWorkflow(employeeId: string, reason = ''): Promise<{ ok: boolean; message: string; request_id?: string; status?: string }> {
  const base = import.meta.env.VITE_API_URL || '';
  const r = await fetch(`${base}/api/auth/password-reset/workflow`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ employee_id: employeeId, reason }),
  });
  return r.json();
}

export async function fetchPasswordResetRequests(status = ''): Promise<{ requests: PasswordResetRequestRow[] }> {
  const q = status ? `?status=${encodeURIComponent(status)}` : '';
  return apiFetch(`/api/auth/password-reset/requests${q}`);
}

export async function decidePasswordResetSupervisor(requestId: string, approve: boolean, notes = '') {
  const base = import.meta.env.VITE_API_URL || '';
  const r = await fetch(`${base}/api/auth/password-reset/requests/${requestId}/supervisor`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ approve, notes }),
  });
  if (!r.ok) {
    const err = await r.json();
    throw new Error(err.detail || 'Decision failed');
  }
  return r.json();
}

export async function decidePasswordResetAdmin(requestId: string, approve: boolean, notes = '') {
  const base = import.meta.env.VITE_API_URL || '';
  const r = await fetch(`${base}/api/auth/password-reset/requests/${requestId}/admin`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ approve, notes }),
  });
  if (!r.ok) {
    const err = await r.json();
    throw new Error(err.detail || 'Decision failed');
  }
  return r.json();
}

export async function fetchNextUserIds(): Promise<{ employee_id: string; badge_number: string }> {
  return apiFetch('/api/enterprise/users/next-ids');
}

export async function fetchUsers() {
  return apiFetch('/api/enterprise/users');
}

export async function createUser(body: Record<string, string>) {
  return apiFetch('/api/enterprise/users', { method: 'POST', body: JSON.stringify(body) });
}

export async function updateUser(userId: string, body: Record<string, unknown>) {
  return apiFetch(`/api/enterprise/users/${userId}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export async function fetchUserAuditHistory(userId: string, limit = 100) {
  return apiFetch<{ logs: AuditLogEntry[] }>(`/api/enterprise/audit/users/${userId}/history?limit=${limit}`);
}

export async function fetchNotifications(): Promise<{ notifications: NotificationItem[] }> {
  return apiFetch('/api/notifications');
}

export async function markNotificationRead(id: string) {
  await apiFetch(`/api/notifications/${id}/read`, { method: 'POST' });
}

export async function fetchCaseComments(caseId: string): Promise<{ comments: { comment_id: string; content: string; author_name?: string; created_at?: string }[] }> {
  return apiFetch(`/api/enterprise/cases/${caseId}/comments`);
}

export async function addCaseComment(caseId: string, content: string) {
  return apiFetch(`/api/enterprise/cases/${caseId}/comments`, { method: 'POST', body: JSON.stringify({ content }) });
}

export async function fetchCaseTasks(caseId: string): Promise<{ tasks: { task_id: string; title: string; status: string; assigned_to?: string }[] }> {
  return apiFetch(`/api/enterprise/cases/${caseId}/tasks`);
}

export async function createCaseTask(caseId: string, body: { title: string; description?: string; assigned_to?: string }) {
  return apiFetch(`/api/enterprise/cases/${caseId}/tasks`, { method: 'POST', body: JSON.stringify(body) });
}

export async function fetchCaseNotes(caseId: string): Promise<{ note_id: string; content: string }[]> {
  return apiFetch(`/api/enterprise/cases/${caseId}/notes`);
}

export async function addCaseNote(caseId: string, content: string, pinned = false) {
  return apiFetch(`/api/enterprise/cases/${caseId}/notes`, { method: 'POST', body: JSON.stringify({ content, pinned }) });
}

export async function fetchCaseEvidence(caseId: string): Promise<{ evidence: { evidence_id: string; sha256: string; source: string; important?: boolean; archived?: boolean }[] }> {
  return apiFetch(`/api/enterprise/cases/${caseId}/evidence`);
}

export async function fetchCaseApprovals(caseId: string): Promise<{ approvals: ApprovalRecord[] }> {
  return apiFetch(`/api/enterprise/cases/${caseId}/approvals`);
}

export async function submitApproval(caseId: string, body: { investigation_id: string; cluster_id: string; notes?: string }): Promise<ApprovalRecord> {
  return apiFetch(`/api/enterprise/cases/${caseId}/approvals/submit`, { method: 'POST', body: JSON.stringify(body) });
}

export async function decideApproval(approvalId: string, decision: string, notes = '') {
  return apiFetch(`/api/enterprise/approvals/${approvalId}/decide`, { method: 'POST', body: JSON.stringify({ decision, notes }) });
}

export async function fetchCaseActivity(caseId: string): Promise<{ activity: { type?: string; timestamp?: string; user?: string; summary?: string }[] }> {
  return apiFetch(`/api/enterprise/cases/${caseId}/activity`);
}

export async function generateCaseReport(caseId: string, format: 'json' | 'html' | 'docx'): Promise<{ content: string | Record<string, unknown>; filename?: string }> {
  return apiFetch(`/api/enterprise/cases/${caseId}/report`, { method: 'POST', body: JSON.stringify({ format }) });
}

export async function requestPasswordReset(email: string) {
  const base = import.meta.env.VITE_API_URL || '';
  const r = await fetch(`${base}/api/auth/password-reset/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  return r.json();
}

export async function confirmPasswordReset(token: string, newPassword: string) {
  const base = import.meta.env.VITE_API_URL || '';
  const r = await fetch(`${base}/api/auth/password-reset/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  if (!r.ok) {
    const err = await r.json();
    throw new Error(err.detail || 'Reset failed');
  }
  return r.json();
}
