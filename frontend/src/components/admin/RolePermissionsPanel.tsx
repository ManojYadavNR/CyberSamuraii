import { useMemo, useState } from 'react';
import type { IamUser } from './iamTypes';
import { getRolePermissions, permissionLabel } from '../../lib/permissions';

const DISPLAY_ROLES = ['SUPER_ADMIN', 'CID_DIRECTOR', 'SP', 'DSP', 'INSPECTOR', 'ANALYST', 'VIEWER', 'AUDITOR'];

interface RolePermissionsPanelProps {
  users: IamUser[];
  onCreateUser: () => void;
}

export function RolePermissionsPanel({ users, onCreateUser }: RolePermissionsPanelProps) {
  const [selectedRole, setSelectedRole] = useState('ANALYST');

  const roleCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    users.forEach((u) => { counts[u.role] = (counts[u.role] || 0) + 1; });
    return counts;
  }, [users]);

  const permissions = getRolePermissions(selectedRole);

  return (
    <div className="iam-card">
      <h3 className="text-sm font-semibold text-white">Roles & Permissions</h3>
      <p className="mt-1 text-xs text-slate-500">
        Assign a role when creating a user. Permissions are inherited automatically from the role policy.
      </p>

      <div className="mt-4 rounded-lg border border-cyan-500/20 bg-cyan-950/20 px-3 py-2.5 text-xs text-cyan-100">
        <strong>How to set access:</strong> click <button type="button" onClick={onCreateUser} className="font-semibold text-cyan-300 underline">Create User</button>, choose a role in the wizard, then provision the account. To change an existing user&apos;s role, use the admin API or recreate the account.
      </div>

      <div className="mt-4">
        <p className="iam-field-label">Select role to inspect</p>
        <div className="flex flex-wrap gap-2">
          {DISPLAY_ROLES.map((role) => (
            <button
              key={role}
              type="button"
              onClick={() => setSelectedRole(role)}
              className={`rounded-full border px-2.5 py-1 text-[10px] transition ${
                selectedRole === role
                  ? 'border-cyan-500/50 bg-cyan-950/40 text-cyan-200'
                  : 'border-slate-700 text-slate-400 hover:border-slate-500'
              }`}
            >
              {role.replace(/_/g, ' ')} · {roleCounts[role] || 0}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <p className="iam-field-label">Inherited permissions</p>
        <div className="flex flex-wrap gap-2">
          {permissions.length === 0 ? (
            <span className="text-xs text-slate-500">No permissions mapped for this role.</span>
          ) : permissions.map((perm) => (
            <span key={perm} className="iam-badge-soft text-cyan-100/90">
              {permissionLabel(perm)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
