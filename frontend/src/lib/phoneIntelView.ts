import type { InvestigationResult } from '../types';
import { platformLabel } from './platformUtils';

const PHONE_RE = /^\+?[\d\s().-]{8,20}$/;

export interface PhoneMetadata {
  phone: string;
  carrier?: string;
  location?: string;
  countryCode?: string;
  countryName?: string;
  valid?: boolean;
  lineType?: string;
  phoneinfogaApi?: boolean;
  numverifyOk?: boolean;
  webHits?: number;
}

function pickText(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (value == null) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return undefined;
}

export interface PhoneRegistration {
  id: string;
  platform: string;
  platformLabel: string;
  phone: string;
  source: string;
  confidence?: string;
  url?: string;
  method?: string;
  status: 'registered' | 'linked' | 'possible';
}

export interface PhoneSocialLink {
  id: string;
  platform: string;
  platformLabel: string;
  url?: string;
  title?: string;
  snippet?: string;
  status: string;
  confidence?: string;
  source: string;
}

export interface PhoneWebHit {
  id: string;
  title: string;
  url: string;
  snippet: string;
  platform: string;
  category: string;
  source: string;
}

export interface PhoneToolStatus {
  tool: string;
  label: string;
  status: string;
  detail?: string;
}

function toolRows(result: InvestigationResult | null, tool: string): Record<string, unknown>[] {
  const tr = result?.tool_results?.find((t) => t.tool === tool);
  if (!tr?.data?.length) return [];
  return tr.data.filter((row) => (row as Record<string, unknown>).platform !== '_scan_summary') as Record<string, unknown>[];
}

function summaryRow(result: InvestigationResult | null, tool: string): Record<string, unknown> | undefined {
  const tr = result?.tool_results?.find((t) => t.tool === tool);
  return tr?.data?.find((row) => (row as Record<string, unknown>).platform === '_scan_summary') as Record<string, unknown> | undefined;
}

export function parseSeedPhone(query: string): string | undefined {
  for (const token of query.split(/[|,]/)) {
    const t = token.trim();
    const digits = t.replace(/[^\d+]/g, '');
    if (digits.length >= 8 && PHONE_RE.test(t)) return t;
    if (digits.length >= 10 && !t.includes('@')) return t.startsWith('+') ? t : `+${digits}`;
  }
  return undefined;
}

export function hasPhoneIntel(result: InvestigationResult | null, query: string): boolean {
  if (parseSeedPhone(query)) return true;
  if (!result) return false;
  if (result.feature === 'infra_intel') return true;
  return result.tool_results?.some((t) =>
    ['phoneinfoga', 'phone_social_intel'].includes(t.tool),
  ) ?? false;
}

export function phoneMetadataFromResult(result: InvestigationResult | null, query: string): PhoneMetadata | null {
  if (!result) return null;
  const seed = parseSeedPhone(query) ?? parseSeedPhone(result.query);
  const socialSummary = summaryRow(result, 'phone_social_intel');
  const piSummary = summaryRow(result, 'phoneinfoga');
  const summary = socialSummary ?? piSummary;
  if (!summary && !seed) return null;

  const nvRow = [...toolRows(result, 'phoneinfoga'), ...toolRows(result, 'phone_social_intel')]
    .find((r) => r.platform === 'numverify' || r.check_type === 'carrier_lookup');

  return {
    phone: pickText(summary?.phone, seed, result.query) ?? '',
    carrier: pickText(summary?.carrier, nvRow?.carrier),
    location: pickText(summary?.location, nvRow?.location),
    countryCode: pickText(summary?.country_code, nvRow?.country_code),
    countryName: pickText(summary?.country_name, nvRow?.country_name),
    valid: summary?.valid === true || nvRow?.status === 'valid'
      ? true
      : summary?.valid === false || nvRow?.status === 'invalid'
        ? false
        : undefined,
    lineType: pickText(summary?.line_type, nvRow?.line_type),
    phoneinfogaApi: summary?.phoneinfoga_api === true || piSummary?.phoneinfoga_api === true,
    numverifyOk: summary?.numverify_ok === true || piSummary?.numverify_ok === true,
    webHits: Number(summary?.web_hits ?? piSummary?.web_hits ?? 0) || undefined,
  };
}

export function phoneRegistrationsFromResult(result: InvestigationResult | null, seedPhone?: string): PhoneRegistration[] {
  if (!result) return [];
  const seed = seedPhone ?? parseSeedPhone(result.query);
  const seen = new Set<string>();
  const out: PhoneRegistration[] = [];

  const add = (reg: PhoneRegistration) => {
    const key = `${reg.platform}:${reg.phone}:${reg.status}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(reg);
  };

  for (const tool of ['phone_social_intel', 'phoneinfoga']) {
    for (const item of toolRows(result, tool)) {
      const platform = String(item.platform ?? 'unknown');
      if (platform === 'numverify' || platform === 'phone_metadata' || platform === 'phone_local') continue;
      const registered = item.status === 'registered' || item.registered === true;
      const linked = item.status === 'linked' || item.verified === true;
      if (!registered && !linked) continue;
      const phone = String(item.phone ?? seed ?? '');
      add({
        id: `${tool}_${platform}_${phone}_${item.status}`,
        platform,
        platformLabel: platformLabel(platform),
        phone,
        source: String(item.source_tool ?? tool),
        confidence: String(item.confidence ?? ''),
        url: pickText(item.url, item.profile_hint),
        method: item.method ? String(item.method) : undefined,
        status: registered ? 'registered' : 'linked',
      });
    }
  }

  return out.sort((a, b) => (a.status === 'registered' ? -1 : 0) - (b.status === 'registered' ? -1 : 0));
}

export function phoneSocialLinksFromResult(result: InvestigationResult | null): PhoneSocialLink[] {
  if (!result) return [];
  const out: PhoneSocialLink[] = [];
  const seen = new Set<string>();

  for (const tool of ['phone_social_intel', 'phoneinfoga']) {
    for (const item of toolRows(result, tool)) {
      const checkType = String(item.check_type ?? '');
      if (!['phone_social_match', 'profile_resolution', 'platform_registration'].includes(checkType)
        && item.status !== 'linked' && item.status !== 'possible_match') {
        continue;
      }
      const platform = String(item.platform ?? 'unknown');
      const url = item.url ? String(item.url) : undefined;
      const key = `${platform}:${url ?? item.title ?? ''}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        id: `${tool}_${key}`,
        platform,
        platformLabel: platformLabel(platform),
        url,
        title: item.title ? String(item.title) : undefined,
        snippet: item.snippet ? String(item.snippet) : undefined,
        status: String(item.status ?? 'linked'),
        confidence: item.confidence ? String(item.confidence) : undefined,
        source: String(item.source_tool ?? tool),
      });
    }
  }
  return out;
}

export function phoneWebHitsFromResult(result: InvestigationResult | null): PhoneWebHit[] {
  if (!result) return [];
  const out: PhoneWebHit[] = [];
  const seen = new Set<string>();

  for (const tool of ['phoneinfoga', 'phone_social_intel']) {
    for (const item of toolRows(result, tool)) {
      const url = item.url ? String(item.url) : '';
      if (!url.startsWith('http')) continue;
      const checkType = String(item.check_type ?? '');
      if (!['google_dork', 'cli_web_search', 'google_cse', 'web_search'].includes(checkType)
        && item.platform !== 'phone_search') {
        continue;
      }
      if (seen.has(url)) continue;
      seen.add(url);
      out.push({
        id: `${tool}_${url}`,
        title: String(item.title ?? url),
        url,
        snippet: String(item.snippet ?? ''),
        platform: String(item.platform ?? 'web'),
        category: String(item.dork_category ?? checkType ?? 'web'),
        source: String(item.source_tool ?? tool),
      });
    }
  }
  return out.slice(0, 40);
}

export function phoneNumbersFromToolResults(result: InvestigationResult | null): {
  id: string;
  label: string;
  value: string;
  confidence?: number;
  source?: string;
  sourcePlatform?: string;
  provenance?: string;
  metadata?: Record<string, unknown>;
}[] {
  if (!result) return [];
  const seen = new Set<string>();
  const out: {
    id: string;
    label: string;
    value: string;
    confidence?: number;
    source?: string;
    sourcePlatform?: string;
    provenance?: string;
    metadata?: Record<string, unknown>;
  }[] = [];

  for (const tool of ['phone_social_intel', 'phoneinfoga']) {
    const summary = summaryRow(result, tool);
    const phone = summary?.phone ? String(summary.phone) : undefined;
    if (phone && !seen.has(phone)) {
      seen.add(phone);
      out.push({
        id: `phone_${tool}_${phone}`,
        label: 'phone',
        value: phone,
        confidence: 0.9,
        source: tool,
        sourcePlatform: 'phone_intel',
        provenance: [summary?.carrier, summary?.location].filter(Boolean).join(' · ') || tool,
        metadata: summary,
      });
    }
    for (const item of toolRows(result, tool)) {
      const p = item.phone ? String(item.phone) : '';
      if (!p || seen.has(p)) continue;
      seen.add(p);
      out.push({
        id: `phone_row_${tool}_${p}`,
        label: 'phone',
        value: p,
        confidence: 0.85,
        source: tool,
        sourcePlatform: String(item.platform ?? 'phone_intel'),
        provenance: String(item.carrier ?? item.location ?? tool),
        metadata: item,
      });
    }
  }
  return out;
}

const TOOL_LABELS: Record<string, string> = {
  phoneinfoga: 'PhoneInfoga',
  phone_social_intel: 'Phone OSINT',
  google_dorking: 'Google dorking',
};

export function phoneToolStatuses(result: InvestigationResult | null): PhoneToolStatus[] {
  if (!result) return [];
  const out: PhoneToolStatus[] = [];

  for (const tool of ['phone_social_intel', 'phoneinfoga', 'google_dorking']) {
    const tr = result.tool_results?.find((t) => t.tool === tool);
    if (!tr) continue;
    const summary = summaryRow(result, tool);
    const rows = toolRows(result, tool);
    let status = tr.success ? 'completed' : 'failed';
    let detail: string | undefined;

    if (tool === 'phone_social_intel') {
      const reg = phoneRegistrationsFromResult(result).filter((r) => r.source === 'phone_social_intel' || r.source === 'ignorant');
      const links = phoneSocialLinksFromResult(result);
      detail = `${Number(summary?.confirmed_links ?? summary?.registered_accounts_found ?? reg.length)} social link(s) · ${links.length} profile hit(s)`;
      if (tr.error) detail = tr.error;
    } else if (tool === 'phoneinfoga') {
      const meta = phoneMetadataFromResult(result, result.query);
      const regs = phoneRegistrationsFromResult(result, parseSeedPhone(result.query));
      const piRegs = regs.filter((r) => r.source === 'phoneinfoga' || r.source === 'ignorant');
      if (meta) {
        const parts = [
          piRegs.length > 0 && `${piRegs.length} platform registration(s)`,
          meta.carrier && `Carrier: ${meta.carrier}`,
          meta.location && `Location: ${meta.location}`,
          meta.lineType && `${meta.lineType} line`,
          meta.countryName || (meta.countryCode ? `+${meta.countryCode}` : ''),
          meta.numverifyOk ? 'Numverify ✓' : '',
          meta.valid ? 'Valid number' : meta.valid === false ? 'Invalid' : '',
        ].filter(Boolean);
        detail = parts.join(' · ') || `${rows.length} finding(s)`;
      } else {
        detail = `${rows.length} finding(s)`;
      }
      if (tr.error) detail = tr.error;
    } else if (tool === 'google_dorking') {
      detail = `${rows.length} SERP hit(s)`;
    }

    out.push({
      tool,
      label: TOOL_LABELS[tool] ?? tool,
      status,
      detail,
    });
  }
  return out;
}
