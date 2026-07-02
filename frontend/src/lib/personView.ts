import type { InvestigationResult } from '../types';
import { verifiedPlatformCount } from './profileStats';
import { displayableEmails, emailRegistrationsFromResult, parseSeedEmail } from './emailIntelView';
import type { IntelligenceItem, IntelligenceSection } from './intelligenceView';
import { buildIntelligenceSections, investigationBrief } from './intelligenceView';
import { buildImageInvestigationSections, imageInvestigationBrief } from './imageInvestigationView';

export type SectionTier = 'person' | 'technical';

export interface PersonSection extends IntelligenceSection {
  tier: SectionTier;
}

const TECHNICAL_IDS = new Set([
  'engines',
  'evidence',
  'paths',
  'supporting',
  'face_matches',
  'confidence_breakdown',
  'hash_signatures',
  'media',
]);

const PERSON_ORDER = [
  'identity',
  'verified_platforms',
  'detected_faces',
  'identity_candidates',
  'person_profile',
  'accounts',
  'google_dorks',
  'search_intelligence',
  'photos',
  'emails',
  'phones',
  'websites',
  'organizations',
  'projects',
  'events',
  'timeline',
  'leads',
  'reverse_matches',
  'evidence_chains',
  'relationships',
  'identifiers',
  'contacts',
  'links',
  'achievements',
  'publications',
];

function splitContacts(section: IntelligenceSection | undefined): PersonSection[] {
  if (!section?.items.length) return [];
  const emails: IntelligenceItem[] = [];
  const phones: IntelligenceItem[] = [];
  for (const item of section.items) {
    const label = item.label.toLowerCase();
    if (label.includes('phone') || item.metadata?.type === 'phone') {
      phones.push(item);
    } else {
      emails.push(item);
    }
  }
  const out: PersonSection[] = [];
  if (emails.length) {
    out.push({
      id: 'emails',
      title: 'Emails',
      icon: '✉️',
      description: 'Email addresses discovered across investigations',
      items: emails,
      tier: 'person',
    });
  }
  if (phones.length) {
    out.push({
      id: 'phones',
      title: 'Phones',
      icon: '📞',
      description: 'Phone numbers linked to this person',
      items: phones,
      tier: 'person',
    });
  }
  return out;
}

function personProfileSection(result: InvestigationResult): PersonSection | null {
  const identity = result.identity_profile;
  const unified = result.evidence_extraction?.unified_profile;
  const profile = identity ?? unified;
  if (!profile) return null;

  const items: IntelligenceItem[] = [];
  const bio = 'primary_bio' in profile ? profile.primary_bio : undefined;
  const loc = 'primary_location' in profile ? profile.primary_location : undefined;
  if (bio) items.push({ id: 'bio', label: 'Biography', value: bio });
  if (loc) items.push({ id: 'location', label: 'Location', value: loc });

  const schools = 'schools' in profile ? profile.schools : [];
  for (const s of schools ?? []) {
    items.push({ id: `school_${s.value}`, label: 'Education', value: s.value, provenance: s.source_platform });
  }
  const companies = 'companies' in profile ? profile.companies : [];
  for (const c of companies ?? []) {
    items.push({ id: `company_${c.value}`, label: 'Employment', value: c.value, provenance: c.source_platform });
  }
  const orgs = 'organizations' in profile ? profile.organizations : [];
  for (const o of orgs ?? []) {
    items.push({ id: `org_${o.value}`, label: 'Organization', value: o.value, provenance: o.source_platform });
  }
  const projects = 'projects' in profile ? profile.projects : [];
  for (const p of projects ?? []) {
    items.push({ id: `proj_${p.value}`, label: 'Project', value: p.value, provenance: p.source_platform });
  }
  const websites = 'websites' in profile ? profile.websites : [];
  for (const w of websites ?? []) {
    items.push({ id: `web_${w.value}`, label: 'Website', value: w.value, provenance: w.source_platform });
  }

  if (!items.length) return null;
  return {
    id: 'person_profile',
    title: 'Person Profile',
    icon: '📋',
    description: 'Biography, locations, education, employment, and affiliations',
    items,
    tier: 'person',
  };
}

export function buildPersonSections(
  result: InvestigationResult | null,
  query: string,
  queryType: string,
): { person: PersonSection[]; technical: PersonSection[] } {
  if (!result) return { person: [], technical: [] };

  const raw = queryType === 'image'
    ? buildImageInvestigationSections(result, query)
    : buildIntelligenceSections(result, query);

  const byId = Object.fromEntries(raw.map((s) => [s.id, s]));
  const contactsSplit = splitContacts(byId.contacts);
  const profileSection = personProfileSection(result);

  const mapped: PersonSection[] = raw.map((s) => ({
    ...s,
    tier: TECHNICAL_IDS.has(s.id) ? 'technical' as const : 'person' as const,
  }));

  if (profileSection) mapped.push(profileSection);
  mapped.push(...contactsSplit);

  // Rename person-facing sections
  for (const s of mapped) {
    if (s.id === 'identity') {
      s.title = 'Identity Summary';
      s.description = 'Who is this person?';
    }
    if (s.id === 'accounts') s.description = 'Social and platform accounts grouped by confidence';
    if (s.id === 'reverse_matches') {
      s.title = 'Visual Matches';
      s.description = 'Where this photo appears on the public web';
    }
    if (s.id === 'leads') s.description = 'Leads queued for automatic expansion';
  }

  const person: PersonSection[] = [];
  const technical: PersonSection[] = [];

  const seen = new Set<string>();
  for (const id of PERSON_ORDER) {
    for (const s of mapped) {
      if (s.id === id && s.items.length > 0 && !seen.has(s.id)) {
        seen.add(s.id);
        if (s.tier === 'technical') technical.push(s);
        else person.push(s);
      }
    }
  }
  for (const s of mapped) {
    if (!seen.has(s.id) && s.items.length > 0) {
      seen.add(s.id);
      if (s.tier === 'technical') technical.push(s);
      else person.push(s);
    }
  }

  return { person, technical };
}

export function personInvestigationBrief(
  result: InvestigationResult | null,
  query: string,
  queryType: string,
) {
  if (queryType === 'image') return imageInvestigationBrief(result, query);
  return investigationBrief(result, query);
}

export interface IdentityStats {
  accounts: number;
  emails: number;
  phones: number;
  domains: number;
  organizations: number;
  photos: number;
  confidence: number;
  hops: number;
  leads: number;
}

export function identityStats(result: InvestigationResult | null, query = ''): IdentityStats {
  const identity = result?.identity_profile;
  const clusters = result?.correlation?.clusters ?? [];
  let accounts = 0;
  for (const c of clusters) accounts += c.linked_accounts?.length ?? 0;

  const emailSet = new Set(displayableEmails(result, query || result?.query || ''));
  for (const reg of emailRegistrationsFromResult(result, parseSeedEmail(query || result?.query || ''))) {
    emailSet.add(reg.email.toLowerCase());
  }

  return {
    accounts: verifiedPlatformCount(result) || accounts || identity?.verified_platform_count || 0,
    emails: emailSet.size || (identity?.emails?.length ?? 0),
    phones: identity?.phones?.length ?? 0,
    domains: identity?.domains?.length ?? 0,
    organizations: identity?.organizations?.length ?? 0,
    photos: identity?.photos?.length ?? 0,
    confidence: (identity?.confidence_score ?? 0) * 100,
    hops: result?.discovery?.total_hops ?? 0,
    leads: result?.discovery?.total_leads_discovered ?? 0,
  };
}
