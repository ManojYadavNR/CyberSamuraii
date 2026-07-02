import type { InvestigationResult } from '../types';
import { dedupeByUrl } from './dedupeUrl';
import { fixFacebookPostUrl } from './socialUrls';
import {
  groupByPlatform,
  isSocialPostUrl,
  normalizePlatformHost,
  openLinkLabel,
  platformFromUrl,
  platformKey,
  platformLabel,
  profileSlugFromUrl,
} from './platformUtils';

export interface GoogleDorkItem {
  id: string;
  title: string;
  url: string;
  snippet: string;
  dorkQuery: string;
  dorkCategory: string;
  categoryLabel: string;
  platform: string;
  platformHost: string;
  platformKey: string;
  attributed: boolean;
  previewUrl?: string;
  isSocialPost: boolean;
}

const CATEGORY_LABELS: Record<string, string> = {
  achievements: 'Hackathon / Achievement',
  news_mentions: 'News',
  events_general: 'Event',
  education: 'College / School',
  article_search: 'Article',
  blog_search: 'Blog',
  forum_mentions: 'Forum',
  profile_exact: 'Profile',
  google_plain: 'Web',
};

function categoryLabel(cat: string): string {
  return CATEGORY_LABELS[cat] || cat.replace(/_/g, ' ');
}

/** Split CamelCase handles into a display name for matching Google titles. */
function displayNameFromHandle(handle: string): string | null {
  const raw = handle.trim();
  if (!raw || raw.includes('@') || /\s/.test(raw)) return null;
  const spaced = raw.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2');
  const parts = spaced.split(/\s+/).filter(Boolean);
  return parts.length >= 2 ? parts.join(' ') : null;
}

/** True when URL/title/snippet references the investigated username or derived name. */
function isGarbageSerpBundle(title: string, _snippet = ''): boolean {
  if (title.length < 120) return false;
  const low = title.toLowerCase();
  const domainTokens = low.match(/\b(?:\w+\.){1,2}(?:com|org|net|io|co)\b/g) ?? [];
  if (new Set(domainTokens).size >= 2) return true;
  const compact = low.replace(/\s/g, '');
  return /\w+(?:com|org)\w+(?:com|org)/.test(compact);
}

/** Split multi-input targets: username | email | phone */
export function investigationSeedTokens(seedQuery: string): string[] {
  const seen = new Set<string>();
  const tokens: string[] = [];
  for (const part of seedQuery.split(/[|;/\n]+/)) {
    const clean = part.trim();
    if (!clean || seen.has(clean.toLowerCase())) continue;
    seen.add(clean.toLowerCase());
    tokens.push(clean);
  }
  return tokens.length ? tokens : [seedQuery.trim()];
}

function seedTokenInContext(
  token: string,
  blob: string,
  blobCompact: string,
  url: string,
): boolean {
  const seedLower = token.toLowerCase();
  const compact = seedLower.replace(/[^\w]/g, '');

  if (seedLower.includes('@')) {
    if (blob.includes(seedLower)) return true;
    const local = seedLower.split('@')[0];
    if (local.length >= 4 && blobCompact.includes(local.replace(/[^\w]/g, ''))) return true;
    return false;
  }

  if (compact.length >= 4 && blobCompact.includes(compact)) return true;
  if (seedLower.length >= 4 && blobCompact.includes(seedLower.replace(/[-_]/g, ''))) return true;

  const displayName = displayNameFromHandle(token);
  if (displayName) {
    const nameLower = displayName.toLowerCase();
    if (blob.includes(nameLower)) return true;
    const nameCompact = nameLower.replace(/[^\w]/g, '');
    if (nameCompact.length >= 6 && blobCompact.includes(nameCompact)) return true;
  }

  try {
    const path = new URL(url).pathname.toLowerCase().replace(/[-_]/g, '');
    if (compact.length >= 4 && path.includes(compact)) return true;
  } catch {
    /* ignore */
  }
  return false;
}

/** Seed must appear in SERP title/snippet/URL — not in the dork query alone. */
export function seedInHitText(title: string, snippet: string, url: string, seedQuery: string): boolean {
  if (!seedQuery.trim()) return false;
  const blob = `${title} ${snippet} ${url}`.toLowerCase();
  const blobCompact = blob.replace(/[-_]/g, '');
  return investigationSeedTokens(seedQuery).some((token) =>
    seedTokenInContext(token, blob, blobCompact, url),
  );
}

function profileHandleConflictsSeed(url: string, seedQuery: string): boolean {
  if (!url || !seedQuery.trim()) return false;
  const username = investigationSeedTokens(seedQuery)[0] ?? '';
  const compact = username.toLowerCase().replace(/[^\w]/g, '');
  const blob = url.toLowerCase().replace(/[-_]/g, '');
  if (compact.length >= 8 && blob.includes(compact)) return false;
  if (isSocialPostUrl(url)) return false;
  const handle = profileSlugFromUrl(url);
  if (!handle) return false;
  const handleNorm = handle.replace(/[^\w]/g, '');
  return handleNorm.length >= 3 && handleNorm !== compact && !compact.includes(handleNorm) && !handleNorm.includes(compact);
}

export function seedInDorkContext(meta: Record<string, unknown>, seedQuery: string): boolean {
  if (!seedQuery.trim()) return false;

  const url = String(meta.url || '');
  const title = String(meta.title || '');
  const snippet = String(meta.snippet || meta.content || '');
  if (isGarbageSerpBundle(title, snippet)) return false;
  if (profileHandleConflictsSeed(url, seedQuery)) return false;

  const slugCheck = socialPostSlugReferencesSeed(url, seedQuery);
  if (slugCheck === false) return false;

  return seedInHitText(title, snippet, url, seedQuery);
}

function normalizeDorkUrl(url: string): string {
  try {
    const u = new URL(url);
    u.hash = '';
    return `${u.origin}${u.pathname}`.replace(/\/$/, '').toLowerCase();
  } catch {
    return url.split('?')[0].replace(/\/$/, '').toLowerCase();
  }
}

const NUMERIC_FB_PHOTO_RE = /\/photos\/(?:a\.\d+\/\d+|\d+)\/?$/i;
const NUMERIC_FB_POST_RE = /\/posts\/\d+\/?$/i;
const OPAQUE_SOCIAL_POST_RE = /\/(?:p|reel|reels|stories|tv)\/[a-z0-9_-]{5,}\/?$/i;

function pathSlugCompact(url: string): string {
  try {
    return new URL(url).pathname.toLowerCase().replace(/[^\w]/g, '');
  } catch {
    return '';
  }
}

/** For readable social post slugs, seed must appear in the URL path (not snippet alone). */
function socialPostSlugReferencesSeed(url: string, seedQuery: string): boolean | null {
  if (!isSocialPostUrl(url)) return null;
  const path = url.toLowerCase();
  if (NUMERIC_FB_PHOTO_RE.test(path) || NUMERIC_FB_POST_RE.test(path) || OPAQUE_SOCIAL_POST_RE.test(path)) return null;

  const slug = pathSlugCompact(url);
  if (slug.length < 12) return null;

  for (const token of investigationSeedTokens(seedQuery)) {
    const compact = token.toLowerCase().replace(/[^\w]/g, '');
    if (compact.length >= 4 && slug.includes(compact)) return true;
    const displayName = displayNameFromHandle(token);
    if (displayName) {
      const nameCompact = displayName.toLowerCase().replace(/[^\w]/g, '');
      if (nameCompact.length >= 6 && slug.includes(nameCompact)) return true;
    }
  }

  if (/congratulations-to-|\/posts\/|\/photos\//.test(path)) return false;
  return null;
}

function normalizeContentBlob(text: string): string {
  return text.toLowerCase().replace(/[^\w\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

function contentDedupeKey(item: GoogleDorkItem): string {
  const snippet = normalizeContentBlob(item.snippet);
  if (snippet.length >= 40) return `snippet:${snippet.slice(0, 150)}`;
  return `title:${normalizeContentBlob(item.title).slice(0, 80)}`;
}

function isHackathonItem(item: GoogleDorkItem): boolean {
  const blob = `${item.title} ${item.snippet} ${item.dorkCategory}`.toLowerCase();
  return item.attributed && (
    item.dorkCategory === 'achievements'
    || item.dorkCategory === 'events_general'
    || /hackathon|winner|won|finalist|champion|devpost|award|trophy|competition|runner-up|runners-up/.test(blob)
  );
}

function isNewsItem(item: GoogleDorkItem): boolean {
  const blob = `${item.title} ${item.snippet}`.toLowerCase();
  return item.attributed && (
    item.dorkCategory === 'news_mentions'
    || item.dorkCategory === 'article_search'
    || item.dorkCategory === 'blog_search'
    || /news|headline|reported|coverage|newspaper|article|congratulations/.test(blob)
  );
}

function isCollegeHomepageUrl(url: string): boolean {
  if (isSocialPostUrl(url)) return false;
  try {
    const { hostname, pathname } = new URL(url);
    const host = hostname.toLowerCase();
    const isEduHost = /\.(edu|ac\.in|edu\.|gov\.)(\.|$)/.test(host)
      || /college|university|institute|school|academy/.test(host);
    if (!isEduHost) return false;
    const segments = pathname.split('/').filter(Boolean);
    return segments.length <= 1;
  } catch {
    return false;
  }
}

const FB_PAGE_POST_RE = /facebook\.com\/([^/?#]+)\/(?:photos|posts|videos|reel|permalink)/i;
const INSTITUTION_NAME_RE = /\b([A-Z][\w\s&'.-]{2,60}(?:Institute|College|University|School|Academy|Polytechnic)(?:\s+of\s+[A-Z][\w\s&'.-]{2,32})?(?:\s+North\s+Campus)?)/gi;

export interface PrimaryCollege {
  name: string;
  pageUrl: string;
  previewUrl?: string;
  sourceUrl?: string;
}

interface CollegeAnchors {
  fbSlugs: Set<string>;
  names: Set<string>;
}

function extractCollegeAnchors(items: GoogleDorkItem[], seedQuery: string): CollegeAnchors {
  const fbSlugs = new Set<string>();
  const names = new Set<string>();

  for (const item of items) {
    if (!seedInHitText(item.title, item.snippet, item.url, seedQuery)) continue;
    if (!item.isSocialPost || !item.url.toLowerCase().includes('facebook.com')) continue;

    const pageMatch = item.url.match(FB_PAGE_POST_RE);
    if (pageMatch) fbSlugs.add(pageMatch[1].toLowerCase());

    const text = `${item.title} ${item.snippet}`;
    for (const match of text.matchAll(INSTITUTION_NAME_RE)) {
      const name = normalizeContentBlob(match[1]);
      if (name.length >= 8) names.add(name);
    }
    if (item.title.includes(' - ')) {
      const prefix = normalizeContentBlob(item.title.split(' - ')[0]);
      if (prefix.length >= 4) names.add(prefix);
    }
  }

  return { fbSlugs, names };
}

function collegeMatchesAnchors(item: GoogleDorkItem, anchors: CollegeAnchors): boolean {
  if (anchors.fbSlugs.size === 0 && anchors.names.size === 0) return true;

  const url = item.url.toLowerCase();
  for (const slug of anchors.fbSlugs) {
    if (url.includes(`facebook.com/${slug}`)) return true;
  }

  const blob = normalizeContentBlob(`${item.title} ${item.snippet}`);
  for (const name of anchors.names) {
    if (name.length >= 8 && blob.includes(name)) return true;
  }
  return false;
}

function isCollegeItem(item: GoogleDorkItem, seedQuery: string, anchors: CollegeAnchors): boolean {
  if (!item.attributed) return false;
  if (isCollegeHomepageUrl(item.url)) return false;
  if (!seedInHitText(item.title, item.snippet, item.url, seedQuery)) return false;
  if (!collegeMatchesAnchors(item, anchors)) return false;

  const textBlob = `${item.title} ${item.snippet}`.toLowerCase();
  const hasInstitution = /college|university|institute|campus|school|alumni|polytechnic|academy/.test(
    `${textBlob} ${item.url}`,
  );
  if (!hasInstitution && item.dorkCategory !== 'education') return false;

  const collegePostContext = /congrat|student|alumni|placement|campus|hackathon|winner|runner|proud|nurturing|achievement/.test(
    textBlob,
  );
  if (item.dorkCategory === 'education') return true;
  if (item.isSocialPost && /facebook|instagram/.test(item.url) && collegePostContext) return true;
  return collegePostContext && hasInstitution;
}

function titleCaseInstitution(value: string): string {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

export function extractPrimaryColleges(
  result: InvestigationResult | null,
  items: GoogleDorkItem[],
  anchors: CollegeAnchors,
): PrimaryCollege[] {
  const colleges: PrimaryCollege[] = [];
  const seen = new Set<string>();

  const add = (name: string, pageUrl: string, previewUrl?: string, sourceUrl?: string) => {
    const clean = name.trim();
    if (!clean || clean.length < 6) return;
    const key = clean.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    colleges.push({
      name: titleCaseInstitution(clean),
      pageUrl: fixFacebookPostUrl(pageUrl),
      previewUrl,
      sourceUrl: sourceUrl ? fixFacebookPostUrl(sourceUrl) : undefined,
    });
  };

  const intelColleges = result?.evidence_extraction?.google_search_intel?.colleges as Array<Record<string, string>> | undefined;
  for (const row of intelColleges ?? []) {
    add(
      String(row.college || row.official_name || row.page_name || ''),
      String(row.page_url || row.url || ''),
      String(row.preview_url || ''),
      String(row.url || ''),
    );
  }

  for (const name of anchors.names) {
    if (name.length < 10) continue;
    const slug = [...anchors.fbSlugs][0];
    if (!slug) continue;
    const pageUrl = `https://www.facebook.com/${slug}`;
    const match = items.find((item) =>
      item.url.toLowerCase().includes(`facebook.com/${slug}`) && item.previewUrl,
    );
    add(name, pageUrl, match?.previewUrl, match?.url);
  }

  for (const item of items) {
    if (!item.isSocialPost || !item.url.includes('facebook.com')) continue;
    const pageMatch = item.url.match(FB_PAGE_POST_RE);
    if (!pageMatch) continue;
    const slug = pageMatch[1];
    const text = `${item.title} ${item.snippet}`;
    for (const match of text.matchAll(INSTITUTION_NAME_RE)) {
      const name = normalizeContentBlob(match[1]);
      if (name.length >= 12) {
        add(name, `https://www.facebook.com/${slug}`, item.previewUrl, item.url);
      }
    }
    if (item.title.includes(' - ')) {
      const right = item.title.split(' - ').slice(1).join(' - ').trim();
      if (/institute|college|university|campus|school/i.test(right)) {
        add(right.replace(/\.\.\./g, '').trim(), `https://www.facebook.com/${slug}`, item.previewUrl, item.url);
      }
    }
  }

  return colleges;
}

function isSocialPostItem(item: GoogleDorkItem): boolean {
  return Boolean(item.attributed && item.isSocialPost);
}

export function buildGoogleDorkItems(
  result: InvestigationResult | null,
  seedQuery = '',
): {
  all: GoogleDorkItem[];
  hackathon: GoogleDorkItem[];
  news: GoogleDorkItem[];
  college: GoogleDorkItem[];
  primaryColleges: PrimaryCollege[];
  social: GoogleDorkItem[];
  socialByPlatform: Map<string, GoogleDorkItem[]>;
} {
  if (!result) {
    return { all: [], hackathon: [], news: [], college: [], primaryColleges: [], social: [], socialByPlatform: new Map() };
  }

  const items: GoogleDorkItem[] = [];
  const seen = new Set<string>();

  for (const ent of result.fusion?.deduplicated_entities ?? []) {
    const meta = (ent.metadata ?? {}) as Record<string, unknown>;
    if (meta.check_type !== 'google_dork' && ent.type !== 'document') continue;
    if (meta.check_type !== 'google_dork') continue;

    const url = fixFacebookPostUrl(String(meta.url || ent.value || ''));
    const dedupeKey = normalizeDorkUrl(url);
    if (!url.startsWith('http') || seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);

    const title = String(meta.title || meta.dork_query || 'Google result');
    const snippet = String(meta.snippet || meta.content || '');
    const dorkCategory = String(meta.dork_category || 'general');
    const preview = String(meta.page_screenshot_url || meta.preview_image_url || '');
    const attributed = seedInDorkContext(meta, seedQuery);
    const platformHost = normalizePlatformHost(url);
    const key = platformKey(url);

    if (seedQuery && !attributed) continue;

    items.push({
      id: ent.entity_id || url,
      title,
      url,
      snippet,
      dorkQuery: String(meta.dork_query || ''),
      dorkCategory,
      categoryLabel: categoryLabel(dorkCategory),
      platform: String(meta.platform || meta.display_link || platformHost),
      platformHost,
      platformKey: key,
      attributed,
      previewUrl: preview || undefined,
      isSocialPost: isSocialPostUrl(url),
    });
  }

  items.sort((a, b) => {
    const score = (x: GoogleDorkItem) =>
      (x.attributed ? 20 : 0)
      + (x.isSocialPost ? 15 : 0)
      + (isHackathonItem(x) ? 10 : 0)
      + (x.previewUrl ? 5 : 0)
      + (x.snippet.length > 20 ? 2 : 0);
    return score(b) - score(a);
  });

  const social = items.filter(isSocialPostItem);
  const collegeAnchors = extractCollegeAnchors(
    items.filter((item) => isHackathonItem(item) || isSocialPostItem(item)),
    seedQuery,
  );
  const usedUrls = new Set<string>();
  const usedContent = new Set<string>();
  const takeUnique = (list: GoogleDorkItem[]) => {
    const unique = dedupeByUrl(list, (item) => item.url);
    return unique.filter((item) => {
      const urlKey = item.url.toLowerCase();
      if (usedUrls.has(urlKey)) return false;
      const contentKey = contentDedupeKey(item);
      if (usedContent.has(contentKey)) return false;
      usedUrls.add(urlKey);
      usedContent.add(contentKey);
      return true;
    });
  };

  const primaryColleges = extractPrimaryColleges(result, items, collegeAnchors);

  return {
    all: items,
    hackathon: takeUnique(items.filter(isHackathonItem)),
    news: takeUnique(items.filter(isNewsItem)),
    college: takeUnique(items.filter((item) => isCollegeItem(item, seedQuery, collegeAnchors))),
    primaryColleges,
    social: takeUnique(social),
    socialByPlatform: groupByPlatform(social, (item) => item.platformKey),
  };
}

export { openLinkLabel, platformLabel, platformFromUrl };
