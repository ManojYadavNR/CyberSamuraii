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
        const tools = await fetchToolsStatus();
        setToolsHealth(tools);
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
    <div className="flex items-center gap-3 text-xs">
      <StatusDot
        label="API"
        ok={backendHealth === 'ok'}
        warn={backendHealth === 'checking'}
        title={backendHealth === 'ok' ? 'Backend healthy' : backendHealth === 'checking' ? 'Checking…' : 'Backend offline'}
      />
      {total > 0 && (
        <StatusDot
          label={`Tools ${healthy}/${total}`}
          ok={healthy === total}
          warn={healthy > 0 && healthy < total}
          title={`${healthy} of ${total} OSINT tools healthy`}
        />
      )}
    </div>
  );
}

function StatusDot({ label, ok, warn, title }: { label: string; ok: boolean; warn?: boolean; title: string }) {
  const color = ok ? 'bg-green-400' : warn ? 'bg-amber-400' : 'bg-red-400';
  return (
    <div className="flex items-center gap-1.5 text-slate-400" title={title}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span>{label}</span>
    </div>
  );
}

export function ToolsHealthSummary() {
  const toolsHealth = useInvestigationStore((s) => s.toolsHealth);
  const entries = Object.entries(toolsHealth);
  if (!entries.length) return null;

  const STATUS_STYLE: Record<BackendToolHealth, string> = {
    healthy: 'text-green-400 border-green-500/30 bg-green-500/10',
    unhealthy: 'text-red-400 border-red-500/30 bg-red-500/10',
    not_installed: 'text-slate-500 border-slate-600 bg-slate-800',
    missing_api_key: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
  };

  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([tool, status]) => (
        <span key={tool} className={`rounded px-2 py-0.5 text-xs border ${STATUS_STYLE[status]}`}>
          {tool}
        </span>
      ))}
    </div>
  );
}
