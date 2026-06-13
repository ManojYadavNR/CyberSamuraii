import { useEffect, useState } from 'react';
import { fetchToolStatus } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';
import type { BackendToolHealth } from '../types';
import { ToolsHealthSummary } from './SystemStatus';

const STATUS_LABEL: Record<BackendToolHealth, string> = {
  healthy: 'Healthy',
  unhealthy: 'Unhealthy',
  not_installed: 'Not Installed',
  missing_api_key: 'Missing API Key',
};

export function ToolsPanel() {
  const toolsHealth = useInvestigationStore((s) => s.toolsHealth);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ tool: string; status: BackendToolHealth } | null>(null);

  useEffect(() => {
    if (!selected) return;
    fetchToolStatus(selected).then(setDetail).catch(() => setDetail(null));
  }, [selected]);

  const entries = Object.entries(toolsHealth);

  if (!entries.length) {
    return <div className="py-8 text-center text-sm text-slate-500">Loading OSINT tool status…</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">OSINT Tool Health</h3>
        <ToolsHealthSummary />
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {entries.map(([tool, status]) => (
          <button
            key={tool}
            onClick={() => setSelected(tool)}
            className={`flex items-center justify-between rounded-xl border px-4 py-3 text-left text-sm transition ${
              selected === tool ? 'border-cyan-500/40 bg-cyan-500/10' : 'border-slate-800/80 bg-slate-900/40 hover:border-slate-600'
            }`}
          >
            <span className="font-mono text-slate-200">{tool}</span>
            <span className={`text-xs capitalize ${
              status === 'healthy' ? 'text-green-400' :
              status === 'missing_api_key' ? 'text-amber-400' :
              status === 'not_installed' ? 'text-slate-500' : 'text-red-400'
            }`}>
              {STATUS_LABEL[status]}
            </span>
          </button>
        ))}
      </div>

      {detail && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-3 text-sm">
          <div className="text-slate-400">GET /api/tools/status/{detail.tool}</div>
          <div className="mt-1 text-slate-200">Status: <strong>{STATUS_LABEL[detail.status]}</strong></div>
        </div>
      )}
    </div>
  );
}
