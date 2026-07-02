import type { InvestigationResult } from '../types';
import { seedInDorkContext } from './googleDorkView';
import { resolveMediaUrl } from './displayFields';
import {
  groupByPlatform,
  isSocialPostUrl,
  openLinkLabel,
  platformFromUrl,
  platformLabel,
} from './platformUtils';

export interface DiscoveredKeyword {
  phrase: string;
  category: string;
  source_url?: string;
  source_title?: string;
  source_snippet?: string;
  score?: number;
}

export interface GoogleSearchHighlight {
  title: string;
  url: string;
  snippet: string;
  platform: string;
  topic: string;
  serp_phase: string;
  trigger_keyword: string;
  preview_url?: string;
}

export interface HackathonWin {
  hackathon: string;
  placement: string;
  title: string;
  url: string;
  snippet: string;
  platform: string;
  preview_url?: string;
  source?: string;
}

export interface CollegeDiscovery {
  college: string;
  page_name?: string;
  page_url?: string;
  title: string;
  url: string;
  snippet: string;
  platform: string;
  preview_url?: string;
}

export interface EmploymentDiscovery {
  employer: string;
  title: string;
  url: string;
  snippet: string;
  platform: string;
  preview_url?: string;
}

export interface GoogleSearchIntel {
  discovered_keywords: DiscoveredKeyword[];
  follow_up_queries: string[];
  seed_hit_count: number;
  highlights: GoogleSearchHighlight[];
  social_posts?: GoogleSearchHighlight[];
  social_posts_by_platform?: Record<string, GoogleSearchHighlight[]>;
  google_highlights?: GoogleSearchHighlight[];
  hackathon_wins?: HackathonWin[];
  colleges?: CollegeDiscovery[];
  employment?: EmploymentDiscovery[];
}

function highlightFromEntity(
  meta: Record<string, unknown>,
  ent: { entity_id?: string; fusion_score?: number; value?: string },
  seedQuery: string,
): GoogleSearchHighlight | null {
  const url = String(meta.url || ent.value || '');
  if (!url.startsWith('http') || !seedInDorkContext(meta, seedQuery)) return null;

  const title = String(meta.title || meta.dork_query || 'Google result');
  const snippet = String(meta.snippet || meta.content || '');
  const blob = `${title} ${snippet}`.toLowerCase();
  const trigger = String(meta.trigger_keyword || '');
  let topic = 'general';
  if (trigger) topic = 'achievement';
  else if (/hackathon|winner|runner-up|award|trophy|fest/.test(blob)) topic = 'achievement';
  else if (/college|university|institute|school|campus|polytechnic|academy/.test(blob)) topic = 'education';

  const preview = String(meta.page_screenshot_url || meta.preview_image_url || '');

  return {
    title,
    url,
    snippet: snippet.slice(0, 500),
    platform: platformFromUrl(url),
    topic,
    serp_phase: String(meta.serp_phase || 'follow_up'),
    trigger_keyword: trigger,
    preview_url: preview || undefined,
  };
}

function socialFromFusion(result: InvestigationResult, seedQuery: string): GoogleSearchHighlight[] {
  const out: GoogleSearchHighlight[] = [];
  const seen = new Set<string>();
  for (const ent of result.fusion?.deduplicated_entities ?? []) {
    const meta = (ent.metadata ?? {}) as Record<string, unknown>;
    if (meta.check_type !== 'google_dork') continue;
    const url = String(meta.url || ent.value || '');
    if (!isSocialPostUrl(url)) continue;
    const row = highlightFromEntity(meta, ent, seedQuery);
    if (!row || seen.has(row.url)) continue;
    seen.add(row.url);
    out.push(row);
  }
  return out;
}

export function googleSearchIntelFromResult(result: InvestigationResult | null): GoogleSearchIntel | null {
  if (!result) return null;
  const seedQuery = result.query || '';
  const intel = result.evidence_extraction?.google_search_intel;
  const fromEvidence = intel && typeof intel === 'object';

  const highlights = (fromEvidence ? (intel.highlights ?? []) : []) as GoogleSearchHighlight[];
  const keywords = (fromEvidence ? (intel.discovered_keywords ?? []) : []) as DiscoveredKeyword[];
  let socialPosts = (fromEvidence ? (intel.social_posts ?? []) : []) as GoogleSearchHighlight[];
  const googleHighlights = (fromEvidence ? (intel.google_highlights ?? []) : []) as GoogleSearchHighlight[];
  let hackathonWins = (fromEvidence ? (intel.hackathon_wins ?? []) : []) as HackathonWin[];
  let colleges = (fromEvidence ? (intel.colleges ?? []) : []) as CollegeDiscovery[];

  if (!socialPosts.length) {
    socialPosts = highlights.filter((h) => isSocialPostUrl(h.url) || h.platform !== 'web');
  }
  if (!socialPosts.length && seedQuery) {
    socialPosts = socialFromFusion(result, seedQuery);
  }

  if (!hackathonWins.length && socialPosts.length) {
    hackathonWins = socialPosts
      .filter((h) => /hackathon|winner|runner-up|fest|award|congratulations/i.test(`${h.title} ${h.snippet}`))
      .map((h) => ({
        hackathon: h.trigger_keyword || h.title.split(/[-–|]/)[0]?.trim() || 'Hackathon',
        placement: /runner-?up/i.test(`${h.title} ${h.snippet}`) ? 'runner_up' : /winner|won/i.test(`${h.title} ${h.snippet}`) ? 'winner' : 'mentioned',
        title: h.title,
        url: h.url,
        snippet: h.snippet,
        platform: h.platform,
        preview_url: h.preview_url,
        source: h.trigger_keyword,
      }));
  }

  if (!colleges.length && socialPosts.length) {
    const seen = new Set<string>();
    for (const post of socialPosts) {
      const prefix = post.title.split(/[-–|]/)[0]?.trim();
      if (!prefix || prefix.length < 3 || seen.has(prefix.toLowerCase())) continue;
      if (!/college|institute|university|school|campus|congrat|hackathon/i.test(`${post.title} ${post.snippet}`)) {
        continue;
      }
      seen.add(prefix.toLowerCase());
      colleges.push({
        college: prefix,
        page_name: prefix,
        title: post.title,
        url: post.url,
        snippet: post.snippet,
        platform: post.platform,
        preview_url: post.preview_url,
      });
    }
  }

  if (
    !highlights.length
    && !keywords.length
    && !socialPosts.length
    && !googleHighlights.length
    && !hackathonWins.length
    && !colleges.length
  ) {
    return null;
  }

  const socialPostsByPlatform = Object.fromEntries(
  groupByPlatform(socialPosts, (h) => h.platform || platformFromUrl(h.url)),
);

  return {
    discovered_keywords: keywords,
    follow_up_queries: (fromEvidence ? (intel.follow_up_queries ?? []) : []) as string[],
    seed_hit_count: Number(fromEvidence ? intel.seed_hit_count ?? 0 : 0),
    highlights,
    social_posts: socialPosts,
    social_posts_by_platform: socialPostsByPlatform,
    google_highlights: googleHighlights,
    hackathon_wins: hackathonWins,
    colleges,
  };
}

export { openLinkLabel, platformLabel, resolveMediaUrl };

export function categoryLabel(category: string): string {
  const map: Record<string, string> = {
    achievement: 'Achievement',
    education: 'Education',
    organization: 'Organization',
    professional: 'Professional',
    social: 'Social',
    identity: 'Identity',
  };
  return map[category] || category.replace(/_/g, ' ');
}

export function placementLabel(placement: string): string {
  const map: Record<string, string> = {
    winner: 'Winner',
    won: 'Winner',
    runner_up: 'Runner-up',
    'runner-up': 'Runner-up',
    finalist: 'Finalist',
    champion: 'Champion',
    mentioned: 'Mentioned',
  };
  return map[placement] || placement.replace(/_/g, ' ');
}
