import { useState } from 'react';
import { LuTerminal } from 'react-icons/lu';
import { domainIntel, emailIntel, imageIntel, infraIntel, investigateSync, usernameSearch } from '../api/intel';
import { PageSectionHeader } from '../components/PageSectionHeader';
import { useCompactPageHeader } from '../hooks/useCompactPageHeader';
import { useAuthStore } from '../store/authStore';
import { useInvestigationStore } from '../store/investigationStore';
import { useUiStore } from '../store/uiStore';
import { hasPermission } from '../lib/permissions';

type IntelMode = 'username' | 'email' | 'domain' | 'infra' | 'image' | 'sync-investigate';

export function IntelApiPage() {
  const [mode, setMode] = useState<IntelMode>('username');
  const [query, setQuery] = useState('');
  const [imagePath, setImagePath] = useState('');
  const [loading, setLoading] = useState(false);
  const [output, setOutput] = useState<string>('');
  const { scrollRef, headerCompact } = useCompactPageHeader([mode, output.length, loading]);
  const activeCaseId = useAuthStore((s) => s.activeCaseId);
  const role = useAuthStore((s) => s.user?.role || 'VIEWER');
  const canRun = hasPermission(role, 'start_investigation');
  const loadFromServer = useInvestigationStore((s) => s.loadFromServer);
  const openCase = useUiStore((s) => s.openCase);

  const run = async () => {
    if (!canRun) return;
    setLoading(true);
    setOutput('');
    try {
      let result: Record<string, unknown>;
      if (mode === 'username') result = await usernameSearch(query);
      else if (mode === 'email') result = await emailIntel(query);
      else if (mode === 'domain') result = await domainIntel(query);
      else if (mode === 'infra') result = await infraIntel(query);
      else if (mode === 'image') result = await imageIntel({ image_path: imagePath || query });
      else {
        if (!activeCaseId) throw new Error('Select a case first (required for sync investigate)');
        const inv = await investigateSync({ query, case_id: activeCaseId, timeout_per_tool: 120 });
        loadFromServer(inv.investigation_id, query, inv.query_type, inv.result);
        if (activeCaseId) openCase(activeCaseId);
        setOutput(JSON.stringify({ investigation_id: inv.investigation_id, query_type: inv.query_type, entity_count: inv.result?.fusion?.deduplicated_entities?.length ?? 0 }, null, 2));
        return;
      }
      setOutput(JSON.stringify(result, null, 2).slice(0, 12000));
    } catch (err) {
      setOutput(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="intel-page--contained">
      <PageSectionHeader
        title="Direct Intel API"
        subtitle="REST endpoints for username, email, domain, infra, image, and sync investigate"
        compact={headerCompact}
        icon={LuTerminal}
      />
      <div ref={scrollRef} className="intel-page__scroll">
        <div className="space-y-4 pb-2">
          {!canRun && <p className="text-sm text-amber-400">You do not have permission to run investigations.</p>}
          <div className="intel-panel space-y-3 rounded-xl p-4">
            <div className="flex flex-wrap gap-2">
              {(['username', 'email', 'domain', 'infra', 'image', 'sync-investigate'] as IntelMode[]).map((m) => (
                <button key={m} type="button" onClick={() => setMode(m)} className={`rounded px-3 py-1 text-xs ${mode === m ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-400'}`}>{m}</button>
              ))}
            </div>
            {mode === 'image' ? (
              <input value={imagePath || query} onChange={(e) => { setImagePath(e.target.value); setQuery(e.target.value); }} placeholder="image_path or URL" className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
            ) : (
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={mode === 'sync-investigate' ? 'Investigation query (case required)' : 'Query'} className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
            )}
            {mode === 'sync-investigate' && (
              <p className="text-xs text-slate-500">Active case: {activeCaseId || 'none — select a case first'}</p>
            )}
            <button type="button" disabled={loading || !canRun || !query.trim()} onClick={run} className="rounded bg-cyan-600 px-4 py-2 text-sm text-white disabled:opacity-40">
              {loading ? 'Running…' : `POST /api/${mode === 'sync-investigate' ? 'dashboard/investigate' : `intel/${mode === 'username' ? 'username-search' : mode}`}`}
            </button>
          </div>
          {output && <pre className="max-h-[32rem] overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">{output}</pre>}
        </div>
      </div>
    </div>
  );
}
