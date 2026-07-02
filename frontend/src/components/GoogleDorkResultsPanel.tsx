import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import {
  buildGoogleDorkItems,
  openLinkLabel,
  platformLabel,
  type GoogleDorkItem,
  type PrimaryCollege,
} from '../lib/googleDorkView';
import { resolveMediaUrl } from '../lib/displayFields';
import { externalVisitUrl } from '../lib/socialUrls';
import { Badge } from './ui/Badge';

function CollegeSummaryCard({ college }: { college: PrimaryCollege }) {
  const preview = resolveMediaUrl(college.previewUrl);
  const pageUrl = externalVisitUrl(college.pageUrl);

  return (
    <article className="rounded-xl border border-sky-500/30 bg-gradient-to-r from-sky-950/40 to-slate-900/40 p-4">
      <div className="flex flex-wrap items-start gap-4">
        {preview && (
          <img src={preview} alt={college.name} className="h-20 w-28 rounded-lg border border-slate-700 object-cover" loading="lazy" referrerPolicy="no-referrer" />
        )}
        <div className="min-w-0 flex-1">
          <Badge variant="info">Your college</Badge>
          <h4 className="mt-2 text-base font-semibold text-sky-100">{college.name}</h4>
          <div className="mt-3 flex flex-wrap gap-3">
            {pageUrl && (
              <a href={pageUrl} target="_blank" rel="noreferrer" className="inline-flex rounded-lg bg-sky-600/20 px-3 py-1.5 text-xs font-semibold text-sky-300 hover:bg-sky-600/30">
                Open college page →
              </a>
            )}
            {college.sourceUrl && college.sourceUrl !== college.pageUrl && (
              <a href={externalVisitUrl(college.sourceUrl)} target="_blank" rel="noreferrer" className="inline-flex text-xs text-cyan-400 hover:underline">
                View attributed post →
              </a>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

function DorkCard({ item }: { item: GoogleDorkItem }) {
  const preview = resolveMediaUrl(item.previewUrl);
  const linkLabel = openLinkLabel(item.url);
  const visitUrl = externalVisitUrl(item.url);

  return (
    <article className="min-w-0 rounded-xl border border-slate-800/80 bg-slate-900/40 p-4">
      <div className="flex flex-wrap items-start gap-3">
        {preview && (
          <a
            href={preview}
            target="_blank"
            rel="noreferrer"
            className="block shrink-0 overflow-hidden rounded-lg border border-slate-700"
            title="View screenshot or preview"
          >
            <img
              src={preview}
              alt={item.title}
              className="h-24 w-32 object-cover object-top"
              loading="lazy"
              referrerPolicy="no-referrer"
            />
          </a>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">{item.categoryLabel}</Badge>
            {item.isSocialPost && <Badge variant="muted">{platformLabel(item.platformHost || item.url)}</Badge>}
            {item.platform && !item.isSocialPost && (
              <Badge variant="muted">{platformLabel(item.platform)}</Badge>
            )}
            {item.attributed && <Badge variant="success">attributed</Badge>}
          </div>
          <h4 className="mt-2 text-sm font-semibold text-slate-100">{item.title}</h4>
          {item.snippet && (
            <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-300">{item.snippet}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-3">
            <a
              href={visitUrl || item.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center rounded-lg bg-cyan-600/20 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-600/30"
            >
              {linkLabel}
            </a>
            {preview && (
              <a
                href={preview}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center text-xs text-emerald-400 hover:underline"
              >
                View screenshot
              </a>
            )}
          </div>
          <p className="mt-2 break-all text-[10px] text-slate-500">{item.url}</p>
          {item.dorkQuery && (
            <p className="mt-1 text-[10px] text-slate-600">
              Found via: <span className="text-slate-500">{item.dorkQuery}</span>
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

export function GoogleDorkResultsPanel() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);

  const { all, hackathon, news, college, primaryColleges, social, socialByPlatform } = useMemo(
    () => buildGoogleDorkItems(result, query),
    [result, query],
  );

  if (!all.length) {
    return (
      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/20 p-6 text-center text-sm text-slate-500">
        No Google dork hits yet — run a fresh username investigation to fetch social and hackathon posts.
      </div>
    );
  }

  const socialSections = [...socialByPlatform.entries()].map(([platform, items]) => ({
    title: `${platformLabel(platform)} Posts`,
    icon: '📱',
    items,
  }));

  const sections = [
    ...socialSections,
    { title: 'Hackathon & Wins', icon: '🏆', items: hackathon },
    ...(primaryColleges.length ? [] : [{ title: 'College & School', icon: '🎓', items: college }]),
    { title: 'News & Articles', icon: '📰', items: news },
  ].filter((s) => s.items.length > 0);

  const shown = new Set(sections.flatMap((s) => s.items.map((i) => i.url.toLowerCase())));
  const other = all.filter((i) => !shown.has(i.url.toLowerCase()));
  if (other.length > 0) {
    sections.push({ title: 'Other Discoveries', icon: '🔍', items: other });
  }

  return (
    <section className="space-y-5">
      <header>
        <h3 className="text-sm font-bold uppercase tracking-[0.12em] text-cyan-300">Google Dorking Results</h3>
        <p className="mt-1 text-xs text-slate-400">
          {all.length} result(s) linked to your username or name
          {social.length > 0 ? ` · ${social.length} social post(s) across ${socialByPlatform.size} platform(s)` : ''}
          . Click the buttons to open posts in a new tab.
        </p>
      </header>
      {primaryColleges.length > 0 && (
        <div>
          <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
            <span>🎓</span>
            College & School
            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">{primaryColleges.length}</span>
          </h4>
          <div className="space-y-3">
            {primaryColleges.map((c) => (
              <CollegeSummaryCard key={`${c.name}-${c.pageUrl}`} college={c} />
            ))}
          </div>
        </div>
      )}
      {sections.map((section) => (
        <div key={section.title}>
          <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
            <span>{section.icon}</span>
            {section.title}
            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">{section.items.length}</span>
          </h4>
          <div className="space-y-3">
            {section.items.slice(0, 12).map((item) => (
              <DorkCard key={item.id} item={item} />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
