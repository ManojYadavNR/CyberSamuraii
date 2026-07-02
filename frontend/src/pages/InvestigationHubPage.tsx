import { GraphView } from '../components/GraphView';
import { EvidencePanel } from '../components/EvidencePanel';
import { ExportPanel } from '../components/ExportPanel';
import { useUiStore, type AppPage } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import { generateCaseReport } from '../api/enterprise';

export function InvestigationHubPage({ mode }: { mode: AppPage }) {
  const caseId = useUiStore((s) => s.selectedCaseId) || useAuthStore((s) => s.activeCaseId);
  const openCase = useUiStore((s) => s.openCase);

  if (!caseId) {
    return (
      <div className="intel-panel rounded-xl p-8 text-center">
        <p className="text-slate-400">Open a case workspace first to view {mode}.</p>
        <button type="button" onClick={() => openCase('')} className="mt-3 text-sm text-cyan-400">Go to Cases</button>
      </div>
    );
  }

  if (mode === 'graph') return <div className="intel-panel rounded-xl p-4"><GraphView /></div>;
  if (mode === 'evidence') return <div className="intel-panel rounded-xl p-4"><EvidencePanel /></div>;
  if (mode === 'reports') {
    return (
      <div className="space-y-4">
        <ExportPanel />
        <div className="flex gap-2">
          {(['json', 'html', 'docx'] as const).map((fmt) => (
            <button
              key={fmt}
              type="button"
              onClick={async () => {
                const r = await generateCaseReport(caseId, fmt);
                const blob = new Blob([typeof r.content === 'string' ? r.content : JSON.stringify(r.content, null, 2)], { type: fmt === 'html' ? 'text/html' : 'application/json' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = r.filename || `report.${fmt}`;
                a.click();
              }}
              className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800"
            >
              Case report ({fmt.toUpperCase()})
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="intel-panel rounded-xl p-8 text-center text-slate-400">
      Use Case Workspace → Investigate for live investigations.
    </div>
  );
}
