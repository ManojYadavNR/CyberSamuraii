import type { FieldProvenance, IdentityProfile, InvestigationResult, InvestigationTreeNode, UnifiedPersonProfile } from '../types';
import { isDisplayableEmailField, isVerifiedPlatformProfile } from './accountVerification';
import { emailRegistrationsFromResult, parseSeedEmail } from './emailIntelView';
import { phoneNumbersFromToolResults } from './phoneIntelView';
import { seedInDorkContext } from './googleDorkView';
import { getVerifiedPlatformDetails } from './platformAccountView';
import { formatTargetLabel, isLocalPath } from './pathDisplay';

export interface IntelligenceItem {
  id: string;
  label: string;
  value: string;
  confidence?: number;
  source?: string;
  sourcePlatform?: string;
  provenance?: string;
  metadata?: Record<string, unknown>;
}

export interface IntelligenceSection {
  id: string;
  title: string;
  icon: string;
  description: string;
  items: IntelligenceItem[];
}

function fpToItem(fp: FieldProvenance, prefix: string, index = 0): IntelligenceItem {
  const valueKey = fp.value.slice(0, 48).replace(/\s+/g, '_');
  const sourceKey = fp.source_tool ? `_${fp.source_tool}` : '';
  return {
    id: `${prefix}_${fp.field}_${valueKey}${sourceKey}_${index}`,
    label: fp.field,
    value: fp.value,
    confidence: fp.confidence,
    source: fp.source_tool,
    sourcePlatform: fp.source_platform,
    provenance: fp.extraction_strategy || fp.source_ref,
  };
}

function itemsFromFieldList(items: FieldProvenance[] | undefined, prefix: string): IntelligenceItem[] {
  const seen = new Set<string>();
  const out: IntelligenceItem[] = [];
  for (let i = 0; i < (items ?? []).length; i++) {
    const fp = items![i];
    const item = fpToItem(fp, prefix, i);
    let id = item.id;
    while (seen.has(id)) {
      id = `${item.id}_dup${seen.size}`;
      item.id = id;
    }
    seen.add(id);
    out.push(item);
  }
  return out;
}

function accountsFromResult(
  result: InvestigationResult,
  _identity: IdentityProfile | undefined,
  confirmedOnly = true,
): IntelligenceItem[] {
  if (!confirmedOnly) return [];
  return getVerifiedPlatformDetails(result).map((detail) => ({
    id: detail.entityId,
    label: detail.displayName || detail.handle || detail.platformLabel,
    value: detail.url || `${detail.platform}/${detail.handle}`,
    confidence: detail.fusionScore,
    source: detail.sources.join(', '),
    sourcePlatform: detail.platform,
    provenance: detail.groups.flatMap((g) => g.items.map((i) => i.value)).slice(0, 4).join(' · ') || 'Verified platform',
    metadata: {
      verified: true,
      corroboration: 'confirmed',
      renderAs: detail.avatarUrl && isPlausibleProfilePhoto(detail.avatarUrl) ? 'image' : undefined,
    },
  }));
}

function googleDorkResults(result: InvestigationResult, seedQuery = ''): IntelligenceItem[] {
  return (result.fusion?.deduplicated_entities ?? [])
    .filter((ent) => ent.type === 'document')
    .filter((ent) => (ent.metadata as Record<string, unknown>)?.check_type === 'google_dork')
    .filter((ent) => !seedQuery || isDorkDisplayable((ent.metadata ?? {}) as Record<string, unknown>, seedQuery))
    .map((ent) => {
      const meta = (ent.metadata ?? {}) as Record<string, unknown>;
      return {
        id: ent.entity_id || ent.value,
        label: String(meta.title || meta.dork_query || 'Google result'),
        value: String(meta.url || ent.value),
        confidence: ent.fusion_score,
        source: 'google_dorking',
        sourcePlatform: String(meta.platform || meta.display_link || ''),
        provenance: String(meta.snippet || meta.dork_query || ''),
        metadata: meta,
      };
    });
}

function isDorkDisplayable(meta: Record<string, unknown>, seedQuery: string): boolean {
  return seedInDorkContext(meta, seedQuery);
}

const BRANDING_IMAGE_HINTS = [
  '/favicon', 'favicon.', '/logo', '/logos/', '/icon-', '/icons/', '/apple-touch-icon',
  '/sprite', '/badge', '/brand/', '/static/images/logo', '/assets/logo', '/default-avatar',
  'opengraph-image', 'og-image', '/share-image', 'placeholder', '1x1.', 'pixel.',
];

function isImageUrl(value: string): boolean {
  if (!value.startsWith('http')) return false;
  const low = value.toLowerCase();
  if (/\.(jpg|jpeg|png|webp|gif|bmp)(\?.*)?$/i.test(low)) return true;
  if (['/avatar', '/photo', '/image', '/img/', 'profile_pic', 'display_url'].some((h) => low.includes(h))) return true;
  return false;
}

function isPlausibleProfilePhoto(value: string): boolean {
  if (value.startsWith('/api/intel/screenshots/')) return true;
  if (!value.startsWith('http')) return false;
  const low = value.toLowerCase();
  if (BRANDING_IMAGE_HINTS.some((hint) => low.includes(hint))) return false;
  if (low.endsWith('.svg') || low.endsWith('.ico')) return false;
  if (/\/\d{1,2}x\d{1,2}\./.test(low)) return false;
  return isImageUrl(value);
}

function domainFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function searchFindingAttributed(fp: FieldProvenance, seedQuery: string): boolean {
  if (!seedQuery.trim()) return true;
  const url = fp.source_ref || (fp.value.includes('|') ? fp.value.split('|', 2)[1]?.trim() : fp.value);
  const title = fp.value.includes('|') ? fp.value.split('|', 2)[0]?.trim() : '';
  const snippet = fp.field === 'search_snippet' ? fp.value : '';
  return seedInDorkContext({ url, title, snippet }, seedQuery);
}

function searchIntelligenceItems(
  identity: IdentityProfile | undefined,
  unified: UnifiedPersonProfile | undefined,
  result: InvestigationResult,
  seedQuery: string,
): IntelligenceItem[] {
  const fromProfile = [
    ...(identity?.search_findings ?? []),
    ...(unified?.search_findings ?? []),
  ];
  const seen = new Set<string>();
  const items: IntelligenceItem[] = [];

  const add = (fp: FieldProvenance, prefix: string) => {
    const key = `${fp.field}:${fp.value.toLowerCase()}`;
    if (seen.has(key)) return;
    seen.add(key);
    const item = fpToItem(fp, prefix);
    if (fp.field === 'search_hit' && fp.value.includes('|')) {
      const [title, url] = fp.value.split('|', 2);
      item.label = title.trim() || 'Search result';
      item.value = url.trim() || fp.value;
      item.provenance = fp.source_ref || fp.extraction_strategy;
    }
    if (fp.field === 'search_snippet') {
      item.label = 'Snippet';
      item.metadata = { ...(item.metadata || {}), renderAs: 'prose' };
    }
    if (fp.field === 'image' && (fp.value.startsWith('/api/intel/') || fp.value.startsWith('http'))) {
      item.metadata = { ...(item.metadata || {}), renderAs: 'image', avatar_url: fp.value };
    }
    if (fp.field === 'search_category') {
      item.label = 'Category';
    }
    items.push(item);
  };

  for (const fp of fromProfile) {
    if (!searchFindingAttributed(fp, seedQuery)) continue;
    add(fp, 'search');
  }

  for (const ent of result.fusion?.deduplicated_entities ?? []) {
    const meta = (ent.metadata ?? {}) as Record<string, unknown>;
    if (meta.check_type !== 'google_dork') continue;
    if (seedQuery && !isDorkDisplayable(meta, seedQuery)) continue;
    const url = String(meta.url || ent.value);
    const title = String(meta.title || meta.dork_query || 'Search result');
    const snippet = String(meta.snippet || '');
    const key = `search_hit:${title}|${url}`.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({
      id: ent.entity_id || url,
      label: title,
      value: url,
      confidence: ent.fusion_score,
      source: 'google_dorking',
      sourcePlatform: String(meta.platform || meta.display_link || 'search'),
      provenance: snippet || String(meta.dork_category || ''),
      metadata: meta,
    });
    if (snippet) {
      items.push({
        id: `snippet_${ent.entity_id || url}`,
        label: 'Snippet',
        value: snippet,
        confidence: ent.fusion_score,
        source: 'google_dorking',
        provenance: title,
      });
    }
  }

  return items.sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
}


function dorkHighlightsForLinks(result: InvestigationResult, seedQuery: string): IntelligenceItem[] {
  const identity = result.identity_profile;
  const unified = result.evidence_extraction?.unified_profile;
  return searchIntelligenceItems(identity, unified, result, seedQuery)
    .filter((item) => item.label !== 'Snippet' && item.label !== 'Category')
    .map((item) => ({
      ...item,
      id: `dork_link_${item.id}`,
      label: item.label || 'Web discovery',
      provenance: item.provenance || 'search_intelligence',
    }));
}

function allProfilePhotos(
  result: InvestigationResult,
  identity: IdentityProfile | undefined,
  unified: UnifiedPersonProfile | undefined,
  seedQuery: string,
): IntelligenceItem[] {
  const items: IntelligenceItem[] = [];
  const seen = new Set<string>();

  const addPhoto = (url: string, source: string, platform?: string, confidence?: number) => {
    if (!url || seen.has(url)) return;
    const displayable = isPlausibleProfilePhoto(url) || url.startsWith('/api/intel/screenshots/');
    if (!displayable) return;
    seen.add(url);
    items.push({
      id: `photo_${url}`,
      label: source || 'profile_photo',
      value: url,
      confidence,
      source,
      sourcePlatform: platform || domainFromUrl(url),
      provenance: url.startsWith('/api/intel/') ? 'page screenshot' : 'verified platform profile image',
      metadata: { renderAs: 'image', avatar_url: url },
    });
  };

  for (const pp of identity?.platform_profiles ?? unified?.platform_profiles ?? []) {
    if (!isVerifiedPlatformProfile(pp)) continue;
    const platform = pp.platform || 'platform';
    if (pp.avatar_url) {
      addPhoto(pp.avatar_url, pp.display_name || pp.handle || platform, platform, pp.fusion_score);
    }
    for (const fp of pp.extracted_fields ?? []) {
      if ((fp.field === 'avatar_url' || fp.field === 'image') && fp.value) {
        addPhoto(fp.value, fp.field, platform, fp.confidence);
      }
    }
  }

  for (const lead of result.evidence_extraction?.lead_visuals ?? []) {
    if (seedQuery && lead.lead_type !== 'profile' && !seedInDorkContext(
      { url: lead.url, title: lead.title, snippet: lead.snippet },
      seedQuery,
    )) continue;
    const img = lead.thumbnail_url || lead.image_url;
    if (img) {
      addPhoto(img, lead.title || lead.lead_type, lead.source_domain, lead.confidence);
    }
  }

  for (const fp of identity?.photos ?? unified?.images ?? []) {
    addPhoto(fp.value, fp.source_tool || 'enrichment', fp.source_platform, fp.confidence);
  }
  for (const fp of identity?.search_findings ?? unified?.search_findings ?? []) {
    if (seedQuery && !searchFindingAttributed(fp, seedQuery)) continue;
    if (fp.field === 'avatar_url' || fp.field === 'image') {
      addPhoto(fp.value, fp.source_tool || 'search', fp.source_platform, fp.confidence);
    }
  }
  // platform_profiles handled above — skip duplicate platformSeen pass
  for (const ent of result.fusion?.deduplicated_entities ?? []) {
    const meta = (ent.metadata ?? {}) as Record<string, unknown>;
    if (meta.check_type === 'google_dork' && meta.dork_category === 'media_images') {
      if (seedQuery && !isDorkDisplayable(meta, seedQuery)) continue;
      const url = String(meta.url || ent.value);
      addPhoto(url, 'google_dorking', String(meta.platform || ''));
    }
  }
  return items;
}

function mediaVideos(
  identity: IdentityProfile | undefined,
  unified: UnifiedPersonProfile | undefined,
  _result: InvestigationResult,
  seedQuery = '',
): IntelligenceItem[] {
  const fromEvents = (identity?.events ?? [])
    .filter((e) => e.field === 'media_video' || e.field === 'video')
    .map((fp) => {
      const [title, url] = fp.value.includes('|') ? fp.value.split('|', 2) : [fp.value, fp.value];
      return {
        id: `media_${url}`,
        label: title.trim() || 'Video',
        value: url.trim(),
        confidence: fp.confidence,
        source: fp.source_tool || 'google_dorking',
        sourcePlatform: fp.source_platform,
        provenance: fp.extraction_strategy,
        metadata: { renderAs: 'video' },
      };
    });

  const fromSearch = (identity?.search_findings ?? [])
    .filter((fp) => fp.field === 'video')
    .filter((fp) => !seedQuery || searchFindingAttributed(fp, seedQuery))
    .map((fp) => fpToItem(fp, 'media'));

  const fromProfiles = (identity?.platform_profiles ?? unified?.platform_profiles ?? [])
    .filter((pp) => isVerifiedPlatformProfile(pp))
    .flatMap((pp) => (pp.extracted_fields ?? [])
      .filter((fp) => fp.field === 'video' || fp.field === 'media_video')
      .map((fp) => {
        const [title, url] = fp.value.includes('|') ? fp.value.split('|', 2) : [fp.value, fp.value];
        return {
          id: `media_${pp.platform}_${url}`,
          label: title.trim() || `${pp.platform} video`,
          value: url.trim(),
          confidence: fp.confidence,
          source: fp.source_tool || (pp.sources ?? []).join(', '),
          sourcePlatform: pp.platform,
          provenance: fp.extraction_strategy,
          metadata: { renderAs: 'video' },
        };
      }));

  const seen = new Set<string>();
  return [...fromEvents, ...fromSearch, ...fromProfiles].filter((item) => {
    if (seen.has(item.value)) return false;
    seen.add(item.value);
    return true;
  });
}

function publicationItems(identity: IdentityProfile | undefined, seedQuery = ''): IntelligenceItem[] {
  const items = itemsFromFieldList(identity?.publications, 'publication');
  const fromSearch = (identity?.search_findings ?? [])
    .filter((fp) => fp.field === 'news' || fp.field === 'article' || fp.field === 'blog')
    .filter((fp) => !seedQuery || searchFindingAttributed(fp, seedQuery))
    .map((fp) => {
      const item = fpToItem(fp, fp.field);
      if (fp.value.includes('|')) {
        const [title, url] = fp.value.split('|', 2);
        item.label = title.trim() || fp.field;
        item.value = url.trim() || fp.value;
      }
      return item;
    });
  const seen = new Set<string>();
  return [...items, ...fromSearch].filter((item) => {
    const key = item.value.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
function eventsAndAppearances(identity: IdentityProfile | undefined): IntelligenceItem[] {
  return (identity?.events ?? [])
    .filter((e) => e.field !== 'media_video' && e.field !== 'video')
    .map((fp) => fpToItem(fp, 'event'));
}

function confirmedEmails(
  identity: IdentityProfile | undefined,
  unified?: UnifiedPersonProfile,
  result?: InvestigationResult,
  query = '',
): IntelligenceItem[] {
  const emails = identity?.emails ?? unified?.emails ?? [];
  const items = itemsFromFieldList(emails.filter(isDisplayableEmailField), 'email');
  const seed = parseSeedEmail(query || result?.query || '');
  if (seed && !items.some((i) => i.value.toLowerCase() === seed)) {
    items.unshift({
      id: `seed_email_${seed}`,
      label: 'email',
      value: seed,
      confidence: 0.95,
      source: 'user_input',
      provenance: 'Investigation seed',
    });
  }
  if (result) {
    for (const reg of emailRegistrationsFromResult(result, seed)) {
      if (items.some((i) => i.value === reg.email && i.sourcePlatform === reg.platform)) continue;
      items.push({
        id: reg.id,
        label: 'email_registration',
        value: reg.email,
        confidence: reg.confidence,
        source: reg.source,
        sourcePlatform: reg.platformLabel,
        provenance: `Registered on ${reg.platformLabel}`,
        metadata: { platform: reg.platform, registration: true },
      });
    }
  }
  return items;
}

function attributedPhones(result: InvestigationResult, identity: IdentityProfile | undefined): IntelligenceItem[] {
  const fromIdentity = itemsFromFieldList(identity?.phones, 'phone');
  const fromFusion = (result.fusion?.deduplicated_entities ?? [])
    .filter((ent) => ent.type === 'phone')
    .map((ent) => ({
      id: ent.entity_id || ent.value,
      label: 'phone',
      value: ent.value,
      confidence: ent.fusion_score,
      source: (ent.sources ?? []).join(', '),
      sourcePlatform: String((ent.metadata as Record<string, unknown>)?.platform || 'phone_intel'),
      provenance: String((ent.metadata as Record<string, unknown>)?.carrier || (ent.metadata as Record<string, unknown>)?.location || 'phone discovery'),
      metadata: ent.metadata,
    }));
  const fromTools = phoneNumbersFromToolResults(result);
  const seen = new Set(fromIdentity.map((i) => i.value));
  const merged = [...fromIdentity];
  for (const item of [...fromFusion, ...fromTools]) {
    if (seen.has(item.value)) continue;
    seen.add(item.value);
    merged.push(item);
  }
  return merged;
}

function evidenceFromFusion(result: InvestigationResult): IntelligenceItem[] {
  return (result.fusion?.deduplicated_entities ?? []).map((ent) => ({
    id: ent.entity_id || ent.value,
    label: ent.type,
    value: ent.canonical_value || ent.value,
    confidence: ent.fusion_score,
    source: (ent.sources ?? []).join(', '),
    provenance: String((ent.metadata as Record<string, unknown>)?.extracted_intelligence ? 'enriched' : ''),
    metadata: ent.metadata,
  }));
}

function pathsFromGraph(result: InvestigationResult): IntelligenceItem[] {
  const paths = result.graph?.reasoning_paths ?? [];
  return paths.map((p) => ({
    id: p.path_id,
    label: 'Reasoning path',
    value: p.summary,
    confidence: p.confidence,
    provenance: p.relations.join(' → '),
    metadata: { labels: p.labels },
  }));
}

function leadsFromDiscovery(result: InvestigationResult): IntelligenceItem[] {
  const leads = result.discovery?.pending_leads ?? [];
  return leads.map((lead) => ({
    id: lead.lead_id || `lead_${lead.query}`,
    label: `${lead.lead_type} · ${lead.feature}`,
    value: lead.query,
    confidence: lead.priority,
    provenance: lead.reason || `depth ${lead.depth}`,
    metadata: {
      lead_type: lead.lead_type,
      feature: lead.feature,
      priority: lead.priority,
      source_entity_type: lead.source_entity_type,
    },
  }));
}

function relationshipsFromIdentity(identity: IdentityProfile | undefined): IntelligenceItem[] {
  return (identity?.relationships ?? []).map((rel, i) => ({
    id: `rel_${i}`,
    label: rel.relation_type,
    value: rel.target,
    confidence: rel.confidence,
    provenance: rel.source_ref,
  }));
}

function supportingEvidenceFromIdentity(identity: IdentityProfile | undefined): IntelligenceItem[] {
  return (identity?.supporting_evidence ?? []).map((ev, i) => ({
    id: `sup_${i}`,
    label: ev.field,
    value: ev.value,
    confidence: ev.confidence,
    source: ev.source_tool,
    sourcePlatform: ev.source_platform,
    provenance: ev.extraction_strategy || ev.source_ref,
  }));
}

function engineStatusFromResult(result: InvestigationResult): IntelligenceItem[] {
  const items: IntelligenceItem[] = [];
  const ex = result.evidence_extraction;
  const id = result.identity_profile;
  if (ex) {
    if (ex.entities_enriched) items.push({ id: 'enriched', label: 'Entities enriched', value: String(ex.entities_enriched) });
    for (const strat of ex.extraction_strategies ?? []) {
      items.push({ id: `strat_${strat}`, label: 'Extraction strategy', value: strat });
    }
  }
  if (id?.enrichment_passes) {
    items.push({ id: 'passes', label: 'Enrichment passes', value: String(id.enrichment_passes) });
  }
  if (result.graph?.graph_engine_version) {
    items.push({ id: 'graph_ver', label: 'Graph engine', value: result.graph.graph_engine_version });
  }
  if (result.discovery?.enabled) {
    items.push({
      id: 'pivot',
      label: 'Auto-pivot engine',
      value: `${result.discovery.total_hops} hop(s), ${result.discovery.total_leads_discovered} lead(s)`,
      provenance: result.discovery.stop_reason.replace(/_/g, ' '),
    });
  }
  return items;
}

function timelineFromIdentity(profile: IdentityProfile | undefined): IntelligenceItem[] {
  return (profile?.timeline ?? []).map((ev, i) => ({
    id: `tl_${i}`,
    label: ev.event_type,
    value: ev.description,
    confidence: ev.confidence,
    source: ev.source ?? undefined,
    provenance: ev.timestamp,
  }));
}

function treeToItems(nodes: InvestigationTreeNode[] | undefined): IntelligenceItem[] {
  return (nodes ?? [])
    .filter((n) => n.node_type !== 'seed')
    .map((n) => ({
      id: n.node_id,
      label: n.node_type,
      value: n.value || n.label,
      provenance: String((n.provenance as Record<string, unknown>)?.expansion_strategy ?? n.provenance?.reason ?? ''),
      metadata: { depth: n.depth, status: n.status },
    }));
}

export function buildIntelligenceSections(result: InvestigationResult | null, query: string): IntelligenceSection[] {
  if (!result) return [];

  const identity = result.identity_profile;
  const unified = result.evidence_extraction?.unified_profile;
  const profile = identity ?? unified;

  const sections: IntelligenceSection[] = [];

  const identityItems: IntelligenceItem[] = [];
  if (profile) {
    if ('primary_name' in profile && profile.primary_name && !isLocalPath(profile.primary_name)) {
      identityItems.push({ id: 'primary_name', label: 'Name', value: profile.primary_name, confidence: 'confidence_score' in profile ? profile.confidence_score : undefined });
    } else if ('primary_display_name' in profile && profile.primary_display_name && !isLocalPath(profile.primary_display_name)) {
      identityItems.push({ id: 'primary_name', label: 'Name', value: profile.primary_display_name });
    }
    const bio = 'primary_bio' in profile ? profile.primary_bio : undefined;
    const loc = 'primary_location' in profile ? profile.primary_location : undefined;
    if (bio) identityItems.push({ id: 'bio', label: 'Bio', value: bio });
    if (loc) identityItems.push({ id: 'location', label: 'Location', value: loc });
    if ('confidence_score' in profile) {
      identityItems.push({ id: 'confidence', label: 'Identity confidence', value: `${(profile.confidence_score * 100).toFixed(0)}%`, confidence: profile.confidence_score });
    }
    if ('total_evidence_fields' in profile) {
      identityItems.push({ id: 'fields', label: 'Evidence fields', value: String(profile.total_evidence_fields) });
    }
    if ('enrichment_passes' in profile && profile.enrichment_passes) {
      identityItems.push({ id: 'passes', label: 'Enrichment passes', value: String(profile.enrichment_passes) });
    }
  }
  if (!identityItems.length && query) {
    identityItems.push({ id: 'seed', label: 'Investigation target', value: query });
  }
  sections.push({ id: 'identity', title: 'Identity Profile', icon: '👤', description: 'Who is this person?', items: identityItems });

  const sectionDefs: Array<{ id: string; title: string; icon: string; description: string; getItems: () => IntelligenceItem[] }> = [
    {
      id: 'photos',
      title: 'Photos',
      icon: '🖼',
      description: 'Profile photos from verified accounts, search hits, and image discoveries',
      getItems: () => allProfilePhotos(result, identity, unified, query),
    },
    {
      id: 'accounts',
      title: 'Accounts',
      icon: '🔗',
      description: 'Verified accounts with deep-enriched bios, emails, and profile images',
      getItems: () => accountsFromResult(result, identity, true),
    },
    {
      id: 'contacts',
      title: 'Contacts',
      icon: '📇',
      description: 'Emails and phones discovered via username search, email intel, and attributed dork hits',
      getItems: () => [
        ...confirmedEmails(identity, unified, result, query),
        ...attributedPhones(result, identity),
      ],
    },
    {
      id: 'identifiers',
      title: 'Identifiers',
      icon: '🪪',
      description: 'Usernames, aliases, domains, and social handles',
      getItems: () => [
        ...itemsFromFieldList(identity?.usernames ?? unified?.usernames, 'username'),
        ...itemsFromFieldList(identity?.aliases ?? unified?.aliases, 'alias'),
        ...itemsFromFieldList(identity?.domains, 'domain'),
        ...itemsFromFieldList(identity?.social_accounts, 'social'),
      ],
    },
    {
      id: 'search_intelligence',
      title: 'Search Intelligence',
      icon: '🔍',
      description: 'Google dork and search engine findings — profiles, news, blogs, articles, events, and mentions',
      getItems: () => searchIntelligenceItems(identity, unified, result, query),
    },
    {
      id: 'links',
      title: 'Web Presence',
      icon: '🌐',
      description: 'Websites, public profiles, and correlated search discoveries',
      getItems: () => [
        ...itemsFromFieldList(identity?.websites ?? unified?.websites, 'website'),
        ...itemsFromFieldList(identity?.public_links ?? unified?.public_links, 'link'),
        ...dorkHighlightsForLinks(result, query),
      ],
    },
    {
      id: 'media',
      title: 'Media',
      icon: '▶️',
      description: 'Videos and media references from search and profile enrichment',
      getItems: () => mediaVideos(identity, unified, result, query),
    },
    {
      id: 'google_dorks',
      title: 'Google Dork Results',
      icon: '🔍',
      description: 'Public web pages discovered via Google dork queries',
      getItems: () => googleDorkResults(result, query),
    },
    {
      id: 'organizations',
      title: 'Organizations',
      icon: '🏢',
      description: 'Companies, schools, and affiliations',
      getItems: () => [
        ...itemsFromFieldList(identity?.organizations ?? unified?.organizations, 'org'),
        ...itemsFromFieldList(identity?.companies, 'company'),
        ...itemsFromFieldList(identity?.schools, 'school'),
      ],
    },
    {
      id: 'projects',
      title: 'Projects',
      icon: '📂',
      description: 'Discovered projects and work',
      getItems: () => itemsFromFieldList(identity?.projects, 'project'),
    },
    {
      id: 'achievements',
      title: 'Achievements',
      icon: '🏆',
      description: 'Achievements and accomplishments',
      getItems: () => itemsFromFieldList(identity?.achievements, 'achievement'),
    },
    {
      id: 'events',
      title: 'Events & Appearances',
      icon: '📅',
      description: 'Conferences, meetups, workshops, competitions, and any public event tied to this username',
      getItems: () => [
        ...eventsAndAppearances(identity),
        ...itemsFromFieldList(identity?.appearances, 'appearance'),
      ],
    },
    {
      id: 'publications',
      title: 'News, Blogs & Articles',
      icon: '📰',
      description: 'News coverage, blog posts, and articles mentioning this username',
      getItems: () => publicationItems(identity, query),
    },
    {
      id: 'timeline',
      title: 'Timeline',
      icon: '⏱',
      description: 'How intelligence was discovered over time',
      getItems: () => [
        ...timelineFromIdentity(identity),
        ...treeToItems(result.discovery?.investigation_tree?.nodes ?? identity?.investigation_tree?.nodes),
      ],
    },
    {
      id: 'evidence',
      title: 'Evidence',
      icon: '📋',
      description: 'All fused entities with provenance',
      getItems: () => evidenceFromFusion(result),
    },
    {
      id: 'relationships',
      title: 'Relationships',
      icon: '↔️',
      description: 'Evidence-backed connections between entities',
      getItems: () => relationshipsFromIdentity(identity),
    },
    {
      id: 'supporting',
      title: 'Supporting Evidence',
      icon: '🧾',
      description: 'Additional corroborating intelligence fields',
      getItems: () => supportingEvidenceFromIdentity(identity),
    },
    {
      id: 'engines',
      title: 'Engine Status',
      icon: '⚙️',
      description: 'Universal extraction, auto-pivot, and graph pipeline',
      getItems: () => engineStatusFromResult(result),
    },
    {
      id: 'paths',
      title: 'Investigation Paths',
      icon: '🧭',
      description: 'Reasoning chains through discovered intelligence',
      getItems: () => pathsFromGraph(result),
    },
    {
      id: 'leads',
      title: 'Recommended Leads',
      icon: '🔍',
      description: 'Pending leads worth investigating next',
      getItems: () => leadsFromDiscovery(result),
    },
  ];

  for (const def of sectionDefs) {
    const items = def.getItems();
    if (items.length > 0) {
      sections.push({ id: def.id, title: def.title, icon: def.icon, description: def.description, items });
    }
  }

  return sections;
}

export function investigationBrief(result: InvestigationResult | null, query: string): {
  who: string;
  what: string;
  why: string;
  how: string;
  next: string;
} {
  const sections = buildIntelligenceSections(result, query);
  const identity = result?.identity_profile;
  const faceDetected = (result?.image_correlation?.face_matches?.length ?? 0) > 0;
  const who = (identity?.primary_name && !isLocalPath(identity.primary_name))
    ? identity.primary_name
    : formatTargetLabel(query, faceDetected) || 'Unknown subject';
  const what = sections.filter((s) => s.id !== 'identity' && s.id !== 'leads').map((s) => `${s.title} (${s.items.length})`).join(' · ') || 'No intelligence yet';
  const why = identity ? `${(identity.confidence_score * 100).toFixed(0)}% identity confidence from ${identity.total_evidence_fields} evidence-backed fields` : 'Awaiting evidence';
  const how = result?.discovery?.investigation_tree
    ? `${result.discovery.total_hops} auto-pivot hop(s), ${result.discovery.investigation_tree.total_evidence_nodes} evidence nodes`
    : result?.evidence_extraction
      ? `${result.evidence_extraction.fields_extracted} fields extracted from ${result.evidence_extraction.platforms_analyzed} platform(s)`
      : 'Seed investigation only';
  const leads = sections.find((s) => s.id === 'leads');
  const next = leads?.items.length ? leads.items.slice(0, 3).map((l) => l.value).join(', ') : 'No pending leads — investigation complete or limits reached';
  return { who, what, why, how, next };
}
