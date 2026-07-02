import { useInvestigationStore } from '../store/investigationStore';
import { buildOsintIntelSections, type OsintIntelItem } from '../lib/osintIntelView';
import { leadVisualsFromResult } from '../lib/leadVisualView';
import { resolveMediaUrl } from '../lib/displayFields';
import { LeadCardsPanel } from './LeadCardsPanel';

function IntelCard({ item }: { item: OsintIntelItem }) {
  const thumb = item.thumbnailUrl || item.imageUrl;
  const pageUrl = item.url && item.url.startsWith('http') ? item.url : undefined;

  if (item.renderAs === 'image' && item.imageUrl) {
    const imgSrc = resolveMediaUrl(item.imageUrl) || item.imageUrl;
    return (
      <div className="rounded-lg border border-slate-800/80 bg-slate-900/40 p-3">
        <div className="flex gap-3">
          <a href={pageUrl || imgSrc} target="_blank" rel="noreferrer" className="shrink-0">
            <img
              src={imgSrc}
              alt={item.label}
              className="h-20 w-20 rounded-lg border border-slate-700 object-cover"
              loading="lazy"
              referrerPolicy="no-referrer"
            />
          </a>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-cyan-400/90">{item.label}</div>
            <p className="mt-1 line-clamp-2 text-sm text-slate-100">{item.value}</p>
            {item.provenance && <p className="mt-1 line-clamp-2 text-xs text-slate-400">{item.provenance}</p>}
            {pageUrl && pageUrl !== item.imageUrl && (
              <a href={pageUrl} target="_blank" rel="noreferrer" className="mt-1 block truncate text-xs text-cyan-400 hover:underline">
                {item.sourcePlatform || domainLabel(pageUrl)}
              </a>
            )}
            <MetaRow item={item} />
          </div>
        </div>
      </div>
    );
  }

  if (item.renderAs === 'video') {
    return (
      <div className="rounded-lg border border-slate-800/80 bg-slate-900/40 p-3">
        <div className="flex gap-3">
          {thumb && (
            <a href={pageUrl || item.value} target="_blank" rel="noreferrer" className="relative shrink-0">
              <img
                src={thumb}
                alt={item.label}
                className="h-20 w-32 rounded-lg border border-slate-700 object-cover"
                loading="lazy"
                referrerPolicy="no-referrer"
              />
              <span className="absolute inset-0 flex items-center justify-center text-2xl text-white/90">▶</span>
            </a>
          )}
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-cyan-400/90">{item.label}</div>
            <a href={pageUrl || item.value} target="_blank" rel="noreferrer" className="mt-1 block break-all text-sm text-slate-100 hover:text-cyan-300">
              {item.value}
            </a>
            {item.provenance && <p className="mt-1 text-xs text-slate-400">{item.provenance}</p>}
            <MetaRow item={item} />
          </div>
        </div>
      </div>
    );
  }

  if (item.renderAs === 'account') {
    return (
      <div className="rounded-lg border border-slate-800/80 bg-slate-900/40 p-3">
        <div className="flex gap-3">
          {item.imageUrl ? (
            <img
              src={item.imageUrl}
              alt={item.label}
              className="h-14 w-14 shrink-0 rounded-full border border-slate-700 object-cover"
              loading="lazy"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-slate-800 text-lg text-slate-400">
              {(item.sourcePlatform || item.label).charAt(0).toUpperCase()}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-100">{item.label}</span>
              {item.sourcePlatform && (
                <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">{item.sourcePlatform}</span>
              )}
            </div>
            {item.provenance && <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-slate-400">{item.provenance}</p>}
            {pageUrl && (
              <a href={pageUrl} target="_blank" rel="noreferrer" className="mt-1 block truncate text-xs text-cyan-400 hover:underline">
                {pageUrl}
              </a>
            )}
            <MetaRow item={item} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800/80 bg-slate-900/40 p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-cyan-400/90">{item.label}</div>
      {pageUrl ? (
        <a href={pageUrl} target="_blank" rel="noreferrer" className="mt-1 block break-all text-sm text-slate-100 hover:text-cyan-300">
          {item.value}
        </a>
      ) : (
        <div className="mt-1 break-words text-sm text-slate-100">{item.value}</div>
      )}
      {item.provenance && <p className="mt-1 line-clamp-3 text-xs text-slate-400">{item.provenance}</p>}
      <MetaRow item={item} />
    </div>
  );
}

function MetaRow({ item }: { item: OsintIntelItem }) {
  return (
    <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-500">
      {item.confidence != null && item.confidence <= 1 && <span>{Math.round(item.confidence * 100)}% conf.</span>}
      {item.source && <span>{item.source}</span>}
    </div>
  );
}

function domainLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export function OsintFrameworkPage() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const status = useInvestigationStore((s) => s.status);
  const identity = result?.identity_profile;
  const sections = buildOsintIntelSections(result, identity, query);
  const leads = leadVisualsFromResult(result, query);

  if (!result && status === 'idle') {
    return (
      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/20 p-8 text-center text-slate-400">
        Run an investigation to populate the OSINT Framework intelligence view.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3">
        <h2 className="text-sm font-bold uppercase tracking-[0.12em] text-cyan-300">OSINT Framework View</h2>
        <p className="mt-1 text-xs text-slate-400">
          Registry-routed collection for <span className="text-slate-200">{query || '—'}</span> — photos, bios, events, and articles with source links.
        </p>
        {identity?.primary_bio && (
          <p className="mt-2 text-sm text-slate-300">
            <span className="text-slate-500">Bio: </span>{identity.primary_bio}
          </p>
        )}
      </div>

      <section className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
        <header className="mb-4 border-b border-emerald-500/10 pb-2">
          <h3 className="text-sm font-bold uppercase tracking-[0.12em] text-emerald-300">
            Lead Generation — Visual Intel
          </h3>
          <p className="mt-1 text-xs text-slate-400">
            Hackathon wins, college posts, news articles — with photos, thumbnails, or page screenshots.
            {result?.evidence_extraction?.lead_screenshots_captured
              ? ` · ${result.evidence_extraction.lead_screenshots_captured} page screenshot(s) captured`
              : ''}
          </p>
        </header>
        <LeadCardsPanel leads={leads} />
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        {sections.map((section) => (
          <section key={section.id} className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-4">
            <header className="mb-3 flex items-center justify-between border-b border-slate-800/60 pb-2">
              <div>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                  <span>{section.icon}</span>
                  {section.title}
                </h3>
                {section.description && <p className="mt-0.5 text-[10px] text-slate-500">{section.description}</p>}
              </div>
              <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-400">
                {section.items.length}
              </span>
            </header>
            {section.items.length === 0 ? (
              <p className="text-xs text-slate-600">No findings in this category yet.</p>
            ) : (
              <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                {section.items.map((item) => (
                  <IntelCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
