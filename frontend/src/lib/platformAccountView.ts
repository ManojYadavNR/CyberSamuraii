import type { FieldProvenance, InvestigationResult, LinkedAccount, PlatformProfile } from '../types';
import {
  isVerifiedLinkedAccount,
  isVerifiedPlatformProfile,
  normalizeAccountHandle,
} from './accountVerification';

export interface PlatformAttribute {
  label: string;
  value: string;
  confidence?: number;
  strategy?: string;
}

export interface PlatformAttributeGroup {
  id: string;
  label: string;
  icon: string;
  items: PlatformAttribute[];
}

export interface VerifiedPlatformDetail {
  entityId: string;
  platform: string;
  platformLabel: string;
  handle: string;
  url?: string;
  displayName?: string;
  avatarUrl?: string;
  verified: boolean;
  fusionScore: number;
  sources: string[];
  enrichmentSource?: string;
  groups: PlatformAttributeGroup[];
  visuals: PlatformVisual[];
  fieldCount: number;
}

const GROUP_DEFS: { id: string; label: string; icon: string; fields: Set<string> }[] = [
  { id: 'identity', label: 'Identity', icon: '🪪', fields: new Set(['display_name', 'username', 'alias']) },
  { id: 'contact', label: 'Contact', icon: '📬', fields: new Set(['email', 'phone', 'website']) },
  { id: 'profile', label: 'Profile', icon: '📝', fields: new Set(['bio', 'location', 'organization', 'school']) },
  { id: 'stats', label: 'Platform Stats', icon: '📊', fields: new Set(['profile_stat']) },
  { id: 'media', label: 'Photos & Videos', icon: '🎬', fields: new Set(['avatar_url', 'image', 'video', 'media_video', 'thumbnail_url']) },
  { id: 'activity', label: 'Activity', icon: '⚡', fields: new Set(['recent_post', 'project', 'achievement']) },
  { id: 'links', label: 'Links', icon: '🔗', fields: new Set(['public_link']) },
];

const FIELD_LABELS: Record<string, string> = {
  display_name: 'Display name',
  username: 'Username',
  alias: 'Alias',
  email: 'Email',
  phone: 'Phone',
  website: 'Website',
  bio: 'Bio',
  location: 'Location',
  organization: 'Organization',
  school: 'Education',
  profile_stat: 'Stat',
  avatar_url: 'Profile photo',
  image: 'Image',
  video: 'Video',
  media_video: 'Media',
  recent_post: 'Recent post',
  project: 'Project',
  achievement: 'Achievement',
  public_link: 'Link',
  thumbnail_url: 'Video preview',
};

export interface PlatformVisual {
  type: 'avatar' | 'image' | 'video';
  url: string;
  thumbnailUrl: string;
  title: string;
}

import { platformLabel } from './platformUtils';

function collectVisuals(pp: PlatformProfile): PlatformVisual[] {
  const visuals: PlatformVisual[] = [];
  const seen = new Set<string>();

  const add = (type: PlatformVisual['type'], url: string, thumbnailUrl: string, title: string) => {
    const key = `${type}:${thumbnailUrl || url}`;
    if ((!url.startsWith('http') && !url.startsWith('/api/intel/')) || seen.has(key)) return;
    seen.add(key);
    visuals.push({ type, url, thumbnailUrl: thumbnailUrl || url, title });
  };

  const rawAssets = pp.public_metadata?.visual_assets;
  if (Array.isArray(rawAssets)) {
    for (const asset of rawAssets) {
      if (!asset || typeof asset !== 'object') continue;
      const a = asset as Record<string, unknown>;
      const type = String(a.type || 'image') as PlatformVisual['type'];
      const url = String(a.url || '');
      const thumb = String(a.thumbnail_url || url);
      const title = String(a.title || type);
      if (url.startsWith('http')) add(type, url, thumb, title);
    }
  }

  if (pp.avatar_url && (pp.avatar_url.startsWith('http') || pp.avatar_url.startsWith('/api/intel/'))) {
    add('avatar', pp.avatar_url, pp.avatar_url, 'Profile photo');
  }

  for (const fp of pp.extracted_fields ?? []) {
    if (fp.field === 'avatar_url' && (fp.value.startsWith('http') || fp.value.startsWith('/api/intel/'))) {
      add('avatar', fp.value, fp.value, 'Profile photo');
    }
    if (fp.field === 'image' && (fp.value.startsWith('http') || fp.value.startsWith('/api/intel/'))) {
      add('image', fp.value, fp.value, 'Image');
    }
    if (fp.field === 'thumbnail_url' && fp.value.startsWith('http')) {
      const video = (pp.extracted_fields ?? []).find((x) => x.field === 'media_video');
      const videoUrl = video?.value.includes('|') ? video.value.split('|', 2)[1] : video?.value;
      add('video', videoUrl || fp.value, fp.value, 'Video preview');
    }
    if (fp.field === 'media_video' && fp.value.includes('|')) {
      const [title, url] = fp.value.split('|', 2);
      const thumb = (pp.extracted_fields ?? []).find((x) => x.field === 'thumbnail_url')?.value;
      add('video', url.trim(), thumb?.startsWith('http') ? thumb : url.trim(), title.trim() || 'Video');
    }
  }

  return visuals;
}

function formatStatValue(raw: string): string {
  const colon = raw.indexOf(':');
  if (colon === -1) return raw;
  const key = raw.slice(0, colon).trim().replace(/_/g, ' ');
  const val = raw.slice(colon + 1).trim();
  return `${key.charAt(0).toUpperCase() + key.slice(1)}: ${val}`;
}

function formatMediaValue(field: string, value: string): string {
  if (field === 'media_video' && value.includes('|')) {
    const [title, url] = value.split('|', 2);
    return title.trim() || url.trim();
  }
  return value;
}

function mediaUrl(field: string, value: string): string | undefined {
  if (field === 'media_video' && value.includes('|')) {
    return value.split('|', 2)[1]?.trim();
  }
  if (value.startsWith('http')) return value;
  return undefined;
}

function addUnique(groupMap: Map<string, PlatformAttribute[]>, groupId: string, item: PlatformAttribute) {
  const list = groupMap.get(groupId) ?? [];
  const key = `${item.label}:${item.value}`.toLowerCase();
  if (list.some((x) => `${x.label}:${x.value}`.toLowerCase() === key)) return;
  list.push(item);
  groupMap.set(groupId, list);
}

function statsFromMetadata(meta: Record<string, unknown> | undefined): PlatformAttribute[] {
  if (!meta) return [];
  const nested = meta.public_metadata;
  const stats = (typeof nested === 'object' && nested !== null ? nested : meta) as Record<string, unknown>;
  const out: PlatformAttribute[] = [];
  for (const key of ['followers', 'following', 'posts', 'videos', 'subscribers', 'public_repos', 'repos']) {
    const val = stats[key];
    if (val != null && String(val).trim()) {
      out.push({
        label: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
        value: String(val),
        strategy: 'platform_metadata',
      });
    }
  }
  return out;
}

export function buildPlatformDetail(pp: PlatformProfile): VerifiedPlatformDetail {
  const groupMap = new Map<string, PlatformAttribute[]>();

  const pushField = (field: string, value: string, confidence?: number, strategy?: string) => {
    const group = GROUP_DEFS.find((g) => g.fields.has(field));
    if (!group) return;
    addUnique(groupMap, group.id, {
      label: FIELD_LABELS[field] ?? field,
      value: field === 'profile_stat' ? formatStatValue(value) : formatMediaValue(field, value),
      confidence,
      strategy,
    });
  };

  if (pp.display_name) pushField('display_name', pp.display_name, pp.fusion_score);
  if (pp.handle) pushField('username', pp.handle, pp.fusion_score);
  for (const u of pp.usernames ?? []) pushField('username', u);
  for (const a of pp.aliases ?? []) pushField('alias', a);
  if (pp.email) pushField('email', pp.email, 0.85);
  if (pp.website) pushField('website', pp.website);
  if (pp.bio) pushField('bio', pp.bio);
  if (pp.location) pushField('location', pp.location);
  for (const org of pp.organizations ?? []) pushField('organization', org);
  for (const link of pp.public_links ?? []) {
    if (link !== pp.url) pushField('public_link', link);
  }

  for (const fp of pp.extracted_fields ?? []) {
    if (fp.field === 'school' || fp.field === 'achievement') continue;
    pushField(fp.field, fp.value, fp.confidence, fp.extraction_strategy);
  }

  for (const stat of statsFromMetadata(pp.public_metadata)) {
    addUnique(groupMap, 'stats', stat);
  }

  const enrichmentSource = typeof pp.public_metadata?.enrichment_source === 'string'
    ? pp.public_metadata.enrichment_source
    : undefined;

  const groups: PlatformAttributeGroup[] = GROUP_DEFS
    .map((def) => ({
      id: def.id,
      label: def.label,
      icon: def.icon,
      items: groupMap.get(def.id) ?? [],
    }))
    .filter((g) => g.items.length > 0);

  const fieldCount = groups.reduce((n, g) => n + g.items.length, 0);
  const visuals = collectVisuals(pp);
  const avatarUrl = pp.avatar_url || visuals.find((v) => v.type === 'avatar')?.thumbnailUrl;

  return {
    entityId: pp.entity_id,
    platform: pp.platform,
    platformLabel: platformLabel(pp.platform),
    handle: normalizeAccountHandle(pp.handle || ''),
    url: pp.url,
    displayName: pp.display_name,
    avatarUrl,
    verified: !!pp.verified,
    fusionScore: pp.fusion_score ?? 0,
    sources: pp.sources ?? [],
    enrichmentSource,
    groups,
    visuals,
    fieldCount,
  };
}

function linkedAccountToProfile(acct: LinkedAccount): PlatformProfile {
  const intel = acct.extracted_intelligence ?? {};
  return {
    entity_id: acct.entity_id || `${acct.platform}:${acct.handle}`,
    platform: acct.platform,
    handle: acct.handle,
    url: acct.url,
    verified: !!acct.verified,
    sources: acct.sources ?? [],
    fusion_score: acct.fusion_score,
    display_name: acct.display_name,
    bio: acct.bio,
    location: acct.location,
    website: acct.website,
    email: acct.email,
    avatar_url: acct.avatar_url,
    organizations: acct.organizations ?? [],
    public_metadata: intel as Record<string, unknown>,
    extracted_fields: [],
  };
}

export {
  formatPlatformHandle,
  isDisplayableEmailField,
  isEmailRegistrationHandle,
  isPlausibleAccountHandle as isPlausibleVerifiedHandle,
  isVerifiedLinkedAccount,
  isVerifiedPlatformProfile,
} from './accountVerification';

export function isLiveConfirmedProfile(pp: PlatformProfile): boolean {
  return isVerifiedPlatformProfile(pp);
}

/** @deprecated use isLiveConfirmedProfile — kept for callers */
export function isMaigretBackedProfile(pp: PlatformProfile): boolean {
  return isLiveConfirmedProfile(pp);
}

export function getVerifiedPlatformDetails(result: InvestigationResult | null): VerifiedPlatformDetail[] {
  const identity = result?.identity_profile;
  const unified = result?.evidence_extraction?.unified_profile;
  const profiles: PlatformProfile[] = [
    ...(identity?.platform_profiles ?? unified?.platform_profiles ?? []),
  ];
  const seen = new Set(profiles.map((p) => `${p.platform}:${p.handle}`.toLowerCase()));

  for (const cluster of result?.correlation?.clusters ?? []) {
    for (const acct of cluster.linked_accounts ?? []) {
      if (!isVerifiedLinkedAccount(acct)) continue;
      const key = `${acct.platform}:${acct.handle}`.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      profiles.push(linkedAccountToProfile(acct));
    }
  }

  return profiles
    .filter((pp) => isVerifiedPlatformProfile(pp))
    .map(buildPlatformDetail)
    .filter((detail, index, list) => list.findIndex((d) => d.entityId === detail.entityId) === index)
    .sort((a, b) => b.fusionScore - a.fusionScore || b.fieldCount - a.fieldCount);
}

export function mediaLinkFromAttribute(field: string, value: string): string | undefined {
  return mediaUrl(field, value);
}

export function isImageField(field: string): boolean {
  return field === 'avatar_url' || field === 'image';
}

export function provenanceFromFields(fields: FieldProvenance[] | undefined): string {
  const tools = new Set((fields ?? []).map((f) => f.source_tool).filter(Boolean));
  return Array.from(tools).join(', ');
}

export interface PlatformPhotoCard {
  id: string;
  platform: string;
  platformLabel: string;
  handle: string;
  url?: string;
  avatarUrl?: string;
  sources: string[];
  fusionScore: number;
}

export function collectVerifiedPlatformPhotos(result: InvestigationResult | null): PlatformPhotoCard[] {
  const cards = new Map<string, PlatformPhotoCard>();

  const upsert = (card: PlatformPhotoCard) => {
    const key = `${card.platform}:${card.handle}`.toLowerCase();
    const existing = cards.get(key);
    if (!existing) {
      cards.set(key, card);
      return;
    }
    if (!existing.avatarUrl && card.avatarUrl) existing.avatarUrl = card.avatarUrl;
    if (card.fusionScore > existing.fusionScore) {
      existing.fusionScore = card.fusionScore;
    }
    existing.sources = Array.from(new Set([...existing.sources, ...card.sources]));
  };

  for (const detail of getVerifiedPlatformDetails(result)) {
    upsert({
      id: detail.entityId,
      platform: detail.platform,
      platformLabel: detail.platformLabel,
      handle: detail.handle,
      url: detail.url,
      avatarUrl: detail.avatarUrl || detail.visuals.find((v) => v.type === 'avatar')?.thumbnailUrl,
      sources: detail.sources,
      fusionScore: detail.fusionScore,
    });
  }

  return Array.from(cards.values()).sort(
    (a, b) => b.fusionScore - a.fusionScore || Number(Boolean(b.avatarUrl)) - Number(Boolean(a.avatarUrl)),
  );
}
