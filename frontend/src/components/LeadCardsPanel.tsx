import type { LeadVisual } from '../types';
import { externalPageUrl, resolveMediaUrl } from '../lib/mediaUrl';
import { dedupeByUrl } from '../lib/dedupeUrl';
import { leadTypeLabel } from '../lib/leadVisualView';
import { useInvestigationStore } from '../store/investigationStore';
import { buildGoogleDorkItems } from '../lib/googleDorkView';
import { useMemo } from 'react';
import { externalVisitUrl } from '../lib/socialUrls';

function LeadCard({ lead }: { lead: LeadVisual }) {
  const image = resolveMediaUrl(lead.thumbnail_url ?? lead.image_url ?? undefined);
  const typeLabel = leadTypeLabel(lead.lead_type);
  const isScreenshot = lead.visual_source === 'page_screenshot' || Boolean(image?.includes('/api/intel/screenshots/'));
  const pageUrl = externalVisitUrl(lead.url) ?? externalPageUrl(lead.url) ?? lead.url;

  return (
    <article className="overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/50">
      {image ? (
        <a
          href={pageUrl}
          target="_blank"
          rel="noreferrer"
          className="block"
          title={isScreenshot ? 'Open original page' : 'Open page preview'}
        >
          <img
            src={image}
            alt={lead.title}
            className="h-40 w-full object-cover object-top"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
        </a>
      ) : (
        <div className="flex h-32 items-center justify-center bg-slate-800/50 text-4xl text-slate-600">
          {lead.lead_type === 'video' ? '▶' : '📄'}
        </div>
      )}
      <div className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-cyan-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-cyan-300">
            {typeLabel}
          </span>
          {lead.source_domain && (
            <span className="text-[10px] text-slate-500">{lead.source_domain}</span>
          )}
          {lead.visual_source && lead.visual_source !== 'none' && (
            <span className="text-[10px] text-slate-600">{lead.visual_source.replace(/_/g, ' ')}</span>
          )}
        </div>
        <h4 className="mt-2 line-clamp-2 text-sm font-semibold text-slate-100">{lead.title}</h4>
        {lead.snippet && (
          <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-400">{lead.snippet}</p>
        )}
        <a
          href={pageUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-block text-xs text-cyan-400 hover:underline"
        >
          Open original page →
        </a>
        {isScreenshot && image && (
          <a
            href={image}
            target="_blank"
            rel="noreferrer"
            className="ml-3 inline-block text-xs text-emerald-400 hover:underline"
          >
            View screenshot
          </a>
        )}
      </div>
    </article>
  );
}

export function LeadCardsPanel({ leads }: { leads: LeadVisual[] }) {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const { primaryColleges } = useMemo(() => buildGoogleDorkItems(result, query), [result, query]);

  const uniqueLeads = dedupeByUrl(leads, (lead) => lead.url);
  if (!uniqueLeads.length) {
    return (
      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/20 p-6 text-center text-sm text-slate-500">
        No lead visuals yet — run a username investigation with Google dorking enabled.
      </div>
    );
  }

  const hackathons = uniqueLeads.filter((l) => ['hackathon', 'achievement', 'event'].includes(l.lead_type));
  const news = uniqueLeads.filter((l) => ['news', 'article', 'college'].includes(l.lead_type));
  const rest = uniqueLeads.filter((l) => !hackathons.includes(l) && !news.includes(l));

  const sections = [
    ...(primaryColleges.length
      ? [{
          title: 'College & School',
          icon: '🎓',
          colleges: primaryColleges,
          items: [] as LeadVisual[],
        }]
      : []),
    { title: 'Hackathons & Events', icon: '🏆', items: hackathons, colleges: [] as typeof primaryColleges },
    { title: 'News & College', icon: '📰', items: news, colleges: [] as typeof primaryColleges },
    { title: 'Profiles & Media', icon: '👤', items: rest, colleges: [] as typeof primaryColleges },
  ].filter((s) => s.items.length > 0 || (s.colleges?.length ?? 0) > 0);

  return (
    <div className="space-y-6">
      {sections.map((section) => (
        <div key={section.title}>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
            <span>{section.icon}</span>
            {section.title}
            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">
              {section.colleges?.length || section.items.length}
            </span>
          </h3>
          {section.colleges && section.colleges.length > 0 && (
            <div className="mb-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {section.colleges.map((college) => (
                <article key={`${college.name}-${college.pageUrl}`} className="rounded-xl border border-sky-500/30 bg-sky-950/20 p-4">
                  <h4 className="text-base font-semibold text-sky-100">{college.name}</h4>
                  <div className="mt-3 flex flex-wrap gap-3">
                    <a href={externalVisitUrl(college.pageUrl)} target="_blank" rel="noreferrer" className="text-xs text-sky-300 hover:underline">
                      Open college page →
                    </a>
                    {college.sourceUrl && (
                      <a href={externalVisitUrl(college.sourceUrl)} target="_blank" rel="noreferrer" className="text-xs text-cyan-400 hover:underline">
                        View post →
                      </a>
                    )}
                  </div>
                  <p className="mt-2 text-[10px] text-slate-500">Facebook may ask you to log in to view some posts.</p>
                </article>
              ))}
            </div>
          )}
          {section.items.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {section.items.map((lead) => (
                <LeadCard key={`${lead.lead_id}_${lead.url}`} lead={lead} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
