export interface CaseOut {
  case_id: string;
  case_number: string;
  title: string;
  description: string;
  priority: string;
  status: string;
  assigned_to: string | null;
  created_by: string;
  created_at: string;
  updated_at?: string | null;
}

export type AuditCategory =
  | 'authentication'
  | 'investigation'
  | 'evidence'
  | 'report'
  | 'export'
  | 'user_management'
  | 'permission'
  | 'administration'
  | 'copilot'
  | 'external_api'
  | 'system';

export interface AuditLogEntry {
  audit_id: string;
  timestamp: string;
  user: string;
  user_id: string;
  username: string;
  role: string;
  session_id: string;
  category: AuditCategory | string;
  action: string;
  entity: string;
  entity_type: string;
  entity_id: string;
  case_id: string;
  investigation_id: string;
  ip: string;
  location_approx: string;
  device: string;
  browser: string;
  os: string;
  result: string;
  failure_reason: string;
  risk_level: string;
  approval_required: boolean;
  supervisor_id: string;
  previous_value: string;
  new_value: string;
  digital_signature: string;
  hash_chain: string;
  suspicious: boolean;
  details: Record<string, unknown>;
}

export interface PasswordResetRequestRow {
  request_id: string;
  user_id: string;
  employee_id: string;
  employee_name: string;
  status: string;
  reason: string;
  requested_at: string;
  supervisor_id: string;
  supervisor_notes: string;
  admin_id: string;
  admin_notes: string;
  temp_password_issued: boolean;
  temporary_password?: string;
  message?: string;
}
