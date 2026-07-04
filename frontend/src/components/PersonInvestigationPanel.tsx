import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import { buildPersonSections, personInvestigationBrief } from '../lib/personView';
import type { IntelligenceItem } from '../lib/intelligenceView';
import type { PersonSection } from '../lib/personView';
import { isMediaUrl, isProseField, resolveMediaUrl } from '../lib/displayFields';
import { leadVisualsFromResult } from '../lib/leadVisualView';
import { Badge } from './ui/Badge';
import { ConfidenceBar } from './ui/ConfidenceBar';
import { EmptyState } from './ui/EmptyState';
import { CollapsibleSection } from './CollapsibleSection';
import { UnifiedProfilePanel } from './UnifiedProfilePanel';
import { IdentitySummaryHero } from './IdentitySummaryHero';
import { VerifiedPlatformsPanel } from './VerifiedPlatformsPanel';
import { EmailIntelPanel } from './EmailIntelPanel';
import { PhoneIntelPanel } from './PhoneIntelPanel';
import { SamuraiSocialPanel } from './SamuraiSocialPanel';
import { InstagramCommentsPanel } from './InstagramCommentsPanel';
import { LinguisticAnalysisPanel } from './LinguisticAnalysisPanel';
import { VerifiedProfilePhotosPanel } from './VerifiedProfilePhotosPanel';
import { DetectedFacesPanel } from './DetectedFacesPanel';
import { LeadCardsPanel } from './LeadCardsPanel';
import { GoogleDorkResultsPanel } from './GoogleDorkResultsPanel';
import { GraphView } from './GraphView';
import { EvidenceTimeline } from './EvidenceTimeline';
import { ProgressTracker } from './ProgressTracker';
import { InvestigationSummary } from './InvestigationSummary';

function ItemRow({ item }: { item: IntelligenceItem }) {
  const renderAs = item.metadata?.renderAs as string | undefined;
  const imageUrl = resolveMediaUrl((item.metadata?.avatar_url as string | undefined) || item.value);
  const prose = isProseField(item.label) || item.metadata?.renderAs === 'prose';
  const isUrl = !prose && item.value.startsWith('http');

  if (renderAs === 'image' && isMediaUrl(imageUrl)) {
    return (
      <div className="min-w-0 px-5 py-3">
        <div className="flex flex-wrap items-start gap-4">
          <img
            src={imageUrl}
            alt={item.label}
            className="h-24 w-24 rounded-lg border border-slate-700 object-cover bg-slate-900"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{item.label}</p>
            <a href={item.value.startsWith('http') ? item.value : imageUrl} target="_blank" rel="noreferrer" className="mt-1 block break-all text-xs text-cyan-400 hover:underline">
              {item.provenance || item.value}
            </a>
            {item.provenance && item.value !== item.provenance && <p className="mt-1 text-xs text-slate-400">{item.provenance}</p>}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {item.sourcePlatform && <Badge variant="muted">{item.sourcePlatform}</Badge>}
              {item.source && <Badge variant="muted">{item.source}</Badge>}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-w-0 px-5 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{item.label}</p>
          {isUrl ? (
            <a
              href={item.value}
              target="_blank"
              rel="noreferrer"
              className="mt-0.5 block break-all font-mono text-sm text-cyan-300 hover:underline"
            >
              {item.value}
            </a>
          ) : (
            <p className={`mt-0.5 whitespace-pre-wrap break-words text-sm leading-relaxed ${prose ? 'text-slate-100' : 'font-mono text-cyan-100'}`}>
              {item.value}
            </p>
          )}
          {item.provenance && item.provenance !== item.value && (
            <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-slate-400">{item.provenance}</p>
          )}
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

function SectionCard({ title, icon, description, items, id }: PersonSection) {
  const isPhotoGrid = id === 'photos';

  return (
    <section className="intel-card min-w-0 overflow-hidden">
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
              href={item.value.startsWith('http') ? item.value : (item.provenance?.startsWith('http') ? item.provenance : '#')}
              target="_blank"
              rel="noreferrer"
              className="group overflow-hidden rounded-lg border border-slate-800 bg-slate-900/50"
            >
              <img
                src={resolveMediaUrl(item.value) || item.value}
                alt={item.label}
                className="aspect-square w-full object-cover transition group-hover:scale-105 bg-slate-900"
                loading="lazy"
                referrerPolicy="no-referrer"
                onError={(e) => {
                  const el = e.target as HTMLImageElement;
                  el.src = '';
                  el.alt = 'Image unavailable';
                  el.className = 'aspect-square w-full flex items-center justify-center text-[10px] text-slate-500 bg-slate-900';
                }}
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

function BriefRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800/80 bg-slate-900/50 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-sm leading-relaxed text-slate-200">{value}</p>
    </div>
  );
}

export function PersonInvestigationPanel() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const queryType = useInvestigationStore((s) => s.queryType);
  const status = useInvestigationStore((s) => s.status);

  const { person, technical } = useMemo(
    () => buildPersonSections(result, query, queryType),
    [result, query, queryType],
  );
  const brief = useMemo(
    () => personInvestigationBrief(result, query, queryType),
    [result, query, queryType],
  );

  const leads = useMemo(() => leadVisualsFromResult(result, query), [result, query]);

  if (!result && status !== 'running') {
    return (
      <EmptyState
        icon="🕵️"
        title="Person investigation"
        description="Upload an image or enter a username, email, or domain. The platform discovers entities and expands until a person profile is built."
      />
    );
  }

  const personSections = person.filter(
    (s) => s.id !== 'identity'
      && !['google_dorks', 'search_intelligence', 'leads', 'links'].includes(s.id)
      && !(leads.length > 0 && ['events', 'achievements', 'publications', 'photos'].includes(s.id)),
  );

  return (
    <div className="space-y-6">
      <IdentitySummaryHero />

      {result && <UnifiedProfilePanel />}

      {result && <VerifiedProfilePhotosPanel />}

      {result && <VerifiedPlatformsPanel />}

      {result && <SamuraiSocialPanel />}
      {result && <InstagramCommentsPanel />}

      {result && <LinguisticAnalysisPanel />}

      {result && <EmailIntelPanel />}

      {(result || queryType === 'phone' || queryType === 'infra') && <PhoneIntelPanel />}

      {result && (
        <section className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
          <header className="mb-4 border-b border-emerald-500/10 pb-2">
            <h3 className="text-sm font-bold uppercase tracking-[0.12em] text-emerald-300">
              Lead Generation — Visual Intel
            </h3>
            <p className="mt-1 text-xs text-slate-400">
              Hackathon wins, college posts, news — with photos, thumbnails, or page screenshots.
              {result.evidence_extraction?.lead_screenshots_captured
                ? ` · ${result.evidence_extraction.lead_screenshots_captured} page screenshot(s)`
                : ''}
            </p>
          </header>
          <LeadCardsPanel leads={leads} />
        </section>
      )}

      {result && (
        <section className="intel-card min-w-0 overflow-hidden p-4">
          <GoogleDorkResultsPanel />
        </section>
      )}

      {result && queryType === 'image' && <DetectedFacesPanel result={result} />}

      {result && (
        <div className="intel-card bg-gradient-to-br from-slate-900/90 to-cyan-950/20 p-5">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-500/80">Investigation brief</p>
          <h2 className="mt-2 text-xl font-semibold text-white">{brief.who}</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {'what' in brief && <BriefRow label="What was discovered?" value={brief.what} />}
            {'why' in brief && <BriefRow label="Why do we believe it?" value={brief.why} />}
            {'how' in brief && <BriefRow label="How was it discovered?" value={brief.how} />}
            {'where' in brief && <BriefRow label="Where did it appear?" value={brief.where} />}
            {'linked' in brief && <BriefRow label="Linked accounts" value={brief.linked} />}
            {'next' in brief && <BriefRow label="Next expansion" value={brief.next} />}
          </div>
        </div>
      )}

      <div className="grid min-w-0 gap-4 xl:grid-cols-2">
        {personSections.map((section) => (
          <div key={section.id} className="min-w-0">
            <SectionCard {...section} />
          </div>
        ))}
      </div>

      {result && personSections.length === 0 && (
        <EmptyState
          icon="🔍"
          title="Expanding investigation"
          description="Image analysis complete — entity expansion is running. Leads will appear as usernames, emails, and domains are investigated."
        />
      )}

      {result && (
        <section>
          <div className="mb-3">
            <h3 className="text-sm font-semibold text-white">🕸 Intelligence Graph</h3>
            <p className="text-xs text-slate-500">Relationship graph — how discovered entities connect to this person</p>
          </div>
          <GraphView />
        </section>
      )}

      <CollapsibleSection
        title="Technical Analysis"
        subtitle="Face embeddings, hashes, OCR, model outputs, and pipeline internals"
        badge={`${technical.length} sections`}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <ProgressTracker technical />
          <InvestigationSummary />
          <EvidenceTimeline />
          {technical.map((section) => (
            <SectionCard key={section.id} {...section} />
          ))}
        </div>
      </CollapsibleSection>
    </div>
  );
}
