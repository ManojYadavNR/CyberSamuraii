/** RBAC — loads from /api/enterprise/rbac/config with static fallback. */

import { apiFetch } from '../api/client';

export interface RbacConfig {
  permissions: string[];
  roles: Record<string, string[]>;
  organizational_ranks: { code: string; label: string; order: number }[];
  legacy_role_map?: Record<string, string>;
  case_relationships: { code: string; label: string }[];
  permission_matrix: Record<string, Record<string, string[]>>;
  workflow: Record<string, unknown>;
  assignment_templates: unknown[];
}

const RANK_FALLBACK = ['DGP', 'ADGP', 'IGP', 'DIG', 'SP', 'DSP', 'PI', 'PSI', 'HC', 'PC'] as const;

const FALLBACK_ROLE_PERMISSIONS: Record<string, string[]> = {
  SUPER_ADMIN: ['*'],
  DGP: ['create_case', 'edit_case', 'assign_case', 'start_investigation', 'export_evidence', 'approve_evidence', 'manage_users', 'view_audit_logs', 'close_case', 'view_cases', 'view_investigations', 'manage_agencies', 'manage_integrations'],
  ADGP: ['create_case', 'assign_case', 'view_cases', 'view_investigations', 'approve_reports', 'approve_evidence', 'close_case', 'view_audit_logs', 'manage_agencies'],
  IGP: ['create_case', 'assign_case', 'view_cases', 'view_investigations', 'approve_reports', 'approve_evidence', 'close_case', 'view_audit_logs'],
  DIG: ['create_case', 'assign_case', 'view_cases', 'view_investigations', 'approve_reports', 'approve_evidence', 'close_case', 'view_audit_logs'],
  SP: ['create_case', 'edit_case', 'assign_case', 'start_investigation', 'export_evidence', 'approve_evidence', 'close_case', 'view_cases', 'view_investigations', 'view_audit_logs'],
  DSP: ['create_case', 'edit_case', 'assign_case', 'start_investigation', 'export_evidence', 'approve_evidence', 'close_case', 'view_cases', 'view_investigations'],
  PI: ['create_case', 'edit_case', 'assign_case', 'start_investigation', 'export_evidence', 'approve_evidence', 'view_cases', 'view_investigations'],
  PSI: ['create_case', 'edit_case', 'start_investigation', 'export_evidence', 'view_cases', 'view_investigations'],
  HC: ['start_investigation', 'export_evidence', 'view_cases', 'view_investigations'],
  PC: ['view_cases', 'view_investigations'],
};

let cachedConfig: RbacConfig | null = null;

export async function loadRbacConfig(): Promise<RbacConfig> {
  if (cachedConfig) return cachedConfig;
  try {
    cachedConfig = await apiFetch<RbacConfig>('/api/enterprise/rbac/config');
    return cachedConfig;
  } catch {
    return {
      permissions: Object.values(FALLBACK_ROLE_PERMISSIONS).flat(),
      roles: FALLBACK_ROLE_PERMISSIONS,
      organizational_ranks: RANK_FALLBACK.map((code, i) => ({ code, label: code, order: i + 1 })),
      legacy_role_map: {},
      case_relationships: [],
      permission_matrix: {},
      workflow: {},
      assignment_templates: [],
    };
  }
}

export function getCachedRbacConfig(): RbacConfig | null {
  return cachedConfig;
}

export const ALL_ROLES = [...RANK_FALLBACK, 'SUPER_ADMIN'];

export const PERMISSION_LABELS: Record<string, string> = {
  create_case: 'Create Case',
  edit_case: 'Edit Case',
  delete_case: 'Delete Case',
  assign_case: 'Assign Case',
  start_investigation: 'Start Investigation',
  run_intelligence_collection: 'Run Intelligence Collection',
  export_evidence: 'Export Evidence',
  upload_evidence: 'Upload Evidence',
  edit_evidence: 'Edit Evidence',
  approve_evidence: 'Approve Evidence',
  approve_reports: 'Approve Reports',
  generate_reports: 'Generate Reports',
  manage_users: 'Manage Users',
  manage_agencies: 'Manage Agencies',
  view_audit_logs: 'View Audit Logs',
  close_case: 'Close Case',
  reopen_case: 'Reopen Case',
  view_cases: 'View Case',
  view_investigations: 'View Investigations',
  view_intelligence_graph: 'View Intelligence Graph',
  manage_integrations: 'Manage Integrations',
};

export function normalizeRole(role: string): string {
  const legacy = cachedConfig?.legacy_role_map || {};
  if (legacy[role]) return legacy[role];
  if (ALL_ROLES.includes(role) || RANK_FALLBACK.includes(role as typeof RANK_FALLBACK[number])) return role;
  return role;
}

export function getRolePermissions(role: string): string[] {
  const normalized = normalizeRole(role);
  const fromCache = cachedConfig?.roles[normalized] || cachedConfig?.roles[role];
  if (fromCache) return fromCache;
  return FALLBACK_ROLE_PERMISSIONS[normalized] || FALLBACK_ROLE_PERMISSIONS[role] || [];
}

export function resolveRank(role: string): string {
  const normalized = normalizeRole(role);
  const ranks = new Set(cachedConfig?.organizational_ranks?.map((r) => r.code) || RANK_FALLBACK);
  if (ranks.has(normalized)) return normalized;
  return normalized;
}

export function matrixPermissions(rank: string, relationship: string): string[] {
  const matrix = cachedConfig?.permission_matrix || {};
  const code = resolveRank(rank);
  return matrix[code]?.[relationship] || [];
}

export function permissionLabel(permission: string): string {
  if (permission === '*') return 'Full platform access';
  return PERMISSION_LABELS[permission] || permission.replace(/_/g, ' ');
}

export function hasEffectivePermission(
  summary: { effective_on_case?: string[] } | null | undefined,
  role: string,
  permission: string,
): boolean {
  const effective = summary?.effective_on_case;
  if (effective?.length) {
    return effective.includes('*') || effective.includes(permission);
  }
  return hasPermission(role, permission);
}

export function hasPermission(role: string, permission: string): boolean {
  const perms = getRolePermissions(role);
  return perms.includes('*') || perms.includes(permission);
}

export function hasCasePermission(role: string, relationship: string, permission: string): boolean {
  if (hasPermission(role, permission)) return true;
  const rank = resolveRank(role);
  const perms = matrixPermissions(rank, relationship);
  return perms.includes('*') || perms.includes(permission);
}

export function relationshipLabel(code: string): string {
  const rel = cachedConfig?.case_relationships.find((r) => r.code === code);
  return rel?.label || code.replace(/_/g, ' ');
}

export const CASE_RELATIONSHIPS_FALLBACK = [
  { code: 'supervisor', label: 'Supervisor' },
  { code: 'investigating_officer', label: 'Investigating Officer' },
  { code: 'assistant_investigator', label: 'Assistant Investigator' },
  { code: 'evidence_officer', label: 'Evidence Officer' },
  { code: 'review_officer', label: 'Review Officer' },
  { code: 'read_only', label: 'Read Only' },
  { code: 'case_observer', label: 'Case Observer' },
];

export function caseRelationshipOptions(): { code: string; label: string }[] {
  return cachedConfig?.case_relationships?.length
    ? cachedConfig.case_relationships
    : CASE_RELATIONSHIPS_FALLBACK;
}

export function organizationalRankOptions(): { code: string; label: string; order: number }[] {
  const ranks = cachedConfig?.organizational_ranks || [];
  if (ranks.length) return [...ranks].sort((a, b) => a.order - b.order);
  return RANK_FALLBACK.map((code, i) => ({ code, label: code, order: i + 1 }));
}
