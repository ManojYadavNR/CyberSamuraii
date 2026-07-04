export interface TimelinePost {
  shortcode?: string;
  post_url?: string;
  type?: string;
  caption?: string;
  published_at?: string;
  published_date?: string;
  weekday?: number;
  weekday_label?: string;
  hour_utc?: number;
  minute_utc?: number;
  likes_count?: number;
  comments_count?: number;
  views_count?: number;
  engagement_score?: number;
}

export interface DayCount {
  day: number;
  label: string;
  count: number;
}

export interface TimelinePoint {
  weekday: number;
  weekday_label: string;
  hour_utc: number;
  shortcode?: string;
  post_url?: string;
  published_at?: string;
  engagement_score?: number;
  likes_count?: number;
}

export interface TimelineAnalytics {
  posts_count: number;
  date_span_days: number;
  posts_per_day: number;
  posts_per_week: number;
  by_week: TimelinePoint[];
  day_counts: DayCount[];
  most_popular?: {
    weekday: number;
    weekday_label: string;
    hour_utc: number;
    label: string;
  } | null;
  calendar_days: Array<{ date: string; count: number }>;
  hour_ticks?: number[];
  weekday_order_sun_first?: string[];
}

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const WEEKDAY_SUN_FIRST = ['Sun', 'Sat', 'Fri', 'Thu', 'Wed', 'Tue', 'Mon'];

function parseDate(value?: string): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function filterTimelinePosts(
  posts: TimelinePost[],
  options?: { selectedDate?: string; fromDate?: string; toDate?: string },
): TimelinePost[] {
  const { selectedDate, fromDate, toDate } = options ?? {};
  return posts.filter((post) => {
    const date = post.published_date || post.published_at?.slice(0, 10);
    if (!date) return false;
    if (selectedDate && date !== selectedDate) return false;
    if (fromDate && date < fromDate) return false;
    if (toDate && date > toDate) return false;
    return true;
  });
}

export function computeTimelineAnalytics(posts: TimelinePost[]): TimelineAnalytics {
  if (!posts.length) {
    return {
      posts_count: 0,
      date_span_days: 0,
      posts_per_day: 0,
      posts_per_week: 0,
      by_week: [],
      day_counts: WEEKDAY_LABELS.map((label, day) => ({ day, label, count: 0 })),
      most_popular: null,
      calendar_days: [],
      hour_ticks: [0, 3, 6, 9, 12, 15, 18, 21, 23],
      weekday_order_sun_first: WEEKDAY_SUN_FIRST,
    };
  }

  const timestamps = posts
    .map((p) => parseDate(p.published_at))
    .filter(Boolean) as Date[];
  const spanDays = timestamps.length > 1
    ? Math.max(1, Math.ceil((Math.max(...timestamps.map((t) => t.getTime())) - Math.min(...timestamps.map((t) => t.getTime()))) / 86400000) + 1)
    : 1;
  const count = posts.length;
  const postsPerDay = Math.round((count / spanDays) * 100) / 100;
  const postsPerWeek = Math.round((count / Math.max(spanDays / 7, 1)) * 100) / 100;

  const dayCounts = Array.from({ length: 7 }, () => 0);
  const hourByDay = new Map<string, number>();
  const calendarMap = new Map<string, number>();
  const byWeek: TimelinePoint[] = [];

  for (const post of posts) {
    const weekday = post.weekday ?? 0;
    const hour = post.hour_utc ?? 0;
    dayCounts[weekday] += 1;
    hourByDay.set(`${weekday}:${hour}`, (hourByDay.get(`${weekday}:${hour}`) ?? 0) + 1);
    const dateKey = post.published_date || post.published_at?.slice(0, 10);
    if (dateKey) calendarMap.set(dateKey, (calendarMap.get(dateKey) ?? 0) + 1);
    byWeek.push({
      weekday,
      weekday_label: post.weekday_label || WEEKDAY_LABELS[weekday],
      hour_utc: hour,
      shortcode: post.shortcode,
      post_url: post.post_url,
      published_at: post.published_at,
      engagement_score: post.engagement_score,
      likes_count: post.likes_count,
    });
  }

  const bestDay = dayCounts.indexOf(Math.max(...dayCounts));
  let bestHour = 0;
  if (dayCounts[bestDay] > 0) {
    bestHour = Array.from({ length: 24 }, (_, h) => h).reduce((best, h) => (
      (hourByDay.get(`${bestDay}:${h}`) ?? 0) > (hourByDay.get(`${bestDay}:${best}`) ?? 0) ? h : best
    ), 0);
  }

  return {
    posts_count: count,
    date_span_days: spanDays,
    posts_per_day: postsPerDay,
    posts_per_week: postsPerWeek,
    by_week: byWeek,
    day_counts: WEEKDAY_LABELS.map((label, day) => ({ day, label, count: dayCounts[day] })),
    most_popular: {
      weekday: bestDay,
      weekday_label: WEEKDAY_LABELS[bestDay],
      hour_utc: bestHour,
      label: `${WEEKDAY_LABELS[bestDay]} | ${String(bestHour).padStart(2, '0')}:00`,
    },
    calendar_days: [...calendarMap.entries()]
      .map(([date, c]) => ({ date, count: c }))
      .sort((a, b) => a.date.localeCompare(b.date)),
    hour_ticks: [0, 3, 6, 9, 12, 15, 18, 21, 23],
    weekday_order_sun_first: WEEKDAY_SUN_FIRST,
  };
}

/** Map Python/JS weekday Mon=0..Sun=6 to Sun-first chart row 0..6. */
export function weekdayToSunFirstRow(weekday: number): number {
  return (7 - ((weekday + 1) % 7)) % 7;
}
