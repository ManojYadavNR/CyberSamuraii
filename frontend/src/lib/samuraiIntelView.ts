import type { InvestigationResult } from '../types';

export interface SamuraiMediaItem {
  url?: string;
  live_url?: string;
  display_url?: string;
  display_live_url?: string;
  thumbnail?: string;
  thumbnail_live_url?: string;
  type?: string;
  caption?: string;
}

export interface SamuraiInstagramPost {
  shortcode?: string;
  url?: string;
  live_url?: string;
  type?: string;
  is_video?: boolean;
  timestamp?: string;
  like_count?: number;
  comment_count?: number;
  caption?: string;
  hashtags?: string[];
  mentions?: string[];
  display_url?: string;
  display_live_url?: string;
  media?: SamuraiMediaItem[];
  video?: {
    view_count?: number;
    duration_seconds?: number;
    video_url?: string;
    video_live_url?: string;
  };
}

export interface SamuraiInstagramProfile {
  scraped_at?: string;
  platform?: string;
  source?: string;
  authenticated?: boolean;
  links?: Record<string, string | null | undefined>;
  profile?: {
    username?: string;
    full_name?: string;
    biography?: string;
    is_verified?: boolean;
    is_private?: boolean;
    follower_count?: number;
    following_count?: number;
    media_count?: number;
    profile_url?: string;
    profile_pic_url?: string;
  };
  stats?: Record<string, number>;
  recent_posts?: SamuraiInstagramPost[];
  reels?: SamuraiInstagramPost[];
  api_response?: Record<string, unknown>;
  notes?: Record<string, string | null | undefined>;
}

export interface SamuraiFacebookItem {
  url?: string;
  live_url?: string;
  type?: string;
  title?: string;
  caption?: string;
  thumbnail?: string;
  thumbnail_live_url?: string;
  is_reel?: boolean;
}

export interface SamuraiFacebookSimilarProfile {
  username?: string;
  full_name?: string;
  profile_url?: string;
  profile_pic_url?: string;
  photo_count?: number;
  source?: string;
  photos?: SamuraiFacebookItem[];
}

export interface SamuraiFacebookProfile {
  scraped_at?: string;
  platform?: string;
  links?: Record<string, string | null | undefined>;
  profile?: {
    username?: string;
    full_name?: string;
    biography?: string;
    profile_url?: string;
    profile_pic_url?: string;
    friend_count?: number;
  };
  personal_details?: Record<string, string>;
  photos?: SamuraiFacebookItem[];
  videos?: SamuraiFacebookItem[];
  reels?: SamuraiFacebookItem[];
  timeline_posts?: SamuraiFacebookItem[];
  similar_profiles?: SamuraiFacebookSimilarProfile[];
}

export interface SamuraiSocialIntel {
  username?: string;
  seed_query?: string;
  display_name?: string;
  facebook_slug?: string;
  facebook_resolution?: string;
  instagram?: SamuraiInstagramProfile | null;
  facebook?: SamuraiFacebookProfile | null;
  cross_platform?: Record<string, unknown> | null;
  instagram_error?: string | null;
  facebook_error?: string | null;
  has_instagram?: boolean;
  has_facebook?: boolean;
}

export function samuraiIntelFromResult(result: InvestigationResult | null): SamuraiSocialIntel | null {
  if (!result) return null;

  const fromEvidence = result.evidence_extraction?.samurai_social_intel as SamuraiSocialIntel | undefined;
  if (fromEvidence && (fromEvidence.instagram || fromEvidence.facebook)) {
    return fromEvidence;
  }

  const tr = result.tool_results?.find((t) => t.tool === 'samurai' && t.success);
  if (!tr?.data?.length) return null;

  for (const row of tr.data) {
    const item = row as Record<string, unknown>;
    if (item.check_type === 'samurai_intel' || item.platform === 'samurai_intel') {
      return {
        username: String(item.username ?? ''),
        seed_query: item.seed_query as string | undefined,
        display_name: item.display_name as string | undefined,
        facebook_slug: item.facebook_slug as string | undefined,
        facebook_resolution: item.facebook_resolution as string | undefined,
        cross_platform: item.cross_platform as Record<string, unknown> | undefined,
        instagram: (item.instagram as SamuraiInstagramProfile) ?? null,
        facebook: (item.facebook as SamuraiFacebookProfile) ?? null,
        instagram_error: item.instagram_error as string | undefined,
        facebook_error: item.facebook_error as string | undefined,
        has_instagram: Boolean(item.instagram),
        has_facebook: Boolean(item.facebook),
      };
    }
  }

  return null;
}

export function pickMediaUrl(...candidates: (string | undefined | null)[]): string | undefined {
  for (const c of candidates) {
    if (c && c.startsWith('http')) return c;
  }
  return undefined;
}

export function postPreviewUrl(post: SamuraiInstagramPost): string | undefined {
  if (post.is_video || post.type === 'Reel' || post.type === 'Video') {
    return pickMediaUrl(
      post.video?.video_live_url,
      post.video?.video_url,
      post.display_live_url,
      post.display_url,
      post.media?.[0]?.live_url,
      post.media?.[0]?.url,
    );
  }
  return pickMediaUrl(
    post.display_live_url,
    post.display_url,
    post.media?.[0]?.live_url,
    post.media?.[0]?.url,
    post.media?.[0]?.display_live_url,
  );
}

export function isVideoUrl(url: string | undefined): boolean {
  if (!url) return false;
  const low = url.toLowerCase();
  if (/\.(mp4|webm|m4v)(\?|$)/i.test(low)) return true;
  if (low.includes('/video/') || low.includes('/reel/')) return true;
  if ((low.includes('fbcdn.net') || low.includes('cdninstagram.com') || low.includes('instagram.'))
    && (low.includes('/v/t') || low.includes('/o1/v/') || low.includes('efg='))) {
    return true;
  }
  return false;
}

export function platformVisitUrl(
  links: Record<string, string | null | undefined> | undefined,
  key: string,
  fallback?: string,
): string | undefined {
  const v = links?.[key];
  if (v && v.startsWith('http')) return v;
  return fallback?.startsWith('http') ? fallback : undefined;
}

export function formatCount(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString();
}

export interface SamuraiComment {
  username?: string;
  text?: string;
  like_count?: number;
  timestamp?: string;
}

export function resolveIgBiography(
  profile: Record<string, unknown>,
  apiResponse?: Record<string, unknown>,
): string {
  const direct = String(profile.biography || '').trim();
  if (direct) return direct;
  const data = apiResponse?.data as Record<string, unknown> | undefined;
  const user = data?.user as Record<string, unknown> | undefined;
  return String(user?.biography || '').trim();
}

export function resolveFbBiography(
  profile: Record<string, unknown>,
  personalDetails?: Record<string, unknown>,
): string {
  const direct = String(profile.biography || '').trim();
  if (direct) return direct;
  const personal = personalDetails || (profile.personal_details as Record<string, unknown> | undefined);
  if (!personal) return '';
  for (const key of ['Overview', 'Bio', 'About', 'bio', 'about']) {
    const val = String(personal[key] || '').trim();
    if (val) return val;
  }
  return '';
}

export function postEngagement(post: Record<string, unknown>) {
  const video = (post.video as Record<string, unknown> | undefined) ?? {};
  return {
    likes: post.like_count as number | undefined,
    views: (video.view_count ?? post.video_view_count) as number | undefined,
    comments: post.comment_count as number | undefined,
    duration: video.duration_seconds as number | undefined,
  };
}

export function mediaEngagement(item: Record<string, unknown>) {
  return {
    likes: (item.like_count ?? item.reactions) as number | undefined,
    views: (item.view_count ?? item.play_count) as number | undefined,
    comments: item.comment_count as number | undefined,
  };
}

export function normalizeComments(raw: unknown): SamuraiComment[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((c) => c && typeof c === 'object')
    .map((c) => {
      const row = c as Record<string, unknown>;
      return {
        username: row.username as string | undefined,
        text: String(row.text || row.message || row.body || '').trim(),
        like_count: row.like_count as number | undefined,
        timestamp: row.timestamp as string | undefined,
      };
    })
    .filter((c) => c.text || c.username);
}

