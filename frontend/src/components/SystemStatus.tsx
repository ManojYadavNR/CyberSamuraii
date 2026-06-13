import { useEffect } from 'react';
import { fetchHealth, fetchToolsStatus } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';
import type { BackendToolHealth } from '../types';

export function SystemStatus() {
  const backendHealth = useInvestigationStore((s) => s.backendHealth);
  const toolsHealth = useInvestigationStore((s) => s.toolsHealth);
  const setBackendHealth = useInvestigationStore((s) => s.setBackendHealth);
  const setToolsHealth = useInvestigationStore((s) => s.setToolsHealth);

  useEffect(() => {
    const check = async () => {
      setBackendHealth('checking');
      try {
        const health = await fetchHealth();
        setBackendHealth(health.status === 'ok' ? 'ok' : 'down');
        setToolsHealth(await fetchToolsStatus());
      } catch {
        setBackendHealth('down');
      }
    };
    check();
    const interval = setInterval(check, 60000);
    return () => clearInterval(interval);
  }, [setBackendHealth, setToolsHealth]);

  const healthy = Object.values(toolsHealth).filter((s) => s === 'healthy').length;
  const total = Object.keys(toolsHealth).length;

  return (
    <div className="flex items-center gap-3 text-[10px] font-semibold uppercase tracking-wider">
      <StatusPill ok={backendHealth === 'ok'} warn={backendHealth === 'checking'} label="API" />
      {total > 0 && <StatusPill ok={healthy === total} warn={healthy > 0 && healthy < total} label={`OSINT ${healthy}/${total}`} />}
    </div>
  );
}

function StatusPill({ ok, warn, label }: { ok: boolean; warn?: boolean; label: string }) {
  return (
    <span className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${
      ok ? 'border-emerald-500/30 text-emerald-400' : warn ? 'border-amber-500/30 text-amber-400' : 'border-rose-500/30 text-rose-400'
    }`}>
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-emerald-400' : warn ? 'bg-amber-400' : 'bg-rose-400'}`} />
      {label}
    </span>
  );
}

export function ToolsHealthSummary() {
  const toolsHealth = useInvestigationStore((s) => s.toolsHealth);
  const STATUS_STYLE: Record<BackendToolHealth, string> = {
    healthy: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300',
    unhealthy: 'border-rose-500/25 bg-rose-500/10 text-rose-300',
    not_installed: 'border-slate-600 bg-slate-800/50 text-slate-500',
    missing_api_key: 'border-amber-500/25 bg-amber-500/10 text-amber-300',
  };

  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(toolsHealth).map(([tool, status]) => (
        <span key={tool} className={`rounded border px-2 py-0.5 font-mono text-[10px] ${STATUS_STYLE[status]}`}>
          {tool}
        </span>
      ))}
    </div>
  );
}
