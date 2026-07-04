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
  similar_profiles?: SamuraiFacebookSimilarProfile[];
  scrape_limited?: boolean;
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
  embed_only?: boolean;
  links?: Record<string, string | null | undefined>;
  profile?: {
    username?: string;
    full_name?: string;
    biography?: string;
    profile_url?: string;
    profile_pic_url?: string;
    profile_pic?: string;
    friend_count?: number;
    personal_details?: Record<string, string>;
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

function _facebookRichness(fb: SamuraiFacebookProfile | Record<string, unknown> | null | undefined): number {
  if (!fb || typeof fb !== 'object') return 0;
  const row = fb as Record<string, unknown>;
  const profile = (row.profile as Record<string, unknown> | undefined) ?? {};
  const personal = {
    ...((profile.personal_details as Record<string, unknown> | undefined) ?? {}),
    ...((row.personal_details as Record<string, unknown> | undefined) ?? {}),
  };
  let score = 1;
  if (!row.embed_only) score += 20;
  score += Array.isArray(row.photos) ? row.photos.length : 0;
  score += Array.isArray(row.similar_profiles) ? row.similar_profiles.length * 2 : 0;
  score += Object.keys(personal).length * 3;
  if (profile.full_name && isCleanFbDisplayName(String(profile.full_name))) score += 5;
  if (profile.profile_pic_url) score += 2;
  return score;
}

function _preferRicherFacebook(
  a: SamuraiFacebookProfile | null | undefined,
  b: SamuraiFacebookProfile | null | undefined,
): SamuraiFacebookProfile | null {
  if (_facebookRichness(a) >= _facebookRichness(b)) return a ?? b ?? null;
  return b ?? a ?? null;
}

/** Reject mojibake / garbage names pulled from Instagram into Facebook stubs. */
export function isCleanFbDisplayName(name: string): boolean {
  const n = name.trim();
  if (!n) return false;
  if (/[¶×°]/.test(n) || /[\u0000-\u001f]/.test(n)) return false;
  const low = n.toLowerCase();
  if (low === 'facebook' || low.startsWith('link to facebook') || low === 'log in to facebook') return false;
  const letters = n.replace(/[^a-zA-Z\u00C0-\u024F]/g, '');
  return letters.length >= 2;
}

export function cleanFbDisplayName(name: string | undefined | null, slug: string): string {
  const n = String(name || '').trim();
  if (n && isCleanFbDisplayName(n) && n.toLowerCase() !== slug.toLowerCase()) return n;
  // Title-case slug segments: manoj.yadav27 → Manoj Yadav
  const fromSlug = slug
    .replace(/[._-]+/g, ' ')
    .replace(/\d+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
  return fromSlug || slug;
}

export function samuraiIntelFromResult(result: InvestigationResult | null): SamuraiSocialIntel | null {
  if (!result) return null;

  const fromTool = _samuraiIntelFromToolResults(result);
  const fromEvidence = result.evidence_extraction?.samurai_social_intel as SamuraiSocialIntel | undefined;

  if (fromEvidence && (fromEvidence.instagram || fromEvidence.facebook || fromEvidence.facebook_slug)) {
    const facebook = _preferRicherFacebook(
      fromEvidence.facebook as SamuraiFacebookProfile | null | undefined,
      fromTool?.facebook as SamuraiFacebookProfile | null | undefined,
    );
    const facebookSlug = fromEvidence.facebook_slug
      ?? fromTool?.facebook_slug
      ?? (facebook?.profile as { username?: string } | undefined)?.username;
    return {
      ...fromEvidence,
      instagram: fromEvidence.instagram ?? fromTool?.instagram ?? null,
      facebook,
      facebook_slug: facebookSlug,
      facebook_resolution: fromEvidence.facebook_resolution ?? fromTool?.facebook_resolution,
      facebook_error: fromEvidence.facebook_error ?? fromTool?.facebook_error,
      instagram_error: fromEvidence.instagram_error ?? fromTool?.instagram_error,
      cross_platform: fromEvidence.cross_platform ?? fromTool?.cross_platform,
      username: fromEvidence.username ?? fromTool?.username,
      seed_query: fromEvidence.seed_query ?? fromTool?.seed_query,
      has_instagram: Boolean(fromEvidence.instagram ?? fromTool?.instagram),
      has_facebook: Boolean(facebook || facebookSlug),
    };
  }

  return fromTool;
}

function _samuraiIntelFromToolResults(result: InvestigationResult): SamuraiSocialIntel | null {
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
    post.media?.[0]?.display_url,
    post.media?.[0]?.thumbnail,
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

/** Stable key for deduplicating Samurai media rows (media_id, lookaside URL, or CDN path). */
export function samuraiMediaKey(item: Record<string, unknown>): string {
  const mediaId = item.media_id;
  if (mediaId != null && String(mediaId).trim()) {
    return `mid:${String(mediaId).trim()}`;
  }
  const url = pickMediaUrl(
    item.url as string,
    item.live_url as string,
    item.thumbnail as string,
    item.display_url as string,
  );
  if (url) {
    const match = url.match(/media_id=(\d+)/i);
    if (match) return `mid:${match[1]}`;
    return `url:${url.split('?')[0]}`;
  }
  return `misc:${String(item.type || 'item')}:${String(item.owner_username || '')}`;
}

export function dedupeSamuraiMedia(items: Record<string, unknown>[]): Record<string, unknown>[] {
  const seen = new Set<string>();
  const out: Record<string, unknown>[] = [];
  for (const item of items) {
    const key = samuraiMediaKey(item);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

export function facebookItemVisitUrl(
  item: Record<string, unknown>,
  profileFallback?: string,
): string | undefined {
  const profile = pickMediaUrl(
    item.profile_url as string,
    profileFallback,
  );
  // Real photo.php links for this profile's album posts.
  const pageUrl = pickMediaUrl(item.page_url as string);
  if (pageUrl && pageUrl.includes('facebook.com/photo')) return pageUrl;

  const album = pickMediaUrl(item.album_url as string);
  if (album) return album;

  const direct = pickMediaUrl(
    item.live_url as string,
    item.url as string,
    item.preview_url as string,
    item.thumbnail as string,
  );
  // Direct CDN / lookaside URLs open the image itself in-browser (via media-proxy).
  if (direct && (direct.includes('fbcdn.net') || direct.includes('lookaside.fbsbx.com'))) {
    return direct;
  }
  if (direct && (direct.includes('facebook.com') || direct.includes('fb.com'))) {
    return direct;
  }
  if (profile) {
    const base = profile.replace(/\/?$/, '');
    return `${base}/photos`;
  }
  return profile;
}

/** True when we can show a photo card (direct CDN, lookaside, or media_id link). */
export function isDisplayableSamuraiMedia(item: Record<string, unknown>): boolean {
  if (item.verified === true) return true;
  if (item.media_id != null && String(item.media_id).trim()) return true;
  const url = pickMediaUrl(
    item.preview_url as string,
    item.thumbnail as string,
    item.display_url as string,
    item.url as string,
    item.live_url as string,
  );
  return Boolean(url);
}

