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

function _toolRows(result: InvestigationResult, tool: string): {
  rows: Record<string, unknown>[];
  summary: Record<string, unknown> | undefined;
  success?: boolean;
  error?: string;
  raw?: string;
} {
  const tr = result.tool_results?.find((t) => t.tool === tool);
  const rows = (tr?.data ?? [])
    .map((row) => row as Record<string, unknown>)
    .filter((row) => row.platform !== '_scan_summary');
  const summary = (tr?.data ?? []).find(
    (row) => (row as Record<string, unknown>).platform === '_scan_summary',
  ) as Record<string, unknown> | undefined;
  return {
    rows,
    summary,
    success: tr?.success,
    error: tr?.error,
    raw: tr?.raw_output,
  };
}

export function emailToolStatuses(result: InvestigationResult | null): EmailToolStatus[] {
  if (!result) return [];
  const summary = result.scan_summary ?? {};
  const out: EmailToolStatus[] = [];

  for (const tool of ['holehe', 'gravatar', 'ghunt', 'theharvester', 'google_dorking', 'spiderfoot']) {
    const trInfo = _toolRows(result, tool);
    const row = summary[tool] as Record<string, unknown> | undefined;
    if (!trInfo.summary && !trInfo.rows.length && trInfo.success === undefined && !row) continue;

    let status = String(row?.status ?? (trInfo.success ? 'completed' : trInfo.success === false ? 'failed' : 'completed'));
    let detail: string | undefined;

    if (tool === 'holehe') {
      const h = holeheScanSummary(result);
      detail = h?.sitesChecked
        ? `${h.sitesChecked} sites checked · ${h.verified ?? 0} registration(s)`
        : undefined;
    } else if (tool === 'gravatar') {
      const found = row?.found === true
        || trInfo.rows.some((r) => r.platform === 'gravatar')
        || (result.public_profile_data ?? []).some((p) => p.source === 'gravatar' || p.platform === 'gravatar');
      status = found ? 'found' : 'not_found';
      detail = found ? 'Public Gravatar profile linked' : 'No Gravatar profile';
    } else if (tool === 'theharvester') {
      const skipped = status === 'skipped'
        || Boolean(trInfo.raw && trInfo.raw.includes('Skipped theHarvester'));
      if (skipped) {
        status = 'skipped';
        detail = String(row?.note ?? trInfo.raw ?? 'Skipped for consumer mail (Gmail/Yahoo) — use org domain');
      } else {
        const items = Math.max(Number(row?.items ?? 0), trInfo.rows.length);
        detail = `${items} harvested item(s)`;
      }
    } else if (tool === 'google_dorking') {
      const dorkRows = trInfo.rows.filter((r) => {
        const ct = String(r.check_type || '');
        return ct === 'google_dork' || ct === 'google_search_discovery' || Boolean(r.url);
      });
      const hits = Math.max(
        Number(row?.hits ?? 0),
        Number(trInfo.summary?.sites_found ?? 0),
        dorkRows.length,
      );
      const dorks = Math.max(
        Number(row?.dorks_run ?? 0),
        Number(trInfo.summary?.sites_checked ?? 0),
      );
      const note = String(trInfo.summary?.note ?? row?.note ?? '');
      detail = note || `${hits} web mention(s) from ${dorks} dork(s)`;
      if (hits > 0 && status === 'failed') status = 'completed';
    } else if (tool === 'ghunt') {
      const items = Math.max(Number(row?.items ?? 0), trInfo.rows.length);
      status = items > 0 ? 'found' : 'not_found';
      detail = items > 0
        ? 'Google account metadata found'
        : String(row?.note ?? trInfo.raw ?? 'No Google profile linked');
    } else if (tool === 'spiderfoot') {
      const items = Math.max(Number(row?.items ?? 0), trInfo.rows.length);
      detail = String(row?.note ?? trInfo.summary?.note ?? `${items} item(s)`);
    } else if (trInfo.error) {
      detail = trInfo.error;
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

  // Prefer live tool_results so the panel matches progress-tracker hits even before
  // scan_summary / fusion is fully written.
  for (const row of result.tool_results?.find((t) => t.tool === 'google_dorking')?.data ?? []) {
    const item = row as Record<string, unknown>;
    if (item.platform === '_scan_summary') continue;
    const checkType = String(item.check_type || '');
    if (checkType && checkType !== 'google_dork' && checkType !== 'google_search_discovery') continue;
    if (item.query_type && item.query_type !== 'email' && result.feature === 'multi') {
      // In multi-input, skip username-branch dork rows in the email panel.
      continue;
    }
    const url = String(item.url || item.source_url || '');
    if (!url.startsWith('http')) continue;
    add({
      id: `tr_dork_${url}`,
      title: String(item.title ?? item.dork_query ?? 'Web mention'),
      url,
      snippet: String(item.snippet ?? item.content ?? '').slice(0, 400),
      platform: platformFromUrl(url),
      category: String(item.dork_category ?? 'email_search'),
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
