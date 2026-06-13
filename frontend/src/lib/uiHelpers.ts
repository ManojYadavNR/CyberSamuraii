import type { AccountCluster, InvestigationResult, LinkedAccount, ToolProgress } from '../types';

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

export function flattenAccounts(result: InvestigationResult | null): FlatAccount[] {
  if (!result?.correlation?.clusters) return [];
  const out: FlatAccount[] = [];
  for (const cluster of result.correlation.clusters) {
    cluster.linked_accounts.forEach((acct, i) => {
      out.push({
        id: `${cluster.account_cluster_id}_${i}`,
        platform: acct.platform || 'unknown',
        handle: acct.handle || acct.url || '—',
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
  const tr = result?.tool_results?.find((t) => t.tool === toolName);
  if (!tr?.data?.length) return 0;
  return tr.data.filter((item) => isVerifiedFinding(item as Record<string, unknown>)).length;
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
    events.push({
      id: `tool_${t.tool}`,
      label: `${capitalize(t.tool)} ${t.status === 'done' ? 'completed' : t.status === 'running' ? 'running' : 'failed'}`,
      detail: count > 0 ? `${count} finding(s) discovered` : t.error ?? undefined,
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

  if (result?.correlation) {
    events.push({
      id: 'correlation',
      label: 'Correlation linked accounts',
      detail: `${result.correlation.total_clusters} cluster(s), ${result.correlation.total_accounts_analyzed} accounts`,
      status: 'done',
    });
  }

  if (result?.graph || phase === 'graph' || status === 'complete') {
    events.push({
      id: 'graph',
      label: 'Graph analysis completed',
      detail: result?.graph
        ? `${result.graph.node_count} nodes, ${result.graph.edge_count} edges`
        : 'Processing network intelligence',
      status: result?.graph ? 'done' : status === 'running' ? 'running' : 'done',
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
  return {
    target: query,
    type: queryType,
    accountsFound: accounts.length || result?.correlation?.total_accounts_analyzed || 0,
    clusters: result?.correlation?.total_clusters ?? 0,
    fusionScore: (result?.fusion?.fusion_score ?? 0) * 100,
    confidence: avgConfidence,
    runtime: (result?.total_execution_time_ms ?? 0) / 1000,
    suspiciousNetworks: result?.graph?.suspicious_networks?.length ?? 0,
  };
}

export function buildAiSummary(result: InvestigationResult | null, query: string): string {
  if (!result) return 'Run an investigation to generate intelligence summary.';
  const s = investigationSummary(result, query, '');
  const cluster = result.correlation?.clusters?.[0];
  const lines = [
    `Target "${query}" — ${s.accountsFound} account(s) across ${s.clusters} identity cluster(s).`,
    `Fusion confidence ${s.fusionScore.toFixed(0)}% · Average link confidence ${s.confidence.toFixed(0)}%.`,
  ];
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
  Email: '#22c55e',
  Phone: '#f97316',
  Domain: '#a855f7',
  Image: '#eab308',
  Post: '#06b6d4',
  Hashtag: '#ec4899',
  Suspicious: '#dc2626',
  Flagged: '#f43f5e',
};

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ');
}
