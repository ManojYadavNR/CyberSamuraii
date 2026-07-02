import { useState } from 'react';
import { changePassword } from '../api/auth';
import { useUiStore } from '../store/uiStore';

export function PasswordChangePage() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const setPage = useUiStore((s) => s.setPage);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setMsg(null);
    if (next !== confirm) {
      setError('New passwords do not match');
      return;
    }
    try {
      await changePassword(current, next);
      setMsg('Password updated successfully');
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    }
  };

  return (
    <div className="mx-auto max-w-md space-y-4">
      <div>
        <h1 className="text-xl font-bold text-white">Change Password</h1>
        <p className="text-sm text-slate-500">Update your account credentials</p>
      </div>
      <form onSubmit={submit} className="intel-panel space-y-3 rounded-xl p-5">
        <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="Current password" className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" required />
        <input type="password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="New password" className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" required />
        <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Confirm new password" className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" required />
        {error && <p className="text-sm text-rose-400">{error}</p>}
        {msg && <p className="text-sm text-emerald-400">{msg}</p>}
        <div className="flex gap-2">
          <button type="submit" className="rounded bg-cyan-600 px-4 py-2 text-sm text-white">Update password</button>
          <button type="button" onClick={() => setPage('dashboard')} className="rounded border border-slate-700 px-4 py-2 text-sm text-slate-400">Cancel</button>
        </div>
      </form>
    </div>
  );
}
