import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import {
  buildImageInvestigationSections,
  imageInvestigationBrief,
} from '../lib/imageInvestigationView';
import type { IntelligenceItem } from '../lib/intelligenceView';
import type { IntelligenceSection } from '../lib/intelligenceView';
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
            className="h-20 w-20 rounded-lg border border-slate-700 object-cover"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{item.label}</p>
            <a href={item.value} target="_blank" rel="noreferrer" className="mt-1 block break-all text-xs text-cyan-400 hover:underline">
              {item.value}
            </a>
            {item.provenance && <p className="mt-1 text-xs text-slate-400">{item.provenance}</p>}
          </div>
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

function EvidenceChainCard({ item }: { item: IntelligenceItem }) {
  const links = (item.metadata?.links ?? []) as Array<{ step: string; value: string; source?: string; confidence?: number }>;
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-cyan-400">Evidence path</p>
        {item.confidence != null && (
          <span className="font-mono text-xs text-emerald-400">{(item.confidence * 100).toFixed(0)}%</span>
        )}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {links.map((link, i) => (
          <div key={`${link.step}_${i}`} className="flex items-center gap-2">
            <div className="rounded-md border border-slate-700 bg-slate-800/60 px-2 py-1.5">
              <p className="text-[9px] font-bold uppercase text-slate-500">{link.step}</p>
              <p className="max-w-[200px] truncate font-mono text-[11px] text-slate-200" title={link.value}>
                {link.value}
              </p>
              {link.source && <p className="text-[9px] text-slate-500">{link.source}</p>}
            </div>
            {i < links.length - 1 && <span className="text-slate-600">→</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function SectionCard({ title, icon, description, items, id }: IntelligenceSection) {
  const isPhotoGrid = id === 'photos';
  const isChains = id === 'evidence_chains';
  const isGraph = id === 'intelligence_graph';

  if (isGraph) {
    return (
      <section className="intel-card overflow-hidden xl:col-span-2">
        <div className="border-b border-slate-800/80 bg-slate-900/40 px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{icon}</span>
            <div>
              <h3 className="text-sm font-semibold text-white">{title}</h3>
              <p className="text-[11px] text-slate-500">{description}</p>
            </div>
          </div>
        </div>
        <div className="p-4">
          <GraphView />
        </div>
      </section>
    );
  }

  return (
    <section className={`intel-card overflow-hidden ${isChains ? 'xl:col-span-2' : ''}`}>
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
      {items.length === 0 ? (
        <p className="px-5 py-4 text-xs text-slate-500">No data in this section yet.</p>
      ) : isChains ? (
        <div className="space-y-3 p-5">
          {items.map((item) => (
            <EvidenceChainCard key={item.id} item={item} />
          ))}
        </div>
      ) : isPhotoGrid ? (
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
                <p className="truncate text-[10px] text-slate-400">{item.sourcePlatform || item.source || item.label}</p>
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

export function ImageInvestigationPanel() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const uploadedImagePreview = useInvestigationStore((s) => s.uploadedImagePreview);
  const uploadedImageName = useInvestigationStore((s) => s.uploadedImageName);

  const sections = useMemo(() => buildImageInvestigationSections(result, query), [result, query]);
  const brief = useMemo(() => imageInvestigationBrief(result, query), [result, query]);

  if (!result) {
    return (
      <EmptyState
        icon="🖼"
        title="Image Investigation"
        description="Select Image type, upload a file or paste an image URL, then start the investigation."
      />
    );
  }

  const seedLabel = uploadedImageName || query;

  return (
    <div className="space-y-6">
      {uploadedImagePreview && (
        <div className="intel-card flex flex-wrap items-center gap-4 p-4">
          <img
            src={uploadedImagePreview}
            alt={seedLabel}
            className="h-28 w-28 rounded-lg border border-slate-700 object-cover"
          />
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Seed image</p>
            <p className="text-sm font-medium text-white">{seedLabel}</p>
          </div>
        </div>
      )}

      <div className="intel-card bg-gradient-to-br from-violet-950/30 to-cyan-950/20 p-5">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-400/90">Image Investigation</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">{brief.who}</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <BriefRow label="Who might this person be?" value={brief.who} />
          <BriefRow label="Why do we believe that?" value={brief.why} />
          <BriefRow label="What evidence supports it?" value={brief.what} />
          <BriefRow label="Where was the image found?" value={brief.where} />
          <BriefRow label="Which accounts are linked?" value={brief.linked} />
          <BriefRow label="What should be investigated next?" value={brief.next} />
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {sections.map((section) => (
          <SectionCard key={section.id} {...section} />
        ))}
      </div>
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
