/** RBAC permissions mirror of config/rbac.json */

const ROLE_PERMISSIONS: Record<string, string[]> = {
  SUPER_ADMIN: ['*'],
  CID_DIRECTOR: ['create_case', 'edit_case', 'assign_case', 'start_investigation', 'export_evidence', 'approve_evidence', 'manage_users', 'view_audit_logs', 'close_case', 'view_cases', 'view_investigations'],
  SP: ['create_case', 'edit_case', 'assign_case', 'start_investigation', 'export_evidence', 'approve_evidence', 'close_case', 'view_cases', 'view_investigations', 'view_audit_logs'],
  DSP: ['create_case', 'edit_case', 'assign_case', 'start_investigation', 'export_evidence', 'approve_evidence', 'close_case', 'view_cases', 'view_investigations'],
  INSPECTOR: ['create_case', 'edit_case', 'assign_case', 'start_investigation', 'export_evidence', 'approve_evidence', 'view_cases', 'view_investigations'],
  SUB_INSPECTOR: ['create_case', 'edit_case', 'start_investigation', 'export_evidence', 'view_cases', 'view_investigations'],
  ANALYST: ['create_case', 'start_investigation', 'export_evidence', 'view_cases', 'view_investigations'],
  INTELLIGENCE_OFFICER: ['start_investigation', 'view_cases', 'view_investigations', 'export_evidence'],
  FORENSICS_OFFICER: ['start_investigation', 'view_cases', 'view_investigations', 'export_evidence'],
  VIEWER: ['view_cases', 'view_investigations'],
  AUDITOR: ['view_cases', 'view_investigations', 'view_audit_logs'],
};

export const ALL_ROLES = Object.keys(ROLE_PERMISSIONS);

export const PERMISSION_LABELS: Record<string, string> = {
  create_case: 'Create Cases',
  edit_case: 'Edit Cases',
  delete_case: 'Delete Cases',
  assign_case: 'Assign Cases',
  start_investigation: 'Start Investigations',
  export_evidence: 'Export Evidence',
  approve_evidence: 'Approve Evidence',
  manage_users: 'Manage Users',
  view_audit_logs: 'View Audit Logs',
  close_case: 'Close Cases',
  view_cases: 'View Cases',
  view_investigations: 'View Investigations',
};

export function getRolePermissions(role: string): string[] {
  return ROLE_PERMISSIONS[role] || [];
}

export function permissionLabel(permission: string): string {
  if (permission === '*') return 'Full platform access';
  return PERMISSION_LABELS[permission] || permission.replace(/_/g, ' ');
}

export function hasPermission(role: string, permission: string): boolean {
  const perms = ROLE_PERMISSIONS[role] || [];
  return perms.includes('*') || perms.includes(permission);
}
