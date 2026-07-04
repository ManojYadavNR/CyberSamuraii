import { apiFetch } from './client';

export interface SamuraiApifyComment {
  id?: string;
  username?: string;
  text?: string;
  like_count?: number;
  timestamp?: string;
  profile_url?: string;
  comment_url?: string;
  replies_count?: number;
  replies?: SamuraiApifyComment[];
}

export interface InstagramCommentsResponse {
  success: boolean;
  post_url?: string;
  results_limit?: number;
  count?: number;
  comments: SamuraiApifyComment[];
  error?: string;
}

export async function fetchApifyInstagramComments(
  url: string,
  options?: { resultsLimit?: number; includeReplies?: boolean },
): Promise<InstagramCommentsResponse> {
  return apiFetch('/api/samurai/instagram-comments', {
    method: 'POST',
    body: JSON.stringify({
      url,
      results_limit: options?.resultsLimit ?? 15,
      include_replies: options?.includeReplies ?? true,
    }),
  });
}

export async function fetchApifyCommentsStatus(): Promise<{ configured: boolean }> {
  return apiFetch('/api/samurai/instagram-comments/status');
}

export interface CommentOnPost {
  text?: string;
  timestamp?: string;
  like_count?: number;
  comment_url?: string;
  is_reply?: boolean;
}

export interface CommenterPostGroup {
  post_url: string;
  shortcode?: string;
  post_type?: string;
  post_owner_username?: string;
  total_comments_on_post?: number;
  comment_count?: number;
  comments: CommentOnPost[];
}

export interface TopCommenter {
  username: string;
  comment_count: number;
  top_level_count?: number;
  reply_count?: number;
  posts_count: number;
  total_likes?: number;
  profile_url?: string;
  profile_pic_url?: string;
  is_verified?: boolean;
  by_post: CommenterPostGroup[];
}

export interface PostCommentStats {
  post_url: string;
  shortcode?: string;
  post_type?: string;
  post_owner_username?: string;
  total_comments_on_post?: number;
  comments_scraped: number;
  replies_scraped: number;
  unique_commenters: number;
}

export interface InstagramTopCommentersResponse {
  success: boolean;
  post_urls?: string[];
  results_limit?: number;
  posts_analyzed: number;
  total_comments: number;
  unique_commenters: number;
  post_stats?: PostCommentStats[];
  top_commenters: TopCommenter[];
  error?: string;
}

export async function fetchInstagramTopCommenters(
  urls: string[],
  options?: {
    profileUsername?: string;
    resultsLimit?: number;
    includeReplies?: boolean;
    topN?: number;
  },
): Promise<InstagramTopCommentersResponse> {
  return apiFetch('/api/samurai/instagram-top-commenters', {
    method: 'POST',
    body: JSON.stringify({
      urls,
      profile_username: options?.profileUsername,
      results_limit: options?.resultsLimit ?? 15,
      include_replies: options?.includeReplies ?? true,
      top_n: options?.topN ?? 10,
    }),
  });
}

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
  owner_username?: string;
}

export interface InstagramTimelineResponse {
  success: boolean;
  profile_username?: string;
  target_url?: string;
  results_limit?: number;
  posts: TimelinePost[];
  analytics: Record<string, unknown>;
  error?: string;
}

export async function fetchInstagramTimeline(
  username: string,
  options?: { resultsLimit?: number; skipPinned?: boolean; dataDetailLevel?: 'basicData' | 'detailedData' },
): Promise<InstagramTimelineResponse> {
  return apiFetch('/api/samurai/instagram-timeline', {
    method: 'POST',
    body: JSON.stringify({
      username,
      results_limit: options?.resultsLimit ?? 20,
      skip_pinned: options?.skipPinned ?? false,
      data_detail_level: options?.dataDetailLevel ?? 'basicData',
    }),
  });
}

export async function fetchIgPostMedia(shortcode: string): Promise<{
  shortcode: string;
  video_url?: string;
  display_url?: string;
  type?: string;
  is_video?: boolean;
}> {
  return apiFetch(`/api/samurai/instagram-media/${encodeURIComponent(shortcode)}`);
}
