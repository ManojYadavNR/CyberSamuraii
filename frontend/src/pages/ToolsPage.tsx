import { useEffect, useState } from 'react';
import { fetchOsintCatalog, fetchToolRoute, fetchToolsStatus, reloadToolsRegistry, setToolEnabled } from '../api/client';
import { ToolsPanel } from '../components/ToolsPanel';
import { useInvestigationStore } from '../store/investigationStore';
import { hasPermission } from '../lib/permissions';
import { useAuthStore } from '../store/authStore';

export function ToolsPage() {
  const setToolsHealth = useInvestigationStore((s) => s.setToolsHealth);
  const role = useAuthStore((s) => s.user?.role || 'VIEWER');
  const canManage = hasPermission(role, 'manage_users');
  const [inputType, setInputType] = useState('username');
  const [routePlan, setRoutePlan] = useState<string>('');
  const [catalogSize, setCatalogSize] = useState(0);
  const [toolName, setToolName] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    fetchToolsStatus().then(setToolsHealth).catch(() => {});
    fetchOsintCatalog().then((c) => {
      const tools = (c.tools as unknown[]) || Object.keys(c);
      setCatalogSize(Array.isArray(tools) ? tools.length : Object.keys(c).length);
    }).catch(() => {});
  }, [setToolsHealth]);

  const reload = async () => {
    const r = await reloadToolsRegistry();
    setMsg('Registry reloaded');
    setToolsHealth(await fetchToolsStatus());
    setRoutePlan(JSON.stringify(r, null, 2).slice(0, 4000));
  };

  const route = async () => {
    const r = await fetchToolRoute(inputType);
    setRoutePlan(JSON.stringify(r, null, 2));
  };

  const toggleTool = async () => {
    if (!toolName.trim()) return;
    await setToolEnabled(toolName.trim(), enabled);
    setMsg(`Tool ${toolName} ${enabled ? 'enabled' : 'disabled'}`);
    setToolsHealth(await fetchToolsStatus());
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">OSINT Tools</h1>
        <p className="text-sm text-slate-500">Health status, routing, and registry ({catalogSize} catalog entries)</p>
      </div>
      <div className="intel-panel rounded-xl p-4">
        <ToolsPanel />
      </div>
      {canManage && (
        <div className="intel-panel space-y-3 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-white">Admin controls</h2>
          <button type="button" onClick={reload} className="rounded bg-slate-700 px-3 py-1 text-xs text-white">POST /api/tools/reload</button>
          <div className="flex flex-wrap gap-2">
            <input value={inputType} onChange={(e) => setInputType(e.target.value)} placeholder="input_type" className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs" />
            <button type="button" onClick={route} className="rounded bg-slate-700 px-3 py-1 text-xs text-white">GET route</button>
          </div>
          <div className="flex flex-wrap gap-2">
            <input value={toolName} onChange={(e) => setToolName(e.target.value)} placeholder="tool_name" className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs" />
            <label className="flex items-center gap-1 text-xs text-slate-400">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> enabled
            </label>
            <button type="button" onClick={toggleTool} className="rounded bg-slate-700 px-3 py-1 text-xs text-white">PATCH enabled</button>
          </div>
          {msg && <p className="text-xs text-emerald-400">{msg}</p>}
          {routePlan && <pre className="max-h-48 overflow-auto text-[10px] text-slate-400">{routePlan}</pre>}
        </div>
      )}
    </div>
  );
}
