export interface IamUser {
  user_id: string;
  username: string;
  name: string;
  email: string;
  role: string;
  department: string;
  designation: string;
  employee_id: string;
  badge_number: string;
  active: boolean;
  last_login: string | null;
  must_change_password?: boolean;
  mfa_enabled?: boolean;
}

export type IamSection = 'identity' | 'organization' | 'security' | 'system';

export type PasswordResetTab = 'pending' | 'approved' | 'rejected' | 'completed';

export interface CreateUserFormState {
  name: string;
  username: string;
  email: string;
  password: string;
  phone: string;
  employeeId: string;
  badgeNumber: string;
  agency: string;
  department: string;
  district: string;
  unit: string;
  supervisor: string;
  role: string;
  forcePasswordChange: boolean;
  requireMfa: boolean;
}

export const DEFAULT_CREATE_USER: CreateUserFormState = {
  name: '',
  username: '',
  email: '',
  password: '',
  phone: '',
  employeeId: '',
  badgeNumber: '',
  agency: 'CID',
  department: '',
  district: '',
  unit: '',
  supervisor: '',
  role: 'ANALYST',
  forcePasswordChange: true,
  requireMfa: false,
};
