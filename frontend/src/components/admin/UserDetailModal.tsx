import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { updateUser } from '../../api/enterprise';
import { IntelSelect } from '../ui/IntelSelect';
import type { IamUser } from './iamTypes';
import { roleBadgeClass, roleSelectOptions, userInitials, userStatus } from './iamHelpers';
import { getRolePermissions, permissionLabel } from '../../lib/permissions';

interface UserDetailModalProps {
  user: IamUser | null;
  onClose: () => void;
  onUpdated: () => void;
}

export function UserDetailModal({ user, onClose, onUpdated }: UserDetailModalProps) {
  const [role, setRole] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (user) {
      setRole(user.role);
      setError('');
      setSaved(false);
    }
  }, [user]);

  if (!user) return null;

  const status = userStatus(user);
  const permissions = getRolePermissions(role);
  const roleChanged = role !== user.role;
  const roleOptions = roleSelectOptions();

  const handleSaveRole = async () => {
    setSaving(true);
    setError('');
    try {
      await updateUser(user.user_id, { role });
      setSaved(true);
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update user');
    } finally {
      setSaving(false);
    }
  };

  const profileFields = [
    ['Employee ID', user.employee_id || '—'],
    ['Badge Number', user.badge_number || '—'],
    ['Email', user.email || '—'],
    ['Department', user.department || 'CID'],
    ['Designation', user.designation || '—'],
    ['Last Login', user.last_login ? user.last_login.slice(0, 19).replace('T', ' ') : 'Never'],
    ['MFA', user.mfa_enabled ? 'Enabled' : 'Disabled'],
    ['Password Policy', user.must_change_password ? 'Must change on login' : 'Compliant'],
  ] as const;

  const modal = (
    <div className="iam-modal-backdrop" onClick={onClose}>
      <div className="iam-modal iam-user-detail-modal" onClick={(e) => e.stopPropagation()}>
        <div className="iam-user-detail-header">
          <div className="flex items-start gap-4">
            <div className="iam-avatar h-14 w-14 shrink-0 text-base shadow-lg shadow-cyan-900/20">
              {userInitials(user)}
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-xl font-bold text-white">{user.name}</h2>
              <p className="text-sm text-slate-400">@{user.username}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <span className={`iam-role ${roleBadgeClass(user.role)}`}>{user.role.replace(/_/g, ' ')}</span>
                <span className={`iam-status ${status.className}`}>{status.label}</span>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="iam-modal-close"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="iam-user-detail-body">
          <div className="iam-user-detail-section">
            <p className="iam-field-label">Change role & permissions</p>
            <p className="mb-4 text-sm leading-relaxed text-slate-400">
              Permissions are inherited from the assigned role. Select a new role and save to update this user&apos;s access.
            </p>
            <div className="iam-user-detail-role-row">
              <IntelSelect
                label="Role"
                value={role}
                options={roleOptions}
                onChange={(next) => { setRole(next); setSaved(false); }}
                className="iam-intel-select iam-intel-select--grow"
                size="sm"
              />
              <button
                type="button"
                onClick={handleSaveRole}
                disabled={saving || !roleChanged}
                className="iam-btn-primary iam-btn-primary--compact disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? 'Saving…' : 'Save Role'}
              </button>
            </div>
            {error && <p className="mt-2 text-xs text-rose-400">{error}</p>}
            {saved && <p className="mt-2 text-xs text-emerald-400">Role updated successfully.</p>}
          </div>

          <div className="iam-user-detail-section">
            <p className="iam-field-label">Inherited permissions</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {permissions.map((perm) => (
                <span key={perm} className="iam-badge-soft text-cyan-100">{permissionLabel(perm)}</span>
              ))}
            </div>
          </div>

          <div className="iam-user-detail-section iam-user-detail-section--flat">
            <p className="iam-field-label mb-3">Profile details</p>
            <dl className="iam-user-detail-fields iam-user-detail-fields--grid">
              {profileFields.map(([k, v]) => (
                <div key={k} className="iam-user-detail-row">
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}
