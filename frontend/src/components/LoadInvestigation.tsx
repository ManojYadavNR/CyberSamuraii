import { useState } from 'react';
import { loadInvestigationById } from '../api/investigate';
import { useInvestigationStore } from '../store/investigationStore';

export function LoadInvestigation() {
  const [id, setId] = useState('');
  const [loading, setLoading] = useState(false);
  const setError = useInvestigationStore((s) => s.setError);
  const investigationId = useInvestigationStore((s) => s.investigationId);

  const handleLoad = async () => {
    const trimmed = id.trim();
    if (!trimmed) return;
    setLoading(true);
    try {
      await loadInvestigationById(trimmed);
      setId('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load investigation');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {investigationId && (
        <span className="hidden font-mono text-xs text-slate-500 sm:inline" title="Current investigation ID">
          ID: {investigationId.slice(0, 8)}…
        </span>
      )}
      <input
        type="text"
        value={id}
        onChange={(e) => setId(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleLoad()}
        placeholder="Load investigation ID…"
        className="w-40 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs outline-none focus:border-blue-500 sm:w-52"
      />
      <button
        onClick={handleLoad}
        disabled={loading || !id.trim()}
        className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
      >
        {loading ? '…' : 'Load'}
      </button>
    </div>
  );
}
