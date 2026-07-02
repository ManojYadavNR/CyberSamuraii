import type { FieldProvenance, IdentityProfile, InvestigationResult } from '../types';
import { isVerifiedLinkedAccount, isVerifiedPlatformProfile } from './accountVerification';
import { getVerifiedPlatformDetails } from './platformAccountView';
import { platformLabel } from './platformUtils';

export interface OsintIntelItem {
  id: string;
  label: string;
  value: string;
  confidence?: number;
  source?: string;
  sourcePlatform?: string;
  url?: string;
  imageUrl?: string;
  thumbnailUrl?: string;
  provenance?: string;
  renderAs?: 'image' | 'video' | 'account';
}

export interface OsintIntelSection {
  id: string;
  title: string;
  icon: string;
  description?: string;
  items: OsintIntelItem[];
}

const BRANDING_IMAGE_HINTS = [
  '/favicon', 'favicon.', '/logo', '/logos/', '/icon-', '/icons/', '/apple-touch-icon',
  '/sprite', '/badge', '/brand/', '/static/images/logo', '/assets/logo', '/default-avatar',
  'opengraph-image', '/share-image', 'placeholder', '1x1.', 'pixel.',
];

function isImageUrl(value: string): boolean {
  if (!value.startsWith('http')) return false;
  const low = value.toLowerCase();
  if (/\.(jpg|jpeg|png|webp|gif|bmp)(\?.*)?$/i.test(low)) return true;
  if (['/avatar', '/photo', '/image', '/img/', 'profile_pic', 'display_url', 'media'].some((h) => low.includes(h))) {
    return true;
  }
  return false;
}

function isPlausiblePhoto(value: string): boolean {
  if (value.startsWith('/api/intel/screenshots/')) return true;
  if (!isImageUrl(value)) return false;
  const low = value.toLowerCase();
  if (BRANDING_IMAGE_HINTS.some((hint) => low.includes(hint))) return false;
  if (low.endsWith('.svg') || low.endsWith('.ico')) return false;
  return true;
}

function domainFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function splitRef(value: string): { label: string; url: string } {
  if (value.includes('|')) {
    const [label, url] = value.split('|', 2);
    return { label: label.trim(), url: url.trim() };
  }
  return { label: value, url: value.startsWith('http') ? value : '' };
}

function fpToItem(fp: FieldProvenance, prefix: string, index = 0): OsintIntelItem {
  const ref = splitRef(fp.value);
  const pageUrl = ref.url || (fp.value.startsWith('http') ? fp.value : fp.source_ref);
  const imageUrl = fp.field === 'avatar_url' || fp.field === 'image' || fp.field === 'image_url'
    ? fp.value.startsWith('http') ? fp.value : undefined
    : undefined;
  return {
    id: `${prefix}_${fp.field}_${index}_${fp.value.slice(0, 40)}`,
    label: fp.field.replace(/_/g, ' '),
    value: ref.label || fp.value,
    confidence: fp.confidence,
    source: fp.source_tool,
    sourcePlatform: fp.source_platform,
    url: pageUrl?.startsWith('http') ? pageUrl : undefined,
    imageUrl: imageUrl && isPlausiblePhoto(imageUrl) ? imageUrl : undefined,
    thumbnailUrl: fp.field === 'thumbnail_url' && fp.value.startsWith('http') ? fp.value : undefined,
    provenance: fp.extraction_strategy || fp.source_ref,
    renderAs: imageUrl && isPlausiblePhoto(imageUrl) ? 'image' : undefined,
  };
}

function dedupeItems(items: OsintIntelItem[]): OsintIntelItem[] {
  const seen = new Set<string>();
  const out: OsintIntelItem[] = [];
  for (const item of items) {
    const key = `${item.label}:${item.value}:${item.url ?? ''}:${item.imageUrl ?? ''}`.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out.sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
}

function isLoginUrl(url: string | undefined): boolean {
  if (!url) return false;
  return /\/login(?:[/?]|$)|\/signin(?:[/?]|$)/i.test(url);
}

function collectPhotos(
  result: InvestigationResult,
  id?: IdentityProfile,
  unified = result.evidence_extraction?.unified_profile,
  seedQuery = '',
): OsintIntelItem[] {
  const items: OsintIntelItem[] = [];
  const seen = new Set<string>();

  const add = (url: string, label: string, source?: string, platform?: string, confidence?: number, pageUrl?: string) => {
    if (!url || seen.has(url)) return;
    const displayable = isPlausiblePhoto(url) || url.startsWith('/api/intel/screenshots/');
    if (!displayable) return;
    seen.add(url);
    items.push({
      id: `photo_${url.slice(-48)}`,
      label,
      value: url,
      confidence,
      source,
      sourcePlatform: platform || domainFromUrl(url),
      url: pageUrl || url,
      imageUrl: url,
      renderAs: 'image',
      provenance: platform ? `From ${platform}` : source,
    });
  };

  if (id?.primary_avatar) add(id.primary_avatar, 'Primary photo', 'identity_profile');
  for (const fp of [...(id?.photos ?? []), ...(unified?.images ?? [])]) {
    add(fp.value, 'Profile photo', fp.source_tool, fp.source_platform, fp.confidence, fp.source_ref);
  }
  for (const fp of [...(id?.search_findings ?? []), ...(unified?.search_findings ?? [])]) {
    if (['avatar_url', 'image', 'image_url'].includes(fp.field) && fp.value.startsWith('http')) {
      add(fp.value, 'Search discovery', fp.source_tool, fp.source_platform, fp.confidence, fp.source_ref);
    }
  }
  for (const pp of [...(id?.platform_profiles ?? []), ...(unified?.platform_profiles ?? [])]) {
    if (!isVerifiedPlatformProfile(pp)) continue;
    if (pp.avatar_url) add(pp.avatar_url, pp.display_name || pp.handle || 'Profile', (pp.sources ?? []).join(', '), pp.platform, pp.fusion_score, pp.url);
    for (const fp of pp.extracted_fields ?? []) {
      if (fp.field === 'avatar_url' || fp.field === 'image') {
        add(fp.value, `${pp.platform} photo`, fp.source_tool, pp.platform, fp.confidence, pp.url);
      }
    }
  }
  for (const cluster of result.correlation?.clusters ?? []) {
    for (const acct of cluster.linked_accounts ?? []) {
      if (!isVerifiedLinkedAccount(acct)) continue;
      if (acct.avatar_url) add(acct.avatar_url, acct.display_name || acct.handle, (acct.sources ?? []).join(', '), acct.platform, acct.fusion_score, acct.url);
    }
  }
  for (const ent of result.fusion?.deduplicated_entities ?? []) {
    const meta = (ent.metadata ?? {}) as Record<string, unknown>;
    if (meta.check_type !== 'google_dork') continue;
    const img = String(meta.url || ent.value);
    if (meta.dork_category === 'media_images' || ent.type === 'image') {
      add(img, String(meta.title || 'Web image'), 'google_dorking', String(meta.platform || domainFromUrl(img)), ent.fusion_score, String(meta.page_url || meta.source_url || ''));
    }
    const structured = meta.structured_intelligence as Record<string, unknown> | undefined;
    const images = structured?.images;
    if (Array.isArray(images)) {
      for (const imgUrl of images) {
        if (typeof imgUrl === 'string') {
          add(imgUrl, String(meta.title || 'Article image'), 'google_dorking', domainFromUrl(imgUrl), ent.fusion_score, String(meta.url || ''));
        }
      }
    }
    const preview = String(meta.preview_image_url || meta.page_screenshot_url || '');
    if (preview) {
      add(
        preview,
        String(meta.title || 'Page preview'),
        'page_capture',
        domainFromUrl(String(meta.url || ent.value)),
        ent.fusion_score,
        String(meta.url || ent.value),
      );
    }
    if (seedQuery && meta.title && typeof meta.snippet === 'string') {
      const imgMatch = String(meta.snippet).match(/https?:\/\/[^\s"'<>]+\.(?:jpg|jpeg|png|webp|gif)/i);
      if (imgMatch) {
        add(imgMatch[0], String(meta.title), 'google_dorking', domainFromUrl(imgMatch[0]), ent.fusion_score, String(meta.url || ''));
      }
    }
  }
  return items;
}

interface GoogleIntelRow {
  title?: string;
  url?: string;
  snippet?: string;
  platform?: string;
  preview_url?: string;
  college?: string;
  page_name?: string;
  page_url?: string;
  hackathon?: string;
  employer?: string;
  placement?: string;
  website_url?: string;
  instagram_url?: string;
}

function itemsFromGoogleSearchIntel(result: InvestigationResult): {
  photos: OsintIntelItem[];
  events: OsintIntelItem[];
  social: OsintIntelItem[];
  colleges: OsintIntelItem[];
  employers: OsintIntelItem[];
} {
  const intel = result.evidence_extraction?.google_search_intel as Record<string, GoogleIntelRow[]> | undefined;
  if (!intel) {
    return { photos: [], events: [], social: [], colleges: [], employers: [] };
  }

  const photos: OsintIntelItem[] = [];
  const events: OsintIntelItem[] = [];
  const social: OsintIntelItem[] = [];
  const colleges: OsintIntelItem[] = [];
  const employers: OsintIntelItem[] = [];
  const seen = new Set<string>();

  const addPhoto = (url: string | undefined, label: string, pageUrl?: string, platform?: string) => {
    if (!url || seen.has(url)) return;
    const resolved = url.startsWith('http') || url.startsWith('/api/') ? url : undefined;
    if (!resolved || (!isPlausiblePhoto(resolved) && !resolved.startsWith('/api/'))) return;
    seen.add(url);
    photos.push({
      id: `gsi_photo_${url.slice(-40)}`,
      label,
      value: label,
      source: 'google_search_intel',
      sourcePlatform: platform || (pageUrl ? domainFromUrl(pageUrl) : undefined),
      url: pageUrl || resolved,
      imageUrl: resolved,
      renderAs: 'image',
    });
  };

  for (const win of intel.hackathon_wins ?? []) {
    addPhoto(win.preview_url, win.hackathon || win.title || 'Hackathon win', win.url, win.platform);
    events.push({
      id: `gsi_win_${win.url}`,
      label: 'Hackathon win',
      value: win.hackathon || win.title || 'Hackathon',
      source: 'google_search_intel',
      sourcePlatform: win.platform,
      url: win.url,
      imageUrl: win.preview_url && (isPlausiblePhoto(win.preview_url) || win.preview_url.startsWith('/api/'))
        ? win.preview_url
        : undefined,
      provenance: win.snippet,
      renderAs: win.preview_url ? 'image' : undefined,
    });
  }

  for (const college of intel.colleges ?? []) {
    addPhoto(college.preview_url, college.college || college.page_name || 'College', college.page_url || college.url, college.platform);
    colleges.push({
      id: `gsi_college_${college.url}`,
      label: 'College',
      value: college.college || college.page_name || college.title || 'College',
      source: 'google_search_intel',
      sourcePlatform: college.platform,
      url: college.page_url || college.url,
      imageUrl: college.preview_url && (isPlausiblePhoto(college.preview_url) || college.preview_url.startsWith('/api/'))
        ? college.preview_url
        : undefined,
      provenance: [
        college.snippet,
        college.website_url ? `Website: ${college.website_url}` : '',
        college.instagram_url ? `${platformLabel(college.instagram_url)}: ${college.instagram_url}` : '',
      ].filter(Boolean).join(' · ') || college.page_name,
      renderAs: college.preview_url ? 'image' : undefined,
    });
    for (const ach of (college as { website_achievements?: Array<{ text?: string; hackathon?: string }> }).website_achievements ?? []) {
      if (!ach.text) continue;
      events.push({
        id: `gsi_web_${ach.text.slice(0, 40)}`,
        label: 'College website achievement',
        value: ach.hackathon || ach.text.slice(0, 120),
        source: 'college_website',
        sourcePlatform: college.website_url ? domainFromUrl(college.website_url) : 'web',
        url: college.website_url || college.page_url,
        provenance: ach.text,
      });
    }
  }

  for (const post of intel.social_posts ?? []) {
    if (!post.url || seen.has(`social:${post.url}`)) continue;
    seen.add(`social:${post.url}`);
    addPhoto(post.preview_url, post.title || 'Social post', post.url, post.platform);
    social.push({
      id: `gsi_social_${post.url}`,
      label: post.platform ? `${platformLabel(post.platform)} post` : 'Social post',
      value: post.title || post.url || 'Post',
      source: 'google_search_intel',
      sourcePlatform: post.platform,
      url: post.url,
      imageUrl: post.preview_url && (isPlausiblePhoto(post.preview_url) || post.preview_url.startsWith('/api/'))
        ? post.preview_url
        : undefined,
      provenance: post.snippet,
      renderAs: post.preview_url ? 'image' : undefined,
    });
  }

  for (const job of intel.employment ?? []) {
    employers.push({
      id: `gsi_job_${job.url}`,
      label: 'Employer',
      value: job.employer || job.title || 'Employer',
      source: 'google_search_intel',
      sourcePlatform: job.platform,
      url: job.url,
      imageUrl: job.preview_url && (isPlausiblePhoto(job.preview_url) || job.preview_url.startsWith('/api/'))
        ? job.preview_url
        : undefined,
      provenance: job.snippet,
    });
  }

  return { photos, events, social, colleges, employers };
}

function accountsFromResult(result: InvestigationResult, _identity?: IdentityProfile): OsintIntelItem[] {
  return getVerifiedPlatformDetails(result)
    .filter((detail) => !isLoginUrl(detail.url))
    .map((detail) => ({
      id: detail.entityId,
      label: detail.displayName || detail.handle || detail.platformLabel,
      value: detail.url || `${detail.platform}/${detail.handle}`,
      confidence: detail.fusionScore,
      source: detail.sources.join(', '),
      sourcePlatform: detail.platform,
      url: detail.url,
      imageUrl: detail.avatarUrl && isPlausiblePhoto(detail.avatarUrl) ? detail.avatarUrl : undefined,
      provenance: detail.groups.flatMap((g) => g.items.map((i) => i.value)).slice(0, 3).join(' · ') || 'Verified',
      renderAs: 'account' as const,
    }));
}

function dorkContentItems(
  result: InvestigationResult,
  fields: Set<string>,
  label: string,
): OsintIntelItem[] {
  const items: OsintIntelItem[] = [];
  for (const ent of result.fusion?.deduplicated_entities ?? []) {
    const meta = (ent.metadata ?? {}) as Record<string, unknown>;
    if (meta.check_type !== 'google_dork' && ent.type !== 'document') continue;
    const title = String(meta.title || ent.value);
    const url = String(meta.url || ent.value);
    const snippet = String(meta.snippet || '');
    const category = String(meta.dork_category || '');
    const isEvent = fields.has('event') && (
      category.includes('event') || category === 'achievements' ||
      /hackathon|winner|conference|competition|award|meetup|workshop/i.test(`${title} ${snippet}`)
    );
    const isArticle = fields.has('article') && (
      category.includes('news') || category.includes('blog') || category.includes('article') ||
      /blog|article|news|post/i.test(category)
    );
    if (!isEvent && !isArticle) continue;
    const ref = splitRef(`${title}|${url}`);
    const imgMatch = snippet.match(/https?:\/\/[^\s"'<>]+\.(?:jpg|jpeg|png|webp|gif)/i);
    const structured = meta.structured_intelligence as Record<string, unknown> | undefined;
    const structImg = Array.isArray(structured?.images) ? structured?.images[0] : undefined;
    const preview = String(meta.preview_image_url || meta.page_screenshot_url || '');
    const imageUrl = typeof structImg === 'string' ? structImg : imgMatch?.[0] || (preview || undefined);
    items.push({
      id: `dork_${ent.entity_id || url}`,
      label: isEvent ? 'Event' : label,
      value: ref.label || title,
      confidence: ent.fusion_score,
      source: preview && !structImg && !imgMatch ? 'page screenshot' : 'google_dorking',
      sourcePlatform: domainFromUrl(url),
      url,
      imageUrl: imageUrl && (isPlausiblePhoto(imageUrl) || imageUrl.startsWith('/api/')) ? imageUrl : undefined,
      thumbnailUrl: imageUrl && (isPlausiblePhoto(imageUrl) || imageUrl.startsWith('/api/')) ? imageUrl : undefined,
      provenance: snippet.slice(0, 200) || category,
      renderAs: imageUrl ? 'image' : undefined,
    });
  }
  return items;
}

function videosFromProfile(id?: IdentityProfile, unified = id?.platform_profiles): OsintIntelItem[] {
  const items: OsintIntelItem[] = [];
  const addVideo = (title: string, url: string, thumb?: string, source?: string, platform?: string, confidence?: number) => {
    if (!url.startsWith('http')) return;
    items.push({
      id: `vid_${url.slice(-40)}`,
      label: title || 'Video',
      value: url,
      confidence,
      source,
      sourcePlatform: platform,
      url,
      thumbnailUrl: thumb,
      provenance: platform ? `Published on ${platform}` : source,
      renderAs: 'video',
    });
  };

  for (const fp of id?.events ?? []) {
    if (fp.field !== 'media_video' && fp.field !== 'video') continue;
    const ref = splitRef(fp.value);
    const thumb = (id?.search_findings ?? []).find((s) => s.field === 'thumbnail_url')?.value;
    addVideo(ref.label, ref.url || ref.label, thumb, fp.source_tool, fp.source_platform, fp.confidence);
  }
  for (const fp of id?.search_findings ?? []) {
    if (fp.field !== 'video') continue;
    const ref = splitRef(fp.value);
    const thumb = (id?.search_findings ?? []).find((s) => s.field === 'thumbnail_url' && s.source_ref === ref.url)?.value;
    addVideo(ref.label, ref.url || fp.value, thumb, fp.source_tool, fp.source_platform, fp.confidence);
  }
  for (const pp of unified ?? []) {
    for (const fp of pp.extracted_fields ?? []) {
      if (fp.field !== 'video' && fp.field !== 'media_video') continue;
      const ref = splitRef(fp.value);
      const thumb = pp.extracted_fields?.find((x) => x.field === 'thumbnail_url')?.value;
      addVideo(ref.label || `${pp.platform} video`, ref.url || ref.label, thumb, fp.source_tool, pp.platform, fp.confidence);
    }
  }
  return items;
}

export function buildOsintIntelSections(
  result: InvestigationResult | null,
  identity?: IdentityProfile,
  seedQuery = '',
): OsintIntelSection[] {
  if (!result) return [];

  const id = identity ?? result.identity_profile;
  const unified = result.evidence_extraction?.unified_profile;
  const googleIntel = itemsFromGoogleSearchIntel(result);
  const leadItems: OsintIntelItem[] = (result.evidence_extraction?.lead_visuals ?? []).map((lead, i) => ({
    id: `lead_${lead.lead_id}_${i}`,
    label: lead.lead_type,
    value: lead.title,
    confidence: lead.confidence,
    source: lead.visual_source,
    sourcePlatform: lead.source_domain,
    url: lead.url,
    imageUrl: lead.thumbnail_url || lead.image_url || undefined,
    thumbnailUrl: lead.thumbnail_url || lead.image_url || undefined,
    provenance: lead.snippet,
    renderAs: lead.image_url || lead.thumbnail_url ? 'image' : undefined,
  }));

  const photos = dedupeItems([
    ...leadItems.filter((i) => i.imageUrl),
    ...googleIntel.photos,
    ...collectPhotos(result, id, unified, seedQuery),
  ]);

  const usernames = dedupeItems([
    ...(id?.usernames ?? unified?.usernames ?? []).map((fp, i) => ({ ...fpToItem(fp, 'username', i), label: 'Username' })),
    ...(id?.aliases ?? unified?.aliases ?? []).map((fp, i) => ({ ...fpToItem(fp, 'alias', i), label: 'Alias' })),
    ...(id?.bios ?? unified?.bios ?? []).map((fp, i) => ({
      ...fpToItem(fp, 'bio', i),
      label: 'Bio',
      renderAs: undefined,
      provenance: fp.value,
    })),
  ]);

  const emails = dedupeItems([...(id?.emails ?? unified?.emails ?? []).map((fp, i) => fpToItem(fp, `email_${i}`, i))]);

  const domains = dedupeItems([
    ...(id?.domains ?? []).map((fp, i) => fpToItem(fp, `domain_${i}`, i)),
    ...(result.fusion?.deduplicated_entities ?? [])
      .filter((e) => e.type === 'domain')
      .map((e) => ({
        id: e.entity_id || e.value,
        label: 'Domain',
        value: e.value,
        confidence: e.fusion_score,
        source: (e.sources ?? []).join(', '),
      })),
  ]);

  const organizations = dedupeItems([
    ...(id?.organizations ?? unified?.organizations ?? []).map((fp, i) => ({
      ...fpToItem(fp, `org_${i}`, i),
      label: fp.field === 'company' || fp.field === 'organization' ? 'Employer' : fp.field.replace(/_/g, ' '),
    })),
    ...(id?.companies ?? []).map((fp, i) => ({ ...fpToItem(fp, `co_${i}`, i), label: 'Employer' })),
    ...(id?.schools ?? []).map((fp, i) => ({ ...fpToItem(fp, `school_${i}`, i), label: 'School' })),
    ...(id?.search_findings ?? [])
      .filter((fp) => fp.field === 'occupation')
      .map((fp, i) => ({ ...fpToItem(fp, `occ_${i}`, i), label: 'Occupation' })),
    ...googleIntel.colleges,
    ...googleIntel.employers,
  ]);

  const projects = dedupeItems((id?.projects ?? []).map((fp, i) => fpToItem(fp, `proj_${i}`, i)));

  const events = dedupeItems([
    ...leadItems.filter((i) => ['hackathon', 'event', 'achievement'].includes(i.label)),
    ...googleIntel.events,
    ...(id?.events ?? []).filter((fp) => fp.field === 'event').map((fp, i) => {
      const ref = splitRef(fp.value);
      return {
        id: `event_${i}`,
        label: 'Event',
        value: ref.label,
        confidence: fp.confidence,
        source: fp.source_tool,
        sourcePlatform: fp.source_platform,
        url: ref.url || undefined,
        provenance: fp.extraction_strategy,
      };
    }),
    ...(id?.search_findings ?? []).filter((fp) => fp.field === 'event').map((fp, i) => fpToItem(fp, `sevent_${i}`, i)),
    ...(id?.achievements ?? []).map((fp, i) => ({ ...fpToItem(fp, `ach_${i}`, i), label: 'Achievement' })),
    ...dorkContentItems(result, new Set(['event']), 'Event'),
  ]);

  const articles = dedupeItems([
    ...leadItems.filter((i) => ['news', 'article', 'college'].includes(i.label)),
    ...googleIntel.social,
    ...(id?.publications ?? []).map((fp, i) => {
      const ref = splitRef(fp.value);
      return {
        id: `pub_${i}`,
        label: ref.label || fp.field,
        value: ref.url || ref.label,
        confidence: fp.confidence,
        source: fp.source_tool,
        url: ref.url || undefined,
        provenance: fp.extraction_strategy,
      };
    }),
    ...(id?.search_findings ?? [])
      .filter((fp) => ['article', 'news', 'blog', 'publication'].includes(fp.field))
      .map((fp, i) => {
        const ref = splitRef(fp.value);
        return {
          id: `article_${i}`,
          label: ref.label || fp.field,
          value: ref.url || ref.label,
          confidence: fp.confidence,
          source: fp.source_tool,
          url: ref.url || undefined,
          provenance: fp.extraction_strategy,
        };
      }),
    ...dorkContentItems(result, new Set(['article']), 'Article'),
  ]);

  const videos = dedupeItems(videosFromProfile(id, unified?.platform_profiles));

  const appearances = dedupeItems((id?.appearances ?? []).map((fp, i) => {
    const ref = splitRef(fp.value);
    return {
      id: `app_${i}`,
      label: ref.label || 'Appearance',
      value: ref.url || ref.label,
      confidence: fp.confidence,
      source: fp.source_tool,
      url: ref.url || undefined,
      provenance: fp.extraction_strategy,
    };
  }));

  const relationships = dedupeItems(
    (id?.relationships ?? []).map((rel, i) => ({
      id: `rel_${i}`,
      label: rel.relation_type,
      value: rel.target,
      confidence: rel.confidence,
      source: rel.source_ref,
    })),
  );

  const sectionDefs: OsintIntelSection[] = [
    { id: 'photos', title: 'Photos', icon: '📷', description: 'Profile photos, hackathon images, and web discoveries', items: photos },
    { id: 'accounts', title: 'Accounts', icon: '👤', description: 'Verified platforms with bios and avatars', items: accountsFromResult(result, id) },
    { id: 'usernames', title: 'Usernames & Bios', icon: '🪪', description: 'Handles, aliases, and profile bios', items: usernames },
    { id: 'emails', title: 'Emails', icon: '📧', items: emails },
    { id: 'domains', title: 'Domains', icon: '🌐', items: domains },
    { id: 'organizations', title: 'Organizations & Employment', icon: '🏢', description: 'Employers, colleges, and affiliations', items: organizations },
    { id: 'projects', title: 'Projects', icon: '📂', items: projects },
    { id: 'events', title: 'Events & Hackathons', icon: '📅', description: 'Competitions, conferences, and public events', items: events },
    { id: 'articles', title: 'Articles & Blogs', icon: '📰', description: 'News, blogs, and published posts with source links', items: articles },
    { id: 'videos', title: 'Videos', icon: '▶️', description: 'Video links with preview thumbnails when available', items: videos },
    { id: 'appearances', title: 'Public Appearances', icon: '🎤', items: appearances },
    { id: 'relationships', title: 'Relationships', icon: '↔️', items: relationships },
  ];

  return sectionDefs.filter((s) => s.items.length > 0 || ['photos', 'accounts', 'events', 'articles'].includes(s.id));
}
