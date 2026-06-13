import { SearchBar } from './components/SearchBar';
import { ProgressTracker } from './components/ProgressTracker';
import { ResultsPanel } from './components/ResultsPanel';
import { EvidencePanel } from './components/EvidencePanel';
import { GraphView } from './components/GraphView';
import { InvestigatorPanel } from './components/InvestigatorPanel';
import { ReviewPanel } from './components/ReviewPanel';
import { CopilotChat } from './components/CopilotChat';
import { ExportPanel } from './components/ExportPanel';
import { ToolsPanel } from './components/ToolsPanel';
import { SystemStatus } from './components/SystemStatus';
import { LoadInvestigation } from './components/LoadInvestigation';
import { useInvestigationStore } from './store/investigationStore';

const TABS = [
  { id: 'results' as const, label: 'Accounts' },
  { id: 'evidence' as const, label: 'Evidence' },
  { id: 'graph' as const, label: 'Graph' },
  { id: 'investigator' as const, label: 'Reasoning' },
  { id: 'review' as const, label: 'Review' },
  { id: 'export' as const, label: 'Export' },
  { id: 'tools' as const, label: 'Tools' },
];

function TabContent() {
  const activeTab = useInvestigationStore((s) => s.activeTab);
  switch (activeTab) {
    case 'results': return <ResultsPanel />;
    case 'evidence': return <EvidencePanel />;
    case 'graph': return <GraphView />;
    case 'investigator': return <InvestigatorPanel />;
    case 'review': return <ReviewPanel />;
    case 'export': return <ExportPanel />;
    case 'tools': return <ToolsPanel />;
  }
}

export default function App() {
  const activeTab = useInvestigationStore((s) => s.activeTab);
  const setActiveTab = useInvestigationStore((s) => s.setActiveTab);
  const error = useInvestigationStore((s) => s.error);
  const status = useInvestigationStore((s) => s.status);

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-900/80 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-slate-100">SOCMINT Investigator</h1>
            <p className="text-xs text-slate-500">CID Intelligence Platform · Fusion · Correlation · Graph</p>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <SystemStatus />
            <LoadInvestigation />
            <div className={`rounded-full px-3 py-1 text-xs font-medium ${
              status === 'running' ? 'bg-blue-500/20 text-blue-300' :
              status === 'complete' ? 'bg-green-500/20 text-green-300' :
              status === 'error' ? 'bg-red-500/20 text-red-300' :
              'bg-slate-700 text-slate-400'
            }`}>
              {status === 'idle' ? 'Ready' : status}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        <section className="mb-6 space-y-4">
          <SearchBar />
          <ProgressTracker />
          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div>
          )}
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
          <section className="lg:col-span-2">
            <div className="rounded-xl border border-slate-700 bg-slate-900/50">
              <div className="flex overflow-x-auto border-b border-slate-700">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`shrink-0 px-4 py-3 text-sm font-medium transition ${
                      activeTab === tab.id
                        ? 'border-b-2 border-blue-500 text-blue-300'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <div className="p-4">
                <TabContent />
              </div>
            </div>
          </section>

          <aside className="rounded-xl border border-slate-700 bg-slate-900/50 p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">AI Copilot</h2>
            <div className="h-[480px]">
              <CopilotChat />
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
