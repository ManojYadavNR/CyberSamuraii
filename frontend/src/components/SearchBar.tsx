import { useState } from 'react';
import { startInvestigation } from '../api/investigate';
import { useInvestigationStore } from '../store/investigationStore';
import type { QueryType } from '../types';

const QUERY_TYPES: { value: QueryType; label: string }[] = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'username', label: 'Username' },
  { value: 'email', label: 'Email' },
  { value: 'phone', label: 'Phone' },
  { value: 'domain', label: 'Domain' },
  { value: 'image', label: 'Image URL' },
];

export function SearchBar() {
  const [input, setInput] = useState('');
  const [queryType, setQueryType] = useState<QueryType>('auto');
  const status = useInvestigationStore((s) => s.status);

  const handleStart = () => {
    const q = input.trim();
    if (!q || status === 'running') return;
    startInvestigation(q, queryType);
  };

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <div className="flex flex-1 gap-2">
        <select
          value={queryType}
          onChange={(e) => setQueryType(e.target.value as QueryType)}
          className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500"
          disabled={status === 'running'}
        >
          {QUERY_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleStart()}
          placeholder="Username, email, phone, domain, or image URL…"
          className="flex-1 rounded-lg border border-slate-600 bg-slate-800 px-4 py-2.5 text-sm placeholder:text-slate-500 outline-none focus:border-blue-500"
          disabled={status === 'running'}
        />
      </div>
      <button
        onClick={handleStart}
        disabled={!input.trim() || status === 'running'}
        className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {status === 'running' ? 'Investigating…' : 'Start Investigation'}
      </button>
    </div>
  );
}
