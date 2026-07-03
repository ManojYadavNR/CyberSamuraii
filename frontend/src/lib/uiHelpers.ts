import type { AccountCluster, InvestigationResult, LinkedAccount, ToolProgress } from '../types';
import { isPlausibleAccountHandle, isVerifiedLinkedAccount } from './accountVerification';
import { getVerifiedPlatformDetails } from './platformAccountView';
import { normalizePlatformHost, profileSlugFromUrl } from './platformUtils';
import { formatTargetLabel, isLocalPath } from './pathDisplay';

export type ConfidenceTier = 'high' | 'medium' | 'low';

export function confidenceTier(score: number): ConfidenceTier {
  if (score >= 70) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}

export function tierLabel(tier: ConfidenceTier): string {
  return tier === 'high' ? 'HIGH CONFIDENCE' : tier === 'medium' ? 'MEDIUM CONFIDENCE' : 'LOW CONFIDENCE';
}

export function tierClasses(tier: ConfidenceTier): string {
  if (tier === 'high') return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  if (tier === 'medium') return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
  return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
}

export interface FlatAccount {
  id: string;
  platform: string;
  handle: string;
  displayName?: string;
  bio?: string;
  location?: string;
  avatarUrl?: string;
  website?: string;
  organizations?: string[];
  email?: string;
  url?: string;
  verified: boolean;
  fusionScore: number;
  confidence: number;
  evidenceCount: number;
  sources: string[];
  clusterId: string;
  cluster: AccountCluster;
  account: LinkedAccount;
}

export function flattenAccounts(result: InvestigationResult | null, verifiedOnly = true): FlatAccount[] {
  if (!result?.correlation?.clusters) return [];
  const out: FlatAccount[] = [];
  for (const cluster of result.correlation.clusters) {
    cluster.linked_accounts.forEach((acct, i) => {
      if (verifiedOnly && !isVerifiedLinkedAccount(acct)) return;
      out.push({
        id: `${cluster.account_cluster_id}_${i}`,
        platform: acct.platform || 'unknown',
        handle: acct.handle || acct.url || '—',
        displayName: acct.display_name,
        bio: acct.bio,
        location: acct.location,
        avatarUrl: acct.avatar_url,
        website: acct.website,
        organizations: acct.organizations,
        email: acct.email,
        url: acct.url,
        verified: !!acct.verified,
        fusionScore: (acct.fusion_score ?? 0) * 100,
        confidence: cluster.confidence_score,
        evidenceCount: cluster.evidence.length,
        sources: acct.sources ?? [],
        clusterId: cluster.account_cluster_id,
        cluster,
        account: acct,
      });
    });
  }
  return out.sort((a, b) => b.confidence - a.confidence);
}

function isVerifiedFinding(item: Record<string, unknown>): boolean {
  if (item.verified === false) return false;
  if (item.check_type === 'dataset_lookup' && item.verified !== true) return false;
  if (item.status === 'not_registered' || item.status === 'rate_limited') return false;
  return true;
}

export function toolFindingsCount(result: InvestigationResult | null, toolName: string): number {
  if (toolName === 'multi_input') {
    const branches = result?.tool_results?.filter((t) => t.tool !== 'multi_input') ?? [];
    if (branches.length) return branches.length;
    if (result?.fusion?.deduplicated_entities?.length) return result.fusion.deduplicated_entities.length;
    return 0;
  }
  const tr = result?.tool_results?.find((t) => t.tool === toolName);
  if (tr?.data?.length) {
    const rows = tr.data.filter((item) => (item as Record<string, unknown>).platform !== '_scan_summary');
    if (rows.length) return rows.length;
    const summary = tr.data.find((item) => (item as Record<string, unknown>).platform === '_scan_summary') as
      | Record<string, unknown>
      | undefined;
    const fromSummary = Number(summary?.sites_found ?? 0);
    if (fromSummary) return fromSummary;
  }
  if (toolName === 'google_dorking' && result?.fusion?.deduplicated_entities) {
    return result.fusion.deduplicated_entities.filter((ent) => {
      const meta = (ent.metadata ?? {}) as Record<string, unknown>;
      return meta.check_type === 'google_dork' || (ent.sources ?? []).includes('google_dorking');
    }).length;
  }
  return 0;
}

function hitsFromToolDetail(detail?: string): number | null {
  if (!detail) return null;
  const m = detail.match(/(\d+)\s+hit\(s\)/i);
  return m ? Number(m[1]) : null;
}

export function toolLiveFindingsCount(
  result: InvestigationResult | null,
  toolName: string,
  detail?: string,
): number {
  const fromResult = toolFindingsCount(result, toolName);
  if (fromResult > 0) return fromResult;
  const fromDetail = hitsFromToolDetail(detail);
  return fromDetail ?? 0;
}

export function toolEmptyLabel(toolName: string): string {
  if (toolName === 'multi_input') return 'Branches completed — see tool results below';
  if (toolName === 'samurai') return 'No social profiles resolved';
  if (toolName === 'google_dorking') return 'No web results found';
  if (toolName === 'platform_probe') return 'No live profiles on major platforms';
  if (toolName === 'nexfil' || toolName === 'blackbird') return 'No profiles found';
  return 'No accounts found';
}

export function toolVerifiedFindingsCount(result: InvestigationResult | null, toolName: string): number {
  const tr = result?.tool_results?.find((t) => t.tool === toolName);
  if (!tr?.data?.length) return 0;
  return tr.data.filter((item) => {
    const row = item as Record<string, unknown>;
    if (row.platform === '_scan_summary') return false;
    return isVerifiedFinding(row);
  }).length;
}

export interface ToolScanStats {
  sitesChecked: number;
  sitesFound: number;
  note?: string;
}

export function toolScanStats(result: InvestigationResult | null, toolName: string): ToolScanStats | null {
  const tr = result?.tool_results?.find((t) => t.tool === toolName);
  const summary = tr?.data?.find((item) => (item as Record<string, unknown>).platform === '_scan_summary') as
    | Record<string, unknown>
    | undefined;
  if (!summary) return null;
  return {
    sitesChecked: Number(summary.sites_checked ?? 0),
    sitesFound: Number(summary.sites_found ?? 0),
    note: summary.note ? String(summary.note) : undefined,
  };
}

export interface ProbeCandidate {
  id: string;
  platform: string;
  handle: string;
  url: string;
  sources: string[];
  status?: string;
}

function probeHandleFromEntity(meta: Record<string, unknown>, url: string, platform: string): string {
  const fromMeta = String(meta.username || meta.handle || '').trim().toLowerCase();
  const fromUrl = profileSlugFromUrl(url)?.toLowerCase() || '';
  const platformHost = normalizePlatformHost(platform || url);
  if (fromUrl && isPlausibleAccountHandle(fromUrl)) return fromUrl;
  if (fromMeta && fromMeta !== platformHost && normalizePlatformHost(fromMeta) !== platformHost && isPlausibleAccountHandle(fromMeta)) {
    return fromMeta;
  }
  return fromUrl || fromMeta;
}

function isUsernameProbeEntity(meta: Record<string, unknown>, sources: string[]): boolean {
  if (meta.investigation_lead || meta.status === 'rate_limited') return false;
  if (meta.check_type === 'google_dork' || meta.corroboration_status === 'search_reference' || meta.status === 'search_reference') {
    return false;
  }
  if (sources.includes('google_dorking')) return false;
  return sources.some((s) => ['sherlock', 'maigret', 'social_analyzer', 'platform_probe', 'blackbird', 'nexfil'].includes(s));
}

export function flattenProbeCandidates(result: InvestigationResult | null): ProbeCandidate[] {
  const verifiedKeys = new Set(
    getVerifiedPlatformDetails(result).map((d) => `${d.platform}:${d.handle}`.toLowerCase()),
  );
  const entities = result?.fusion?.deduplicated_entities ?? [];
  const out: ProbeCandidate[] = [];
  const seen = new Set<string>();
  for (const ent of entities) {
    if (ent.type !== 'account') continue;
    const meta = (ent.metadata ?? {}) as Record<string, unknown>;
    const sources = ent.sources ?? [];
    if (!isUsernameProbeEntity(meta, sources)) continue;
    if (meta.verified === true || meta.live_profile_verified === true) continue;
    if (meta.status === 'unavailable' || meta.live_profile_verified === false) continue;
    const platform = String(meta.platform || ent.value.split('/')[0] || 'unknown');
    const url = String(meta.url || ent.value);
    const handle = probeHandleFromEntity(meta, url, platform);
    if (!handle || !isPlausibleAccountHandle(handle)) continue;
    if (normalizePlatformHost(handle) === normalizePlatformHost(platform)) continue;
    const key = `${normalizePlatformHost(platform)}:${handle}`.toLowerCase();
    if (verifiedKeys.has(key)) continue;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      id: ent.entity_id || key,
      platform: normalizePlatformHost(platform) || platform,
      handle,
      url,
      sources,
      status: String(meta.corroboration_status || meta.status || 'probe'),
    });
  }
  return out;
}

export interface TimelineEvent {
  id: string;
  label: string;
  detail?: string;
  status: 'done' | 'running' | 'failed';
}

export function buildTimeline(
  result: InvestigationResult | null,
  toolProgress: ToolProgress[],
  phase: string,
  status: string,
): TimelineEvent[] {
  const events: TimelineEvent[] = [];

  for (const t of toolProgress) {
    const count = toolFindingsCount(result, t.tool);
    const verified = toolVerifiedFindingsCount(result, t.tool);
    const detail =
      count > 0
        ? verified > 0 && verified < count
          ? `${count} hit(s), ${verified} verified`
          : `${count} finding(s) discovered`
        : t.error ?? undefined;
    events.push({
      id: `tool_${t.tool}`,
      label: `${capitalize(t.tool)} ${t.status === 'done' ? 'completed' : t.status === 'running' ? 'running' : 'failed'}`,
      detail,
      status: t.status === 'done' ? 'done' : t.status === 'failed' ? 'failed' : 'running',
    });
  }

  if (result?.fusion) {
    const n = result.fusion.deduplicated_entities?.length ?? 0;
    events.push({
      id: 'fusion',
      label: 'Fusion merged duplicate entities',
      detail: `${n} unified entities`,
      status: 'done',
    });
  }

  if (result?.evidence_extraction) {
    const ex = result.evidence_extraction;
    events.push({
      id: 'evidence_extraction',
      label: 'Universal evidence extraction completed',
      detail: `${ex.fields_extracted} field(s) from ${ex.platforms_analyzed} platform(s) · ${ex.entities_enriched ?? 0} enriched`,
      status: 'done',
    });
    if (ex.extraction_strategies?.length) {
      events.push({
        id: 'extraction_strategies',
        label: 'Extraction strategies applied',
        detail: ex.extraction_strategies.join(', '),
        status: 'done',
      });
    }
  } else if (phase === 'evidence_extraction' && status === 'running') {
    events.push({
      id: 'evidence_extraction_running',
      label: 'Extracting intelligence from discovered evidence',
      detail: 'Building multi-platform person profile',
      status: 'running',
    });
  }

  if (result?.correlation) {
    events.push({
      id: 'correlation',
      label: 'Correlation linked accounts',
      detail: `${result.correlation.total_clusters} cluster(s), ${result.correlation.total_accounts_analyzed} accounts`,
      status: 'done',
    });
  }

  if (result?.graph || phase === 'graph' || phase === 'discovery' || status === 'complete') {
    events.push({
      id: 'graph',
      label: 'Graph analysis completed',
      detail: result?.graph
        ? `${result.graph.node_count} nodes, ${result.graph.edge_count} edges`
        : 'Processing network intelligence',
      status: result?.graph ? 'done' : status === 'running' ? 'running' : 'done',
    });
  }

  if (result?.identity_profile?.timeline?.length) {
    for (const ev of result.identity_profile.timeline) {
      events.push({
        id: `identity_tl_${ev.timestamp}_${ev.event_type}`,
        label: ev.description,
        detail: `${ev.event_type} · ${ev.source ?? 'identity profile'}`,
        status: 'done',
      });
    }
  }

  if (result?.graph?.reasoning_paths?.length) {
    events.push({
      id: 'reasoning_paths',
      label: 'Knowledge graph reasoning paths discovered',
      detail: `${result.graph.reasoning_paths.length} path(s) through connected intelligence`,
      status: 'done',
    });
  }

  if (result?.discovery?.timeline?.length) {
    for (const ev of result.discovery.timeline) {
      events.push({
        id: `discovery_${ev.event_id}`,
        label: ev.message,
        detail: ev.detail ?? undefined,
        status:
          ev.phase === 'hop_failed' || ev.phase === 'expansion_stopped' && result.discovery?.stop_reason !== 'no_new_leads'
            ? 'failed'
            : ev.phase === 'hop_started'
              ? 'running'
              : 'done',
      });
    }
  } else if (phase === 'discovery' && status === 'running') {
    events.push({
      id: 'discovery_running',
      label: 'Recursive discovery expanding leads',
      detail: 'Following evidence from discovered entities',
      status: 'running',
    });
  }

  return events;
}

export function investigationSummary(result: InvestigationResult | null, query: string, queryType: string) {
  const clusters = result?.correlation?.clusters ?? [];
  const avgConfidence =
    clusters.length > 0
      ? clusters.reduce((s, c) => s + c.confidence_score, 0) / clusters.length
      : 0;
  const accounts = flattenAccounts(result);
  const identityConfidence = (result?.identity_profile?.confidence_score ?? 0) * 100;
  const faceDetected = (result?.image_correlation?.face_matches?.length ?? 0) > 0;
  const displayQuery = formatTargetLabel(
    result?.identity_profile?.seed_query && !isLocalPath(result.identity_profile.seed_query)
      ? result.identity_profile.seed_query
      : query,
    faceDetected,
  );
  return {
    target: displayQuery,
    type: queryType,
    accountsFound: accounts.length || result?.correlation?.total_accounts_analyzed || 0,
    clusters: result?.correlation?.total_clusters ?? 0,
    fusionScore: (result?.fusion?.fusion_score ?? 0) * 100,
    confidence: identityConfidence || avgConfidence,
    identityConfidence,
    entitiesEnriched: result?.evidence_extraction?.entities_enriched ?? 0,
    reasoningPaths: result?.graph?.reasoning_paths?.length ?? 0,
    runtime: (result?.total_execution_time_ms ?? 0) / 1000,
    suspiciousNetworks: result?.graph?.suspicious_networks?.length ?? 0,
  };
}

export function buildAiSummary(result: InvestigationResult | null, query: string): string {
  if (!result) return 'Run an investigation to generate intelligence summary.';
  const s = investigationSummary(result, query, '');
  const identity = result.identity_profile;
  const profile = identity ?? result.evidence_extraction?.unified_profile;
  const cluster = result.correlation?.clusters?.[0];
  const lines = [
    `Target "${query}" — ${s.accountsFound} account(s) across ${s.clusters} identity cluster(s).`,
  ];
  if (identity) {
    lines.push(
      `Identity profile: ${(identity.confidence_score * 100).toFixed(0)}% confidence · ` +
      `${identity.total_evidence_fields} evidence field(s) · ${identity.verified_platform_count} verified platform(s).`,
    );
    if (identity.primary_name && !isLocalPath(identity.primary_name)) lines.push(`Primary identity: ${identity.primary_name}`);
    if (identity.primary_bio) lines.push(`Bio: ${identity.primary_bio.slice(0, 120)}${identity.primary_bio.length > 120 ? '…' : ''}`);
    if (identity.relationships.length) lines.push(`${identity.relationships.length} relationship(s) with evidence.`);
  } else if (profile) {
    const up = profile as { verified_platform_count?: number; names?: unknown[]; bios?: unknown[]; locations?: unknown[]; primary_display_name?: string; primary_bio?: string };
    lines.push(
      `Unified profile built from ${up.verified_platform_count ?? 0} verified platform(s) — ` +
      `${up.names?.length ?? 0} name(s), ${up.bios?.length ?? 0} bio(s), ${up.locations?.length ?? 0} location(s).`,
    );
    if (up.primary_display_name) lines.push(`Primary identity: ${up.primary_display_name}`);
    if (up.primary_bio) lines.push(`Bio: ${up.primary_bio.slice(0, 120)}${up.primary_bio.length > 120 ? '…' : ''}`);
  }
  if (result.evidence_extraction) {
    lines.push(`Universal extraction: ${result.evidence_extraction.fields_extracted} fields from ${result.evidence_extraction.platforms_analyzed} platform(s).`);
  }
  if (result.discovery?.enabled) {
    lines.push(`Auto-pivot: ${result.discovery.total_hops} hop(s), ${result.discovery.total_leads_discovered} lead(s) discovered.`);
  }
  if (s.reasoningPaths > 0) {
    lines.push(`Knowledge graph: ${s.reasoningPaths} reasoning path(s).`);
  }
  lines.push(`Fusion confidence ${s.fusionScore.toFixed(0)}% · Link confidence ${s.confidence.toFixed(0)}%.`);
  if (cluster) {
    const top = cluster.explainability.slice(0, 2);
    if (top.length) lines.push(`Key evidence: ${top.join(' ')}`);
  }
  if (s.suspiciousNetworks > 0) {
    lines.push(`⚠ ${s.suspiciousNetworks} suspicious network pattern(s) detected.`);
  }
  const strong = cluster?.evidence.filter((e) => e.score >= 0.7).map((e) => e.type);
  if (strong?.length) lines.push(`Strongest signals: ${strong.join(', ')}.`);
  return lines.join('\n');
}

export const NODE_COLORS: Record<string, string> = {
  Person: '#ef4444',
  Account: '#3b82f6',
  Username: '#6366f1',
  Email: '#22c55e',
  Phone: '#f97316',
  Domain: '#a855f7',
  Website: '#8b5cf6',
  Image: '#eab308',
  Organization: '#14b8a6',
  Event: '#f59e0b',
  Project: '#0ea5e9',
  Achievement: '#84cc16',
  Publication: '#d946ef',
  Location: '#64748b',
  Post: '#06b6d4',
  Hashtag: '#ec4899',
  Suspicious: '#dc2626',
  Flagged: '#f43f5e',
};

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ');
}
