import type { InvestigationResult } from '../types';
import { isDisplayableEmailField } from './accountVerification';
import { investigationSeedTokens, seedInDorkContext } from './googleDorkView';
import { getVerifiedPlatformDetails, isEmailRegistrationHandle } from './platformAccountView';
import { platformFromUrl, platformLabel } from './platformUtils';

const EMAIL_RE = /^[\w.+-]+@[\w-]+\.[\w.-]+$/i;

export interface EmailRegistration {
  id: string;
  platform: string;
  platformLabel: string;
  email: string;
  source: string;
  confidence?: number;
  url?: string;
}

export interface HoleheScanSummary {
  sitesChecked?: number;
  sitesFound?: number;
  verified?: number;
  email?: string;
}

export interface EmailToolStatus {
  tool: string;
  label: string;
  status: string;
  detail?: string;
}

export interface EmailDorkHit {
  id: string;
  title: string;
  url: string;
  snippet: string;
  platform: string;
  category: string;
}

export interface GhuntSummary {
  found: boolean;
  note?: string;
  metadata?: Record<string, unknown>;
}

export function parseSeedEmail(query: string): string | undefined {
  for (const token of investigationSeedTokens(query)) {
    if (EMAIL_RE.test(token.trim())) return token.trim().toLowerCase();
  }
  return undefined;
}

export function holeheScanSummary(result: InvestigationResult | null): HoleheScanSummary | null {
  const tr = result?.tool_results?.find((t) => t.tool === 'holehe');
  if (!tr?.data?.length) return null;
  const summary = tr.data.find((row) => (row as Record<string, unknown>).platform === '_scan_summary') as
    | Record<string, unknown>
    | undefined;
  const registered = tr.data.filter((row) => {
    const r = row as Record<string, unknown>;
    return r.platform !== '_scan_summary' && (r.status === 'registered' || r.registered === true);
  }).length;
  const scan = (result?.scan_summary?.holehe ?? summary) as Record<string, unknown> | undefined;
  return {
    sitesChecked: Number(scan?.sites_checked ?? summary?.sites_checked ?? 0) || undefined,
    sitesFound: Number(scan?.sites_found ?? summary?.sites_found ?? registered) || registered || undefined,
    verified: registered || Number(scan?.verified ?? 0) || undefined,
    email: String(result?.scan_summary?.email ?? scan?.email ?? parseSeedEmail(result?.query ?? '') ?? ''),
  };
}

export function emailRegistrationsFromResult(result: InvestigationResult | null, seedEmail?: string): EmailRegistration[] {
  if (!result) return [];
  const seed = seedEmail ?? parseSeedEmail(result.query);
  const seen = new Set<string>();
  const out: EmailRegistration[] = [];

  const add = (reg: EmailRegistration) => {
    const key = `${reg.platform}:${reg.email}`.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(reg);
  };

  for (const detail of getVerifiedPlatformDetails(result)) {
    if (!isEmailRegistrationHandle(detail.handle)) continue;
    if (seed && detail.handle.toLowerCase() !== seed.toLowerCase()) continue;
    add({
      id: detail.entityId,
      platform: detail.platform,
      platformLabel: detail.platformLabel,
      email: detail.handle,
      source: detail.sources.join(', ') || 'holehe',
      confidence: detail.fusionScore,
      url: detail.url,
    });
  }

  for (const finding of result.confirmed_findings ?? []) {
    if (finding.type !== 'account_registration' || !finding.platform) continue;
    const email = String(finding.email ?? seed ?? '').toLowerCase();
    if (!email || !EMAIL_RE.test(email)) continue;
    if (seed && email !== seed.toLowerCase()) continue;
    add({
      id: `cf_${finding.platform}_${email}`,
      platform: String(finding.platform),
      platformLabel: platformLabel(String(finding.platform)),
      email,
      source: String(finding.source_tool ?? 'holehe'),
      confidence: 0.88,
    });
  }

  for (const row of result.tool_results?.find((t) => t.tool === 'holehe')?.data ?? []) {
    const item = row as Record<string, unknown>;
    if (item.platform === '_scan_summary') continue;
    if (item.status !== 'registered' && item.registered !== true) continue;
    const email = String(item.email ?? seed ?? '').toLowerCase();
    if (!email || !EMAIL_RE.test(email)) continue;
    if (seed && email !== seed.toLowerCase()) continue;
    add({
      id: `holehe_${item.platform}_${email}`,
      platform: String(item.platform ?? 'unknown'),
      platformLabel: platformLabel(String(item.platform ?? '')),
      email,
      source: 'holehe',
      confidence: 0.85,
    });
  }

  return out.sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
}

export function displayableEmails(result: InvestigationResult | null, query: string): string[] {
  const identity = result?.identity_profile;
  const unified = result?.evidence_extraction?.unified_profile;
  const fromProfile = [
    ...(identity?.emails ?? []),
    ...(unified?.emails ?? []),
  ]
    .filter(isDisplayableEmailField)
    .map((e) => e.value.toLowerCase());
  const seed = parseSeedEmail(query);
  const all = seed ? [seed, ...fromProfile] : fromProfile;
  return [...new Set(all)];
}

export function hasEmailIntel(result: InvestigationResult | null, query: string): boolean {
  if (!result) return false;
  if (parseSeedEmail(query)) return true;
  if (result.feature === 'email_intel' || result.feature === 'multi') return true;
  if ((result.confirmed_findings?.length ?? 0) > 0) return true;
  if (result.scan_summary && Object.keys(result.scan_summary).length > 0) return true;
  return result.tool_results?.some((t) =>
    ['holehe', 'gravatar', 'ghunt', 'theharvester', 'google_dorking'].includes(t.tool),
  ) ?? false;
}

const TOOL_LABELS: Record<string, string> = {
  holehe: 'Holehe',
  gravatar: 'Gravatar',
  ghunt: 'GHunt',
  theharvester: 'theHarvester',
  google_dorking: 'Google dorking',
  spiderfoot: 'SpiderFoot',
};

export function emailToolStatuses(result: InvestigationResult | null): EmailToolStatus[] {
  if (!result) return [];
  const summary = result.scan_summary ?? {};
  const out: EmailToolStatus[] = [];

  for (const tool of ['holehe', 'gravatar', 'ghunt', 'theharvester', 'google_dorking', 'spiderfoot']) {
    const tr = result.tool_results?.find((t) => t.tool === tool);
    const row = summary[tool] as Record<string, unknown> | undefined;
    if (!tr && !row) continue;

    let status = String(row?.status ?? (tr?.success ? 'completed' : 'failed'));
    let detail: string | undefined;

    if (tool === 'holehe') {
      const h = holeheScanSummary(result);
      detail = h?.sitesChecked
        ? `${h.sitesChecked} sites checked · ${h.verified ?? 0} registration(s)`
        : undefined;
    } else if (tool === 'gravatar') {
      const found = row?.found === true || (result.public_profile_data ?? []).some((p) => p.source === 'gravatar');
      status = found ? 'found' : 'not_found';
      detail = found ? 'Public Gravatar profile linked' : 'No Gravatar profile';
    } else if (tool === 'theharvester') {
      if (status === 'skipped') {
        detail = String(row?.note ?? 'Skipped for consumer mail (Gmail/Yahoo) — use org domain');
      } else {
        detail = `${Number(row?.items ?? 0)} harvested item(s)`;
      }
    } else if (tool === 'google_dorking') {
      detail = `${Number(row?.hits ?? 0)} web mention(s) from ${Number(row?.dorks_run ?? 0)} dork(s)`;
    } else if (tool === 'ghunt') {
      const items = Number(row?.items ?? 0);
      status = items > 0 ? 'found' : 'not_found';
      detail = items > 0 ? 'Google account metadata found' : String(row?.note ?? 'No Google profile linked');
    } else if (tool === 'spiderfoot') {
      detail = String(row?.note ?? `${Number(row?.items ?? 0)} item(s)`);
    } else if (tr?.error) {
      detail = tr.error;
    }

    out.push({ tool, label: TOOL_LABELS[tool] ?? tool, status, detail });
  }

  return out;
}

export function ghuntFromResult(result: InvestigationResult | null): GhuntSummary | null {
  if (!result) return null;
  const row = result.scan_summary?.ghunt as Record<string, unknown> | undefined;
  const finding = (result.confirmed_findings ?? []).find((f) => f.type === 'google_account_intel');
  const meta = (finding?.profile_metadata ?? {}) as Record<string, unknown>;
  const items = Number(row?.items ?? 0);
  if (!row && !finding) return null;
  return {
    found: items > 0 || Boolean(finding),
    note: String(row?.note ?? ''),
    metadata: Object.keys(meta).length ? meta : undefined,
  };
}

export function emailDorkHitsFromResult(result: InvestigationResult | null, query: string): EmailDorkHit[] {
  if (!result) return [];
  const seedEmail = parseSeedEmail(query || result.query);
  const seen = new Set<string>();
  const out: EmailDorkHit[] = [];

  const add = (hit: EmailDorkHit) => {
    if (!hit.url.startsWith('http') || seen.has(hit.url)) return;
    seen.add(hit.url);
    out.push(hit);
  };

  for (const finding of result.confirmed_findings ?? []) {
    if (finding.type !== 'email_web_mention' || !finding.url) continue;
    add({
      id: `cf_dork_${String(finding.url)}`,
      title: String(finding.title ?? finding.url),
      url: String(finding.url),
      snippet: String(finding.snippet ?? '').slice(0, 400),
      platform: platformFromUrl(String(finding.url)),
      category: String(finding.dork_category ?? 'email_search'),
    });
  }

  for (const ent of result.fusion?.deduplicated_entities ?? []) {
    const meta = (ent.metadata ?? {}) as Record<string, unknown>;
    if (meta.check_type !== 'google_dork') continue;
    if (meta.query_type && meta.query_type !== 'email') continue;
    if (!seedInDorkContext(meta, seedEmail ?? query)) continue;
    const url = String(meta.url || ent.value || '');
    if (!url.startsWith('http')) continue;
    add({
      id: ent.entity_id ?? url,
      title: String(meta.title ?? meta.dork_query ?? 'Web mention'),
      url,
      snippet: String(meta.snippet ?? meta.content ?? '').slice(0, 400),
      platform: platformFromUrl(url),
      category: String(meta.dork_category ?? 'email_search'),
    });
  }

  return out.slice(0, 24);
}
