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
        <span className="hidden font-mono text-[10px] text-slate-500 sm:inline" title="Current investigation ID">
          {investigationId.slice(0, 8)}…
        </span>
      )}
      <input
        type="text"
        value={id}
        onChange={(e) => setId(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleLoad()}
        placeholder="Investigation ID…"
        className="w-36 rounded-lg border border-slate-700/80 bg-slate-900/60 px-2.5 py-1.5 text-xs text-slate-200 outline-none transition focus:border-cyan-500/50 sm:w-48"
      />
      <button
        onClick={handleLoad}
        disabled={loading || !id.trim()}
        className="intel-btn-ghost py-1.5 text-xs disabled:opacity-40"
      >
        {loading ? '…' : 'Load'}
      </button>
    </div>
  );
}
