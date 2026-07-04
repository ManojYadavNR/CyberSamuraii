import { useEffect, useMemo, useState } from 'react';
import { fetchInstagramTimeline, type InstagramTimelineResponse } from '../api/samurai';
import {
  computeTimelineAnalytics,
  filterTimelinePosts,
  weekdayToSunFirstRow,
  type TimelinePost,
} from '../lib/instagramTimeline';

const WEEKDAY_SUN_FIRST = ['Sun', 'Sat', 'Fri', 'Thu', 'Wed', 'Tue', 'Mon'];
const HOUR_TICKS = [0, 3, 6, 9, 12, 15, 18, 21, 23];

function formatCount(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function MonthCalendar({
  days,
  selectedDate,
  onSelect,
}: {
  days: Array<{ date: string; count: number }>;
  selectedDate?: string;
  onSelect: (date: string | undefined) => void;
}) {
  const countByDate = useMemo(() => new Map(days.map((d) => [d.date, d.count])), [days]);
  const latestDate = days[days.length - 1]?.date;
  const defaultViewYm = latestDate?.slice(0, 7) || new Date().toISOString().slice(0, 7);
  const [viewYm, setViewYm] = useState(defaultViewYm);

  const monthsWithPosts = useMemo(() => {
    const seen = new Set<string>();
    for (const day of days) seen.add(day.date.slice(0, 7));
    return [...seen].sort();
  }, [days]);

  useEffect(() => {
    if (selectedDate) {
      setViewYm(selectedDate.slice(0, 7));
      return;
    }
    if (latestDate) setViewYm(latestDate.slice(0, 7));
  }, [latestDate, selectedDate, days.length]);

  const [year, month] = viewYm.split('-').map(Number);
  const first = new Date(Date.UTC(year, month - 1, 1));
  const startPad = first.getUTCDay();
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const cells: Array<{ date?: string; count?: number }> = [];
  for (let i = 0; i < startPad; i += 1) cells.push({});
  for (let d = 1; d <= daysInMonth; d += 1) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push({ date, count: countByDate.get(date) });
  }

  const postsThisMonth = days.filter((d) => d.date.startsWith(viewYm)).reduce((sum, d) => sum + d.count, 0);

  const shiftMonth = (delta: number) => {
    const next = new Date(Date.UTC(year, month - 1 + delta, 1));
    setViewYm(`${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, '0')}`);
  };

  const formatMonthLabel = (ym: string) => {
    const [y, m] = ym.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, 1)).toLocaleString(undefined, {
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    });
  };

  return (
    <div className="rounded-xl border border-slate-800/80 bg-slate-950/50 p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => shiftMonth(-1)}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-700 bg-slate-900/80 text-slate-300 hover:border-violet-500/40 hover:bg-violet-500/10"
            aria-label="Previous month"
          >
            ‹
          </button>
          <p className="min-w-[7.5rem] text-center text-xs font-semibold text-slate-200">
            {first.toLocaleString(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' })}
          </p>
          <button
            type="button"
            onClick={() => shiftMonth(1)}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-700 bg-slate-900/80 text-slate-300 hover:border-violet-500/40 hover:bg-violet-500/10"
            aria-label="Next month"
          >
            ›
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {selectedDate && (
            <button
              type="button"
              onClick={() => onSelect(undefined)}
              className="rounded-md border border-slate-700 px-2 py-0.5 text-[10px] text-cyan-300 hover:bg-slate-800"
            >
              Clear
            </button>
          )}
          {latestDate && viewYm !== latestDate.slice(0, 7) && (
            <button
              type="button"
              onClick={() => setViewYm(latestDate.slice(0, 7))}
              className="rounded-md border border-violet-500/30 px-2 py-0.5 text-[10px] text-violet-200 hover:bg-violet-500/10"
            >
              Latest
            </button>
          )}
        </div>
      </div>

      {monthsWithPosts.length > 1 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {monthsWithPosts.map((ym) => {
            const count = days.filter((d) => d.date.startsWith(ym)).reduce((sum, d) => sum + d.count, 0);
            const active = ym === viewYm;
            return (
              <button
                key={ym}
                type="button"
                onClick={() => setViewYm(ym)}
                className={`rounded-full px-2 py-0.5 text-[10px] transition ${
                  active
                    ? 'bg-violet-500/25 font-semibold text-violet-100 ring-1 ring-violet-400/40'
                    : 'border border-slate-700/80 bg-slate-900/60 text-slate-400 hover:border-violet-500/30 hover:text-violet-200'
                }`}
              >
                {formatMonthLabel(ym)} · {count}
              </button>
            );
          })}
        </div>
      )}

      <div className="grid grid-cols-7 gap-1 text-center text-[10px] text-slate-500">
        {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((label, idx) => (
          <span key={`${label}-${idx}`} className="py-1 font-medium">{label}</span>
        ))}
        {cells.map((cell, idx) => {
          if (!cell.date) return <span key={`pad-${idx}`} />;
          const active = cell.date === selectedDate;
          const postCount = cell.count ?? 0;
          const hasPosts = postCount > 0;
          return (
            <button
              key={cell.date}
              type="button"
              onClick={() => onSelect(active ? undefined : cell.date)}
              disabled={!hasPosts}
              className={`relative flex min-h-[2rem] flex-col items-center justify-center rounded-md py-1 text-[11px] transition ${
                active
                  ? 'bg-cyan-500/25 font-semibold text-cyan-100 ring-1 ring-cyan-400/50'
                  : hasPosts
                    ? 'bg-pink-500/15 text-pink-100 hover:bg-pink-500/25'
                    : 'cursor-default text-slate-600'
              }`}
              title={hasPosts ? `${postCount} post${postCount === 1 ? '' : 's'} · click to filter` : 'No posts this day'}
            >
              <span>{Number(cell.date.slice(-2))}</span>
              {hasPosts && postCount > 1 && (
                <span className="mt-0.5 text-[9px] leading-none text-pink-300/90">{postCount}</span>
              )}
              {hasPosts && postCount === 1 && (
                <span className="absolute bottom-0.5 h-1 w-1 rounded-full bg-pink-400" />
              )}
            </button>
          );
        })}
      </div>

      <p className="mt-2 text-[10px] text-slate-500">
        {postsThisMonth > 0
          ? `${postsThisMonth} post${postsThisMonth === 1 ? '' : 's'} in this month · click a highlighted day to filter charts`
          : 'No posts in this month — use ‹ › or the month pills above to browse'}
      </p>
    </div>
  );
}

function WeekScatterChart({
  points,
  mode,
}: {
  points: TimelinePost[];
  mode: 'posts' | 'engagement';
}) {
  const maxEngagement = useMemo(
    () => Math.max(1, ...points.map((p) => p.engagement_score ?? p.likes_count ?? 1)),
    [points],
  );

  return (
    <div className="relative min-h-[220px] rounded-xl border border-slate-800/80 bg-slate-950/40 p-3">
      <div className="grid grid-cols-[2.5rem_1fr] gap-2">
        <div className="flex flex-col justify-between py-1 text-[10px] text-slate-500">
          {WEEKDAY_SUN_FIRST.map((label) => (
            <span key={label} className="leading-none">{label}</span>
          ))}
        </div>
        <div className="relative">
          <div className="absolute inset-0 grid grid-rows-7">
            {WEEKDAY_SUN_FIRST.map((label) => (
              <div key={label} className="border-b border-dashed border-slate-800/70 last:border-b-0" />
            ))}
          </div>
          <div className="relative h-[210px]">
            {points.map((point, idx) => {
              const sunFirstRow = weekdayToSunFirstRow(point.weekday ?? 0);
              const hour = point.hour_utc ?? 0;
              const xPct = Math.min(98, Math.max(2, (hour / 23) * 100));
              const yPct = ((sunFirstRow + 0.5) / 7) * 100;
              const score = point.engagement_score ?? point.likes_count ?? 1;
              const size = mode === 'engagement'
                ? 8 + (score / maxEngagement) * 14
                : 10;
              return (
                <a
                  key={`${point.shortcode}_${idx}`}
                  href={point.post_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="absolute rounded-full bg-cyan-400/80 shadow-sm ring-2 ring-cyan-300/30 transition hover:bg-cyan-300"
                  style={{
                    left: `${xPct}%`,
                    top: `${yPct}%`,
                    width: size,
                    height: size,
                    transform: 'translate(-50%, -50%)',
                  }}
                  title={`${point.weekday_label} ${String(hour).padStart(2, '0')}:00 UTC`}
                />
              );
            })}
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-slate-500">
            {HOUR_TICKS.map((h) => (
              <span key={h}>{String(h).padStart(2, '0')}:00</span>
            ))}
          </div>
        </div>
      </div>
      <p className="mt-2 text-[10px] text-slate-500">Time is shown in UTC time zone</p>
    </div>
  );
}

function DayBarChart({ dayCounts }: { dayCounts: Array<{ label: string; count: number }> }) {
  const max = Math.max(1, ...dayCounts.map((d) => d.count));
  return (
    <div className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-4">
      <p className="text-xs font-semibold text-slate-300">Most popular post time</p>
      <div className="mt-4 flex h-28 items-end justify-between gap-1">
        {dayCounts.map((day) => (
          <div key={day.label} className="flex flex-1 flex-col items-center gap-1">
            <div
              className="w-full max-w-[2rem] rounded-t-md bg-gradient-to-t from-cyan-600/60 to-cyan-400/70"
              style={{ height: `${Math.max(8, (day.count / max) * 100)}%` }}
            />
            <span className="text-[10px] text-slate-500">{day.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function InstagramTimelinePanel({ profileUsername }: { profileUsername: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<InstagramTimelineResponse | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [chartMode, setChartMode] = useState<'posts' | 'engagement'>('posts');
  const [selectedDate, setSelectedDate] = useState<string | undefined>();

  const allPosts = data?.posts ?? [];
  const filteredPosts = useMemo(
    () => filterTimelinePosts(allPosts, { selectedDate }),
    [allPosts, selectedDate],
  );
  const analytics = useMemo(
    () => computeTimelineAnalytics(filteredPosts),
    [filteredPosts],
  );

  const loadTimeline = async () => {
    if (!profileUsername || loading) return;
    setLoading(true);
    setError(null);
    setPanelOpen(true);
    try {
      const res = await fetchInstagramTimeline(profileUsername, { resultsLimit: 20 });
      setData(res);
      setSelectedDate(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load publishing timeline');
    } finally {
      setLoading(false);
    }
  };

  const summary = data
    ? `${formatCount(analytics.posts_count)} posts${selectedDate ? ` on ${selectedDate}` : ''}`
    : `@${profileUsername} · up to 20 recent posts`;

  return (
    <div className="overflow-hidden rounded-2xl border border-violet-500/20 bg-gradient-to-b from-violet-950/20 via-slate-950/40 to-slate-950/20">
      <div className="flex flex-wrap items-center gap-3 border-b border-violet-500/15 bg-violet-950/20 px-4 py-3">
        <button
          type="button"
          onClick={() => setPanelOpen((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          aria-expanded={panelOpen}
        >
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border text-sm ${
            panelOpen ? 'border-violet-400/40 bg-violet-500/15 text-violet-200' : 'border-slate-700 bg-slate-900/80 text-slate-400'
          }`}
          >
            {panelOpen ? '▾' : '▸'}
          </span>
          <div className="min-w-0">
            <h4 className="text-sm font-bold text-white">Publishing timeline</h4>
            <p className="mt-0.5 truncate text-[11px] text-slate-400">{summary}</p>
          </div>
        </button>
        <button
          type="button"
          onClick={loadTimeline}
          disabled={loading}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-violet-400/30 bg-violet-500/15 px-3 py-2 text-xs font-semibold text-violet-100 hover:bg-violet-500/25 disabled:opacity-50"
        >
          {loading ? 'Loading…' : data ? 'Refresh' : 'Load timeline'}
        </button>
      </div>

      {panelOpen && (
        <div className="space-y-4 p-4">
          {error && (
            <p className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">{error}</p>
          )}

          {!data && !loading && !error && (
            <p className="rounded-xl border border-dashed border-slate-700/80 bg-slate-950/30 px-4 py-6 text-center text-sm text-slate-400">
              Click <span className="font-semibold text-violet-300">Load timeline</span> to fetch post timestamps and publishing patterns.
            </p>
          )}

          {loading && (
            <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-800/60 bg-slate-950/40 px-4 py-8 text-sm text-slate-400">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-violet-400/30 border-t-violet-400" />
              Loading publishing data…
            </div>
          )}

          {data && !loading && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-slate-800/80 bg-slate-950/50 px-4 py-3">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Publishing frequency</p>
                  <div className="mt-3 grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-2xl font-semibold tabular-nums text-white">{formatCount(analytics.posts_per_day)}</p>
                      <p className="text-xs text-slate-400">Posts per day</p>
                    </div>
                    <div>
                      <p className="text-2xl font-semibold tabular-nums text-white">{formatCount(analytics.posts_per_week)}</p>
                      <p className="text-xs text-slate-400">Posts per week</p>
                    </div>
                  </div>
                  <p className="mt-2 text-[10px] text-slate-500">
                    From {analytics.posts_count} post{analytics.posts_count === 1 ? '' : 's'}
                    {analytics.date_span_days > 0 ? ` across ${analytics.date_span_days} day${analytics.date_span_days === 1 ? '' : 's'}` : ''}
                  </p>
                </div>
                <MonthCalendar
                  days={computeTimelineAnalytics(allPosts).calendar_days}
                  selectedDate={selectedDate}
                  onSelect={setSelectedDate}
                />
              </div>

              <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
                <div>
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-xs font-semibold text-slate-200">By week</p>
                      <p className="text-[11px] text-slate-500">
                        {selectedDate ? `Posts on ${selectedDate}` : `From the last ${analytics.posts_count} posts`}
                      </p>
                    </div>
                    <div className="flex rounded-lg border border-slate-700 bg-slate-900/60 p-0.5 text-[11px]">
                      <button
                        type="button"
                        onClick={() => setChartMode('posts')}
                        className={`rounded-md px-2.5 py-1 ${chartMode === 'posts' ? 'bg-violet-500/20 text-violet-100' : 'text-slate-400'}`}
                      >
                        Posts
                      </button>
                      <button
                        type="button"
                        onClick={() => setChartMode('engagement')}
                        className={`rounded-md px-2.5 py-1 ${chartMode === 'engagement' ? 'bg-violet-500/20 text-violet-100' : 'text-slate-400'}`}
                      >
                        Engagement
                      </button>
                    </div>
                  </div>
                  <WeekScatterChart points={filteredPosts} mode={chartMode} />
                </div>
                <div className="space-y-3">
                  {analytics.most_popular && (
                    <div className="rounded-xl border border-slate-800/80 bg-slate-950/40 px-4 py-3 text-center">
                      <p className="text-[10px] uppercase tracking-wider text-slate-500">Peak slot</p>
                      <p className="mt-1 text-lg font-bold text-white">{analytics.most_popular.label}</p>
                    </div>
                  )}
                  <DayBarChart dayCounts={analytics.day_counts} />
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
