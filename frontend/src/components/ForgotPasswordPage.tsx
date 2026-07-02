import { useState } from 'react';
import { confirmPasswordReset, submitPasswordResetWorkflow } from '../api/enterprise';

function PasswordField({
  id,
  value,
  onChange,
  placeholder,
  compact = false,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  compact?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  const inputClass = compact
    ? 'w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 pr-10 text-xs'
    : 'w-full rounded-lg border border-slate-700 bg-slate-950 py-2.5 pl-3 pr-10 text-white outline-none focus:border-cyan-500';

  return (
    <div className="relative">
      <input
        id={id}
        type={visible ? 'text' : 'password'}
        className={inputClass}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="new-password"
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        className="absolute right-2 top-1/2 -translate-y-1/2 rounded px-2 py-1 text-[10px] font-medium text-slate-400 hover:text-cyan-300"
        aria-label={visible ? 'Hide password' : 'Show password'}
      >
        {visible ? 'Hide' : 'Show'}
      </button>
    </div>
  );
}

interface ForgotPasswordPageProps {
  onBack: () => void;
}

export function ForgotPasswordPage({ onBack }: ForgotPasswordPageProps) {
  const [employeeId, setEmployeeId] = useState('');
  const [reason, setReason] = useState('');
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [password, setPassword] = useState('');
  const [devMsg, setDevMsg] = useState('');

  const submit = async () => {
    setLoading(true);
    setMsg('');
    setError('');
    try {
      const r = await submitPasswordResetWorkflow(employeeId, reason);
      setMsg(r.message || 'Request submitted. A supervisor and administrator must approve before your password is reset.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#070b14] px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/80 p-8 shadow-2xl">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 text-xl font-bold text-white">
            S
          </div>
          <h1 className="text-xl font-bold text-white">Password Reset</h1>
          <p className="mt-1 text-xs uppercase tracking-widest text-slate-500">CID Investigation Platform</p>
        </div>

        <div className="space-y-4">
          <p className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-xs leading-relaxed text-slate-400">
            CID password reset requires identity verification, supervisor approval, and administrator authorization.
            No self-service OTP reset.
          </p>

          <div>
            <label htmlFor="reset-employee-id" className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">
              Employee ID (username)
            </label>
            <input
              id="reset-employee-id"
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="e.g. inspector1"
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-white outline-none focus:border-cyan-500"
              autoComplete="username"
            />
          </div>

          <div>
            <label htmlFor="reset-reason" className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">
              Reason for reset (optional)
            </label>
            <textarea
              id="reset-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Brief operational justification"
              rows={3}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-500"
            />
          </div>

          {error && <p className="text-sm text-rose-400">{error}</p>}
          {msg && <p className="text-sm text-emerald-400">{msg}</p>}

          <button
            type="button"
            disabled={loading || !employeeId.trim()}
            onClick={submit}
            className="w-full rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 py-2.5 text-sm font-semibold text-white hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50"
          >
            {loading ? 'Submitting…' : 'Submit reset request'}
          </button>
        </div>

        <details className="mt-6 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-left">
          <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-slate-600">
            Dev-only email reset
          </summary>
          <div className="mt-3 space-y-2">
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs"
            />
            <button
              type="button"
              onClick={() => import('../api/enterprise').then((m) => m.requestPasswordReset(email).then((r) => {
                setDevMsg(r.message || 'Sent');
                if (r.reset_token) setToken(r.reset_token);
              }))}
              className="text-[10px] text-cyan-400 hover:text-cyan-300"
            >
              Request token
            </button>
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Token"
              className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs"
            />
            <PasswordField id="reset-password" value={password} onChange={setPassword} placeholder="New password" compact />
            <button
              type="button"
              onClick={() => confirmPasswordReset(token, password).then(() => setDevMsg('Password updated')).catch((e) => setDevMsg(e.message))}
              className="text-[10px] text-emerald-400 hover:text-emerald-300"
            >
              Set password
            </button>
            {devMsg && <p className="text-[10px] text-slate-400">{devMsg}</p>}
          </div>
        </details>

        <button
          type="button"
          onClick={onBack}
          className="mt-6 w-full text-center text-sm text-cyan-400 hover:text-cyan-300"
        >
          ← Back to sign in
        </button>
      </div>
    </div>
  );
}
