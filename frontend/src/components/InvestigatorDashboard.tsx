import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import { buildIntelligenceSections, investigationBrief, type IntelligenceItem, type IntelligenceSection } from '../lib/intelligenceView';
import { Badge } from './ui/Badge';
import { ConfidenceBar } from './ui/ConfidenceBar';
import { EmptyState } from './ui/EmptyState';
import { GraphView } from './GraphView';

function ItemRow({ item }: { item: IntelligenceItem }) {
  const renderAs = item.metadata?.renderAs as string | undefined;

  if (renderAs === 'image') {
    return (
      <div className="px-5 py-3">
        <div className="flex flex-wrap items-start gap-4">
          <img
            src={item.value}
            alt={item.label}
            className="h-24 w-24 rounded-lg border border-slate-700 object-cover"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{item.label}</p>
            <a href={item.value} target="_blank" rel="noreferrer" className="mt-1 block break-all text-xs text-cyan-400 hover:underline">
              {item.value}
            </a>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {item.sourcePlatform && <Badge variant="muted">{item.sourcePlatform}</Badge>}
              {item.source && <Badge variant="muted">{item.source}</Badge>}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (renderAs === 'youtube') {
    const videoId = item.value.match(/(?:v=|youtu\.be\/|@)([A-Za-z0-9_-]{6,})/)?.[1];
    return (
      <div className="px-5 py-3">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">YouTube</p>
        <p className="mt-0.5 text-sm font-medium text-white">{item.label}</p>
        <a href={item.value} target="_blank" rel="noreferrer" className="mt-1 block break-all font-mono text-xs text-cyan-400 hover:underline">
          {item.value}
        </a>
        {item.provenance && <p className="mt-2 text-xs leading-relaxed text-slate-400">{item.provenance}</p>}
        {videoId && !item.value.includes('/@') && (
          <div className="mt-3 aspect-video max-w-md overflow-hidden rounded-lg border border-slate-700">
            <iframe
              title={item.label}
              src={`https://www.youtube.com/embed/${videoId}`}
              className="h-full w-full"
              allowFullScreen
            />
          </div>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {item.sourcePlatform && <Badge variant="muted">{item.sourcePlatform}</Badge>}
          {item.source && <Badge variant="muted">{item.source}</Badge>}
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{item.label}</p>
          <p className="mt-0.5 break-words font-mono text-sm text-cyan-100">{item.value}</p>
          {item.provenance && <p className="mt-1 text-xs leading-relaxed text-slate-400">{item.provenance}</p>}
        </div>
        {item.confidence != null && item.confidence <= 1 && (
          <span className="shrink-0 font-mono text-xs text-emerald-400">{(item.confidence * 100).toFixed(0)}%</span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {item.sourcePlatform && <Badge variant="muted">{item.sourcePlatform}</Badge>}
        {item.source && <Badge variant="muted">{item.source}</Badge>}
      </div>
      {item.confidence != null && item.confidence <= 1 && (
        <div className="mt-2"><ConfidenceBar score={item.confidence * 100} /></div>
      )}
    </div>
  );
}

function SectionCard({ title, icon, description, items, id }: IntelligenceSection) {
  const isPhotoGrid = id === 'photos';

  return (
    <section className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-slate-900/40 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <div>
            <h3 className="text-sm font-semibold text-white">{title}</h3>
            <p className="text-[11px] text-slate-500">{description}</p>
          </div>
          <Badge variant="info" className="ml-auto">{items.length}</Badge>
        </div>
      </div>
      {isPhotoGrid && items.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 p-5 sm:grid-cols-3">
          {items.map((item) => (
            <a
              key={item.id}
              href={item.value}
              target="_blank"
              rel="noreferrer"
              className="group overflow-hidden rounded-lg border border-slate-800 bg-slate-900/50"
            >
              <img
                src={item.value}
                alt={item.label}
                className="aspect-square w-full object-cover transition group-hover:scale-105"
                loading="lazy"
                referrerPolicy="no-referrer"
              />
              <div className="px-2 py-1.5">
                <p className="truncate text-[10px] text-slate-400">{item.sourcePlatform || item.source}</p>
              </div>
            </a>
          ))}
        </div>
      ) : (
        <div className="divide-y divide-slate-800/60">
          {items.map((item) => (
            <ItemRow key={item.id} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}

export function InvestigatorDashboard() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);

  const sections = useMemo(() => buildIntelligenceSections(result, query), [result, query]);
  const brief = useMemo(() => investigationBrief(result, query), [result, query]);

  if (!result) {
    return (
      <EmptyState
        icon="🕵️"
        title="Investigator workspace"
        description="Run an investigation to see the complete intelligence profile — identity, evidence, paths, and recommended leads."
      />
    );
  }

  const contentSections = sections.filter((s) => s.id !== 'identity');
  const identitySection = sections.find((s) => s.id === 'identity');

  return (
    <div className="space-y-6">
      <div className="intel-card bg-gradient-to-br from-slate-900/90 to-cyan-950/20 p-5">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-500/80">Case Brief</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">{brief.who}</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <BriefRow label="What was discovered?" value={brief.what} />
          <BriefRow label="Why do we believe it?" value={brief.why} />
          <BriefRow label="How was it discovered?" value={brief.how} />
          <BriefRow label="What to investigate next?" value={brief.next} />
        </div>
      </div>

      {identitySection && identitySection.items.length > 0 && (
        <SectionCard {...identitySection} />
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {contentSections.map((section) => (
          <SectionCard key={section.id} {...section} />
        ))}
      </div>

      {contentSections.length === 0 && (
        <EmptyState icon="📭" title="Limited intelligence" description="Only seed data available. Enable discovery or run additional pivots to enrich the profile." />
      )}

      <section>
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-white">🕸 Knowledge Graph</h3>
          <p className="text-xs text-slate-500">Connected intelligence structure with evidence-backed relationships</p>
        </div>
        <GraphView />
      </section>
    </div>
  );
}

function BriefRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800/80 bg-slate-900/50 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-sm leading-relaxed text-slate-200">{value}</p>
    </div>
  );
}
