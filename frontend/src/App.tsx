import { SearchBar } from './components/SearchBar';
import { ProgressTracker } from './components/ProgressTracker';
import { InvestigationSummary } from './components/InvestigationSummary';
import { EvidenceTimeline } from './components/EvidenceTimeline';
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
import { EntityDetailDrawer } from './components/EntityDetailDrawer';
import { useInvestigationStore } from './store/investigationStore';

const TABS = [
  { id: 'results' as const, label: 'Accounts', icon: '👤' },
  { id: 'evidence' as const, label: 'Evidence', icon: '📁' },
  { id: 'graph' as const, label: 'Graph', icon: '🕸' },
  { id: 'investigator' as const, label: 'Reasoning', icon: '💡' },
  { id: 'review' as const, label: 'Review', icon: '✓' },
  { id: 'export' as const, label: 'Export', icon: '📤' },
  { id: 'tools' as const, label: 'Tools', icon: '⚙' },
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
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-[#070b14]/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 text-lg font-bold text-white shadow-lg shadow-cyan-900/40">
              S
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-white">SOCMINT Intelligence</h1>
              <p className="text-[10px] uppercase tracking-[0.15em] text-slate-500">CID Investigation Platform</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <SystemStatus />
            <LoadInvestigation />
            <div className={`rounded-lg border px-3 py-1.5 text-xs font-semibold uppercase tracking-wider ${
              status === 'running' ? 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300' :
              status === 'complete' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' :
              status === 'error' ? 'border-rose-500/30 bg-rose-500/10 text-rose-300' :
              'border-slate-700 bg-slate-800/50 text-slate-400'
            }`}>
              {status === 'idle' ? 'Standby' : status}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-6 py-6">
        <div className="space-y-5">
          <SearchBar />
          <ProgressTracker />
          <InvestigationSummary />
          <EvidenceTimeline />

          {error && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {error}
            </div>
          )}
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-12">
          <section className="xl:col-span-8">
            <div className="intel-panel overflow-hidden">
              <nav className="flex overflow-x-auto border-b border-slate-800/80 bg-slate-900/40">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex shrink-0 items-center gap-2 px-5 py-3.5 text-sm font-medium transition ${
                      activeTab === tab.id ? 'intel-tab-active' : 'text-slate-500 hover:bg-slate-800/30 hover:text-slate-300'
                    }`}
                  >
                    <span className="text-base opacity-70">{tab.icon}</span>
                    {tab.label}
                  </button>
                ))}
              </nav>
              <div className="p-5">
                <TabContent />
              </div>
            </div>
          </section>

          <aside className="xl:col-span-4">
            <div className="intel-panel sticky top-20 h-[calc(100vh-8rem)] p-4">
              <CopilotChat />
            </div>
          </aside>
        </div>
      </main>

      <EntityDetailDrawer />
    </div>
  );
}
