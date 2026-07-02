import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import {
  categoryLabel,
  googleSearchIntelFromResult,
  openLinkLabel,
  placementLabel,
  platformLabel,
  resolveMediaUrl,
  type CollegeDiscovery,
  type GoogleSearchHighlight,
  type HackathonWin,
} from '../lib/googleSearchIntelView';
import { groupByPlatform } from '../lib/platformUtils';
import { Badge } from './ui/Badge';

function PreviewThumb({ url, title, large = false }: { url?: string; title: string; large?: boolean }) {
  const preview = resolveMediaUrl(url);
  const cls = large ? 'h-44 w-64 object-cover object-top' : 'h-28 w-40 object-cover object-top';
  const box = large ? 'h-44 w-64' : 'h-28 w-40';
  if (!preview) {
    return (
      <div className={`flex shrink-0 items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-800/40 text-[10px] text-slate-500 ${box}`}>
        No screenshot yet
      </div>
    );
  }
  return (
    <a href={preview} target="_blank" rel="noreferrer" className="block shrink-0 overflow-hidden rounded-lg border border-slate-700" title="View screenshot">
      <img src={preview} alt={title} className={cls} loading="lazy" referrerPolicy="no-referrer" />
    </a>
  );
}

function HighlightCard({ item, emphasizeScreenshot = false }: { item: GoogleSearchHighlight; emphasizeScreenshot?: boolean }) {
  const linkLabel = openLinkLabel(item.url);
  return (
    <article className="min-w-0 rounded-xl border border-violet-500/20 bg-slate-900/40 p-4">
      <div className="flex flex-wrap items-start gap-3">
        <PreviewThumb url={item.preview_url} title={item.title} large={emphasizeScreenshot} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">{platformLabel(item.platform || item.url)}</Badge>
            {item.trigger_keyword && <Badge variant="muted">via: {item.trigger_keyword}</Badge>}
            {item.serp_phase === 'seed' && <Badge variant="success">Google highlight</Badge>}
          </div>
          <h4 className="mt-2 text-sm font-semibold text-slate-100">{item.title}</h4>
          {item.snippet && <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-300">{item.snippet}</p>}
          <div className="mt-3 flex flex-wrap gap-3">
            <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center rounded-lg bg-violet-600/20 px-3 py-1.5 text-xs font-semibold text-violet-300 hover:bg-violet-600/30">
              {linkLabel}
            </a>
          </div>
          <p className="mt-2 break-all text-[10px] text-slate-500">{item.url}</p>
        </div>
      </div>
    </article>
  );
}

function HackathonCard({ win }: { win: HackathonWin }) {
  return (
    <article className="min-w-0 rounded-xl border border-amber-500/25 bg-amber-500/5 p-4">
      <div className="flex flex-wrap items-start gap-3">
        <PreviewThumb url={win.preview_url} title={win.hackathon} large />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">🏆 {placementLabel(win.placement)}</Badge>
            <Badge variant="muted">{platformLabel(win.platform || win.url)}</Badge>
          </div>
          <h4 className="mt-2 text-base font-semibold text-amber-100">{win.hackathon}</h4>
          <p className="mt-1 text-sm text-slate-200">{win.title}</p>
          {win.snippet && <p className="mt-2 text-xs text-slate-400">{win.snippet}</p>}
          <a href={win.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex rounded-lg bg-amber-600/20 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-600/30">
            {openLinkLabel(win.url)}
          </a>
        </div>
      </div>
    </article>
  );
}

function CollegeCard({ college }: { college: CollegeDiscovery }) {
  return (
    <article className="min-w-0 rounded-xl border border-sky-500/25 bg-sky-500/5 p-4">
      <div className="flex flex-wrap items-start gap-3">
        <PreviewThumb url={college.preview_url} title={college.college} large />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">🎓 College</Badge>
            <Badge variant="muted">{platformLabel(college.platform || college.url)}</Badge>
          </div>
          <h4 className="mt-2 text-base font-semibold text-sky-100">{college.college}</h4>
          {college.page_name && college.page_name !== college.college && (
            <p className="mt-1 text-xs text-sky-300">Page: {college.page_name}</p>
          )}
          <p className="mt-1 text-sm text-slate-300">{college.title}</p>
          {college.snippet && <p className="mt-2 text-xs text-slate-400">{college.snippet}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <a href={college.url} target="_blank" rel="noreferrer" className="inline-flex rounded-lg bg-sky-600/20 px-3 py-1.5 text-xs font-semibold text-sky-300 hover:bg-sky-600/30">
              {openLinkLabel(college.url)}
            </a>
            {college.page_url && college.page_url !== college.url && (
              <a href={college.page_url} target="_blank" rel="noreferrer" className="inline-flex rounded-lg bg-slate-700/40 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700/60">
                College page
              </a>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

export function GoogleSearchIntelPanel() {
  const result = useInvestigationStore((s) => s.result);
  const intel = useMemo(() => googleSearchIntelFromResult(result), [result]);

  const socialPosts = intel?.social_posts ?? [];
  const socialByPlatform = useMemo(
    () => groupByPlatform(socialPosts, (h) => h.platform || h.url),
    [socialPosts],
  );
  const googleHighlights = intel?.google_highlights ?? intel?.highlights.filter((h) => h.serp_phase === 'seed') ?? [];
  const hackathons = intel?.hackathon_wins ?? [];
  const colleges = intel?.colleges ?? [];

  if (!intel) return null;

  return (
    <section className="rounded-xl border border-violet-500/30 bg-gradient-to-br from-violet-950/30 to-slate-900/50 p-5">
      <header className="mb-5 border-b border-violet-500/15 pb-3">
        <h3 className="text-sm font-bold uppercase tracking-[0.14em] text-violet-300">
          Google Dork Intelligence
        </h3>
        <p className="mt-1 text-xs text-slate-400">
          SERP highlights → social post search → college discovery from attributed posts.
          {intel.discovered_keywords.length > 0 ? ` · ${intel.discovered_keywords.length} term(s) discovered` : ''}
        </p>
      </header>

      {intel.discovered_keywords.length > 0 && (
        <div className="mb-6">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Keywords Google highlighted (dynamic — not hardcoded)</p>
          <div className="flex flex-wrap gap-2">
            {intel.discovered_keywords
              .filter((kw) => !['identity', 'social'].includes(kw.category))
              .map((kw) => (
                <span key={`${kw.phrase}-${kw.category}`} className="rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1 text-xs text-violet-200" title={kw.source_snippet || kw.source_url}>
                  {kw.phrase}
                  <span className="ml-1.5 text-[10px] text-violet-400/80">{categoryLabel(kw.category)}</span>
                </span>
              ))}
          </div>
        </div>
      )}

      {googleHighlights.length > 0 && (
        <div className="mb-6">
          <h4 className="mb-3 text-sm font-semibold text-white">🔍 Google highlights</h4>
          <div className="space-y-3">{googleHighlights.slice(0, 6).map((item) => <HighlightCard key={item.url} item={item} />)}</div>
        </div>
      )}

      {hackathons.length > 0 && (
        <div className="mb-6">
          <h4 className="mb-3 text-sm font-semibold text-white">
            🏆 Hackathon wins
            <span className="ml-2 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">{hackathons.length}</span>
          </h4>
          <div className="space-y-3">{hackathons.map((win) => <HackathonCard key={`${win.hackathon}-${win.url}`} win={win} />)}</div>
        </div>
      )}

      {colleges.length > 0 && (
        <div className="mb-6">
          <h4 className="mb-3 text-sm font-semibold text-white">
            🎓 College (from social posts)
            <span className="ml-2 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">{colleges.length}</span>
          </h4>
          <div className="space-y-3">{colleges.map((c) => <CollegeCard key={`${c.college}-${c.url}`} college={c} />)}</div>
        </div>
      )}

      {socialPosts.length > 0 ? (
        <div>
          <h4 className="mb-3 text-sm font-semibold text-white">
            📱 Social posts
            <span className="ml-2 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">{socialPosts.length}</span>
          </h4>
          {[...socialByPlatform.entries()].map(([platform, posts]) => (
            <div key={platform} className="mb-4">
              <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-violet-300/90">
                {platformLabel(platform)} ({posts.length})
              </p>
              <div className="space-y-3">{posts.map((item) => <HighlightCard key={item.url} item={item} emphasizeScreenshot />)}</div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-amber-400/90">
          No social posts matched yet — run a fresh investigation. Posts are searched using your display name on discovered platforms.
        </p>
      )}
    </section>
  );
}
