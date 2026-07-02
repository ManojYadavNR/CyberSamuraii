import { useState } from 'react';
import { confirmPasswordReset, requestPasswordReset } from '../api/enterprise';
import { useUiStore } from '../store/uiStore';

export function PasswordResetPage() {
  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const setPage = useUiStore((s) => s.setPage);

  const handleRequest = async () => {
    setError('');
    const r = await requestPasswordReset(email);
    setMessage(r.message || 'Check your email');
    if (r.reset_token) setToken(r.reset_token);
  };

  const handleConfirm = async () => {
    setError('');
    try {
      await confirmPasswordReset(token, password);
      setMessage('Password updated — you can log in now.');
      setTimeout(() => setPage('dashboard'), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    }
  };

  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-xl font-bold text-white">Password Reset</h1>
      <div className="intel-panel space-y-3 rounded-xl p-5">
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Registered email" className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
        <button type="button" onClick={handleRequest} className="w-full rounded bg-slate-700 py-2 text-sm text-white">Request reset</button>
        <hr className="border-slate-800" />
        <input value={token} onChange={(e) => setToken(e.target.value)} placeholder="Reset token" className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" placeholder="New password (12+ chars, mixed case, number, symbol)" className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
        <button type="button" onClick={handleConfirm} className="w-full rounded bg-cyan-600 py-2 text-sm text-white">Set new password</button>
        {message && <p className="text-xs text-emerald-400">{message}</p>}
        {error && <p className="text-xs text-rose-400">{error}</p>}
        <p className="text-[10px] text-slate-600">Password must be 12+ characters with uppercase, lowercase, number, and special character.</p>
      </div>
    </div>
  );
}
