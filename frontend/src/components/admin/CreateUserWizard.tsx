import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchNextUserIds } from '../../api/enterprise';
import { IntelSelect } from '../ui/IntelSelect';
import type { CreateUserFormState } from './iamTypes';
import { DEFAULT_CREATE_USER } from './iamTypes';
import { agencySelectOptions, roleSelectOptions } from './iamHelpers';
import { getRolePermissions, permissionLabel } from '../../lib/permissions';

const STEPS = ['Personal', 'Organization', 'Access', 'Security', 'Review'] as const;

interface CreateUserWizardProps {
  open: boolean;
  agencies: { id: string; name: string; code?: string }[];
  onClose: () => void;
  onSubmit: (payload: Record<string, string>) => Promise<void>;
}

export function CreateUserWizard({ open, agencies, onClose, onSubmit }: CreateUserWizardProps) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<CreateUserFormState>({ ...DEFAULT_CREATE_USER });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [idsLoading, setIdsLoading] = useState(false);

  const roleOptions = roleSelectOptions();
  const agencyOptions = agencySelectOptions(agencies);

  useEffect(() => {
    if (!open) return;
    setIdsLoading(true);
    fetchNextUserIds()
      .then((ids) => setForm((f) => ({ ...f, employeeId: ids.employee_id, badgeNumber: ids.badge_number })))
      .catch(() => undefined)
      .finally(() => setIdsLoading(false));
  }, [open]);

  if (!open) return null;

  const set = <K extends keyof CreateUserFormState>(key: K, value: CreateUserFormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const handleCreate = async () => {
    setSubmitting(true);
    setError('');
    try {
      const designation = [form.badgeNumber, form.unit].filter(Boolean).join(' · ') || form.district;
      await onSubmit({
        username: form.username.trim(),
        password: form.password,
        name: form.name.trim(),
        email: form.email.trim(),
        role: form.role,
        department: form.department || form.agency || 'CID',
        designation,
        employee_id: form.employeeId,
        badge_number: form.badgeNumber,
      });
      setForm({ ...DEFAULT_CREATE_USER });
      setStep(0);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create user');
    } finally {
      setSubmitting(false);
    }
  };

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));
  const canContinuePersonal = form.name.trim() && form.username.trim() && form.email.trim();
  const canContinueSecurity = form.password.trim().length >= 8;

  const modal = (
    <div className="iam-modal-backdrop" onClick={onClose}>
      <div className="iam-modal iam-create-user-modal" onClick={(e) => e.stopPropagation()}>
        <div className="iam-modal-shell">
          <aside className="iam-modal-side">
            <div className="iam-modal-summary">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-400/80">Provision Identity</p>
              <h2 className="mt-2 text-xl font-bold text-white">Create Investigator Account</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">
                Step through identity, organization, and access controls before provisioning the account.
              </p>
              <div className="iam-wizard-steps mt-6">
                {STEPS.map((label, i) => (
                  <span
                    key={label}
                    className={`iam-wizard-step ${i === step ? 'iam-wizard-step--active' : ''} ${i < step ? 'iam-wizard-step--done' : ''}`}
                  >
                    <span className="iam-wizard-step__index">{i + 1}</span>
                    {label}
                  </span>
                ))}
              </div>
              <div className="mt-6 space-y-3">
                <div className="iam-quick-stat">
                  <p className="iam-field-label">Selected Role</p>
                  <p className="text-sm font-medium text-slate-100">{form.role.replace(/_/g, ' ')}</p>
                </div>
                <div className="iam-quick-stat">
                  <p className="iam-field-label">Agency</p>
                  <p className="text-sm font-medium text-slate-100">{form.agency || 'CID'}</p>
                </div>
                <div className="iam-quick-stat">
                  <p className="iam-field-label">Username</p>
                  <p className="text-sm font-medium text-slate-100">{form.username || 'Not set'}</p>
                </div>
              </div>
            </div>
          </aside>

          <div className="iam-modal-main">
            <div className="iam-modal-header">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-lg font-bold text-white">{STEPS[step]} Configuration</h3>
                  <p className="text-xs text-slate-400">Provision identity, organization context, and access controls.</p>
                </div>
                <button type="button" onClick={onClose} className="iam-modal-close" aria-label="Close">✕</button>
              </div>
            </div>

            <div className="iam-modal-body">
              {step === 0 && (
                <div className="iam-card-grid">
                  <div className="iam-card col-span-full">
                    <h3 className="mb-4 text-sm font-semibold text-white">Personal Information</h3>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <label className="block">
                        <span className="iam-field-label">Full Name</span>
                        <input className="iam-input" value={form.name} onChange={(e) => set('name', e.target.value)} />
                      </label>
                      <label className="block">
                        <span className="iam-field-label">Username</span>
                        <input className="iam-input" value={form.username} onChange={(e) => set('username', e.target.value)} />
                      </label>
                      <label className="block">
                        <span className="iam-field-label">Email</span>
                        <input type="email" className="iam-input" value={form.email} onChange={(e) => set('email', e.target.value)} />
                      </label>
                      <label className="block">
                        <span className="iam-field-label">Phone</span>
                        <input className="iam-input" value={form.phone} onChange={(e) => set('phone', e.target.value)} placeholder="Operational contact" />
                      </label>
                      <label className="block">
                        <span className="iam-field-label">Employee ID</span>
                        <input className="iam-input iam-input--readonly" value={form.employeeId} readOnly placeholder={idsLoading ? 'Generating…' : ''} />
                      </label>
                      <label className="block">
                        <span className="iam-field-label">Badge Number</span>
                        <input className="iam-input iam-input--readonly" value={form.badgeNumber} readOnly placeholder={idsLoading ? 'Generating…' : ''} />
                      </label>
                      <IntelSelect
                        label="Role"
                        value={form.role}
                        options={roleOptions}
                        onChange={(next) => set('role', next)}
                        className="iam-intel-select"
                        size="sm"
                      />
                      <IntelSelect
                        label="Primary Agency"
                        value={form.agency}
                        options={agencyOptions}
                        onChange={(next) => set('agency', next)}
                        className="iam-intel-select"
                        size="sm"
                      />
                    </div>
                  </div>
                </div>
              )}

              {step === 1 && (
                <div className="iam-card">
                  <h3 className="mb-4 text-sm font-semibold text-white">Organization</h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <IntelSelect
                      label="Agency"
                      value={form.agency}
                      options={agencyOptions}
                      onChange={(next) => set('agency', next)}
                      className="iam-intel-select"
                      size="sm"
                    />
                    <label className="block">
                      <span className="iam-field-label">Department</span>
                      <input className="iam-input" value={form.department} onChange={(e) => set('department', e.target.value)} />
                    </label>
                    <label className="block">
                      <span className="iam-field-label">District</span>
                      <input className="iam-input" value={form.district} onChange={(e) => set('district', e.target.value)} />
                    </label>
                    <label className="block">
                      <span className="iam-field-label">Unit</span>
                      <input className="iam-input" value={form.unit} onChange={(e) => set('unit', e.target.value)} />
                    </label>
                    <label className="block sm:col-span-2">
                      <span className="iam-field-label">Supervisor</span>
                      <input className="iam-input" value={form.supervisor} onChange={(e) => set('supervisor', e.target.value)} placeholder="Reporting officer" />
                    </label>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="iam-card">
                  <h3 className="mb-4 text-sm font-semibold text-white">Access</h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <IntelSelect
                      label="Role"
                      value={form.role}
                      options={roleOptions}
                      onChange={(next) => set('role', next)}
                      className="iam-intel-select"
                      size="sm"
                    />
                    <label className="block opacity-60">
                      <span className="iam-field-label">Case Visibility</span>
                      <input className="iam-input" disabled value="Agency default" />
                    </label>
                  </div>
                  <div className="mt-4">
                    <p className="iam-field-label">Permissions granted by this role</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {getRolePermissions(form.role).map((perm) => (
                        <span key={perm} className="iam-badge-soft">{permissionLabel(perm)}</span>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="iam-card">
                  <h3 className="mb-4 text-sm font-semibold text-white">Security</h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block sm:col-span-2">
                      <span className="iam-field-label">Temporary Password</span>
                      <input type="password" className="iam-input" value={form.password} onChange={(e) => set('password', e.target.value)} autoComplete="new-password" />
                      <p className="mt-1 text-[11px] text-slate-500">Minimum 8 characters required.</p>
                    </label>
                    <label className="flex items-center gap-2 text-sm text-slate-300">
                      <input type="checkbox" checked={form.forcePasswordChange} onChange={(e) => set('forcePasswordChange', e.target.checked)} disabled />
                      Force password change on first login
                    </label>
                    <label className="flex items-center gap-2 text-sm text-slate-300">
                      <input type="checkbox" checked={form.requireMfa} onChange={(e) => set('requireMfa', e.target.checked)} disabled />
                      Require MFA (policy-managed)
                    </label>
                    <label className="block opacity-60">
                      <span className="iam-field-label">Account Expiry</span>
                      <input className="iam-input" disabled placeholder="Not configured" />
                    </label>
                    <label className="block opacity-60">
                      <span className="iam-field-label">Maximum Sessions</span>
                      <input className="iam-input" disabled value="1" />
                    </label>
                  </div>
                </div>
              )}

              {step === 4 && (
                <div className="iam-card">
                  <h3 className="mb-4 text-sm font-semibold text-white">Review & Provision</h3>
                  <dl className="iam-review-grid">
                    {[
                      ['Name', form.name], ['Username', form.username], ['Email', form.email],
                      ['Role', form.role.replace(/_/g, ' ')], ['Agency', form.agency], ['Department', form.department || '—'],
                      ['District', form.district || '—'], ['Supervisor', form.supervisor || '—'],
                    ].map(([k, v]) => (
                      <div key={k} className="iam-review-row">
                        <dt>{k}</dt>
                        <dd>{v}</dd>
                      </div>
                    ))}
                  </dl>
                  {error && <p className="mt-3 text-xs text-rose-400">{error}</p>}
                </div>
              )}
            </div>

            <div className="iam-modal-footer">
              <button type="button" onClick={step === 0 ? onClose : back} className="iam-btn-ghost">
                {step === 0 ? 'Cancel' : 'Back'}
              </button>
              {step < STEPS.length - 1 ? (
                <button
                  type="button"
                  onClick={next}
                  disabled={(step === 0 && !canContinuePersonal) || (step === 3 && !canContinueSecurity)}
                  className="iam-btn-primary disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Continue
                </button>
              ) : (
                <button type="button" onClick={handleCreate} disabled={submitting || !canContinueSecurity} className="iam-btn-primary disabled:cursor-not-allowed disabled:opacity-50">
                  {submitting ? 'Creating…' : 'Create User'}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}
