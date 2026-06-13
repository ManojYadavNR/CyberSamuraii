import { useState } from 'react';
import { startInvestigation, loadInvestigationById } from '../api/investigate';
import { useInvestigationStore } from '../store/investigationStore';
import type { QueryType } from '../types';

const QUERY_TYPES: { value: QueryType; label: string; icon: string }[] = [
  { value: 'auto', label: 'Auto Detect', icon: '◎' },
  { value: 'username', label: 'Username', icon: '👤' },
  { value: 'email', label: 'Email', icon: '✉' },
  { value: 'phone', label: 'Phone', icon: '📱' },
  { value: 'domain', label: 'Domain', icon: '🌐' },
  { value: 'image', label: 'Image', icon: '🖼' },
];

export function SearchBar() {
  const [input, setInput] = useState('');
  const [queryType, setQueryType] = useState<QueryType>('auto');
  const status = useInvestigationStore((s) => s.status);
  const reset = useInvestigationStore((s) => s.reset);
  const recent = useInvestigationStore((s) => s.recentInvestigations);
  const setError = useInvestigationStore((s) => s.setError);

  const handleStart = () => {
    const q = input.trim();
    if (!q || status === 'running') return;
    useInvestigationStore.getState().setQuery(q);
    startInvestigation(q, queryType);
  };

  const handleClear = () => {
    setInput('');
    reset();
  };

  const handleRecent = async (id: string) => {
    try {
      await loadInvestigationById(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    }
  };

  return (
    <div className="intel-panel p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">New Investigation</h2>
          <p className="text-xs text-slate-500">Enter target and select intelligence type</p>
        </div>
        {recent.length > 0 && (
          <select
            className="intel-input max-w-[200px] py-1.5 text-xs"
            defaultValue=""
            onChange={(e) => e.target.value && handleRecent(e.target.value)}
          >
            <option value="" disabled>Recent investigations</option>
            {recent.map((r) => (
              <option key={r.id} value={r.id}>{r.query} ({r.queryType})</option>
            ))}
          </select>
        )}
      </div>

      <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Investigation Type</p>
      <div className="mb-4 flex flex-wrap gap-2">
        {QUERY_TYPES.map((t) => (
          <button
            key={t.value}
            type="button"
            disabled={status === 'running'}
            onClick={() => setQueryType(t.value)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
              queryType === t.value
                ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300'
                : 'border-slate-700/60 bg-slate-800/30 text-slate-400 hover:border-slate-600'
            }`}
          >
            <span className="mr-1.5 opacity-70">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Investigation Target</p>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleStart()}
          placeholder="Username, email, phone, domain, or image URL…"
          className="intel-input flex-1 font-mono"
          disabled={status === 'running'}
        />
        <div className="flex gap-2">
          <button onClick={handleStart} disabled={!input.trim() || status === 'running'} className="intel-btn-primary whitespace-nowrap">
            {status === 'running' ? (
              <span className="flex items-center gap-2">
                <span className="h-2 w-2 animate-pulse-glow rounded-full bg-white" />
                Investigating…
              </span>
            ) : (
              '▶ Start Investigation'
            )}
          </button>
          <button onClick={handleClear} disabled={status === 'running'} className="intel-btn-ghost">
            Clear
          </button>
        </div>
      </div>
    </div>
  );
}
