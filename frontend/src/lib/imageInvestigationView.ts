import type {
  EvidenceChain,
  IdentityCandidate,
  ImageCorrelationOutput,
  InvestigationResult,
  ReverseImageDiscoveryOutput,
  ReverseImageMatch,
} from '../types';
import type { IntelligenceItem, IntelligenceSection } from './intelligenceView';
import { buildIntelligenceSections } from './intelligenceView';
import { formatTargetLabel, sanitizeProvenance } from './pathDisplay';

function rev(result: InvestigationResult): ReverseImageDiscoveryOutput | undefined {
  return result.reverse_image_discovery;
}

function corr(result: InvestigationResult): ImageCorrelationOutput | undefined {
  return result.image_correlation;
}

function matchToItem(match: ReverseImageMatch, prefix: string): IntelligenceItem {
  return {
    id: `${prefix}_${match.match_id}`,
    label: match.title || match.platform || match.match_type,
    value: match.page_url || match.match_url,
    confidence: match.confidence,
    source: match.source,
    sourcePlatform: match.platform || undefined,
    provenance: sanitizeProvenance([
      match.match_type,
      match.snippet,
      ...(match.evidence_path ?? []),
    ]),
    metadata: { ...match, renderAs: match.match_url.match(/\.(jpg|jpeg|png|webp|gif)/i) ? 'image' : undefined },
  };
}

function candidateToItem(c: IdentityCandidate): IntelligenceItem {
  return {
    id: c.candidate_id,
    label: c.label,
    value: (c.linked_accounts ?? [])[0] || c.label,
    confidence: c.confidence,
    provenance: (c.reasons ?? []).join(' · '),
    metadata: {
      linked_accounts: c.linked_accounts,
      face_match_score: c.face_match_score,
      image_similarity_score: c.image_similarity_score,
      hash_similarity_score: c.hash_similarity_score,
      evidence_paths: c.evidence_paths,
    },
  };
}

function chainToItem(chain: EvidenceChain, idx: number): IntelligenceItem {
  const path = (chain.links ?? []).map((l) => `${l.step}: ${l.value}`).join(' → ');
  return {
    id: chain.chain_id || `chain_${idx}`,
    label: 'Evidence chain',
    value: path,
    confidence: chain.confidence,
    provenance: chain.terminal_lead || undefined,
    metadata: { links: chain.links, seed_image: chain.seed_image },
  };
}

export interface ImageInvestigationBrief {
  who: string;
  why: string;
  what: string;
  where: string;
  linked: string;
  next: string;
}

export function imageInvestigationBrief(result: InvestigationResult | null, query: string): ImageInvestigationBrief {
  if (!result) {
    return {
      who: 'Unknown — upload an image to begin',
      why: 'No analysis yet',
      what: '—',
      where: '—',
      linked: '—',
      next: 'Upload a profile photo, screenshot, or image URL',
    };
  }

  const correlation = corr(result);
  const discovery = rev(result);
  const topCandidate = correlation?.identity_candidates?.[0];
  const topMatch = discovery?.matches?.[0] || correlation?.reverse_matches?.[0];
  const accounts = new Set<string>();

  for (const c of correlation?.identity_candidates ?? []) {
    for (const a of c.linked_accounts ?? []) accounts.add(a);
  }
  for (const m of discovery?.matches ?? []) {
    for (const p of m.profile_urls ?? []) accounts.add(p);
  }

  const faceDetected = (correlation?.face_matches?.length ?? 0) > 0;
  const who = topCandidate?.label
    || topMatch?.title
    || topMatch?.platform
    || formatTargetLabel(query, faceDetected);
  const isGraphic = (topCandidate?.reasons ?? []).some((r) =>
    r.includes('not a person photo') || r.includes('CLIP classified'),
  );
  const why = isGraphic
    ? 'Logo/graphic detected — results show OCR text and hash-verified matches only, not person identity'
    : topCandidate
      ? (topCandidate.reasons ?? []).slice(0, 2).join('; ')
      : topMatch
        ? `Hash-verified match (${topMatch.match_type}) via ${topMatch.source} at ${(topMatch.confidence * 100).toFixed(0)}%`
        : 'No hash-verified reverse matches — upload a profile photo for identity linking';

  const what = [
    discovery?.total_matches ? `${discovery.total_matches} reverse image match(es)` : null,
    correlation?.face_matches?.length ? `${correlation.face_matches.length} face signal(s)` : null,
    Object.keys(correlation?.hash_signatures ?? {}).length ? 'perceptual hash fingerprint' : null,
    accounts.size ? `${accounts.size} linked account(s)` : null,
  ].filter(Boolean).join(' · ') || 'Image analyzed — limited external matches';

  const where = topMatch
    ? `${topMatch.source} → ${topMatch.page_url || topMatch.match_url}`
    : (discovery?.sources_run ?? []).join(', ') || 'local analysis only';

  const linked = accounts.size
    ? Array.from(accounts).slice(0, 3).join(', ') + (accounts.size > 3 ? ` (+${accounts.size - 3})` : '')
    : 'No linked accounts yet';

  const nextLeads = discovery?.generated_leads?.slice(0, 3).map((l) => l.query) ?? [];
  const next = nextLeads.length
    ? `Investigate: ${nextLeads.join('; ')}`
    : accounts.size
      ? 'Pivot into linked profile URLs and usernames'
      : 'Expand reverse search sources or run discovery on extracted domains';

  return { who, why, what, where, linked, next };
}

export function buildImageInvestigationSections(
  result: InvestigationResult | null,
  query: string,
): IntelligenceSection[] {
  if (!result) return [];

  const discovery = rev(result);
  const correlation = corr(result);
  const baseSections = buildIntelligenceSections(result, query);
  const byId = Object.fromEntries(baseSections.map((s) => [s.id, s]));

  const reverseMatches = [
    ...(discovery?.matches ?? []),
    ...(correlation?.reverse_matches ?? []),
  ];
  const seenMatch = new Set<string>();
  const uniqueMatches = reverseMatches.filter((m) => {
    const key = (m.page_url || m.match_url).toLowerCase();
    if (seenMatch.has(key)) return false;
    seenMatch.add(key);
    return true;
  });

  const chains = [
    ...(discovery?.evidence_chains ?? []),
    ...(correlation?.evidence_chains ?? []),
  ];

  const confidenceItems: IntelligenceItem[] = Object.entries(correlation?.confidence_breakdown ?? {}).map(
    ([key, val]) => ({
      id: `conf_${key}`,
      label: key.replace(/_/g, ' '),
      value: `${(val * 100).toFixed(0)}%`,
      confidence: val,
    }),
  );

  const faceItems: IntelligenceItem[] = (correlation?.face_matches ?? []).map((f, i) => ({
    id: `face_${i}`,
    label: String(f.field || 'face'),
    value: String(f.value || f.embedding || 'detected'),
    confidence: Number(f.confidence ?? 0),
    source: String(f.source_tool || ''),
    provenance: f.quality != null ? `quality ${f.quality}` : undefined,
    metadata: f,
  }));

  const hashItems: IntelligenceItem[] = Object.entries(correlation?.hash_signatures ?? {}).map(([algo, sig]) => ({
    id: `hash_${algo}`,
    label: algo,
    value: sig,
    provenance: 'perceptual hash',
  }));

  return [
    {
      id: 'identity_candidates',
      title: 'Identity Candidates',
      icon: '🎯',
      description: 'Who might this person be?',
      items: (correlation?.identity_candidates ?? []).map(candidateToItem),
    },
    {
      id: 'face_matches',
      title: 'Face Matches',
      icon: '👤',
      description: 'Face embedding and detection signals',
      items: faceItems,
    },
    {
      id: 'reverse_matches',
      title: 'Reverse Image Matches',
      icon: '🔍',
      description: 'Identical, cropped, mirrored, and cross-platform reuse',
      items: uniqueMatches.map((m, i) => matchToItem(m, `rev_${i}`)),
    },
    {
      id: 'accounts',
      title: 'Accounts Discovered',
      icon: '👥',
      description: 'Profiles linked via image correlation',
      items: byId.accounts?.items ?? [],
    },
    {
      id: 'photos',
      title: 'Photos Discovered',
      icon: '📷',
      description: 'Matched and related images across platforms',
      items: [
        ...(byId.photos?.items ?? []),
        ...uniqueMatches
          .filter((m) => /\.(jpg|jpeg|png|webp|gif)/i.test(m.match_url))
          .map((m, i) => matchToItem(m, `photo_${i}`)),
      ],
    },
    {
      id: 'emails',
      title: 'Emails Discovered',
      icon: '✉️',
      description: 'Email addresses from linked profiles and OCR',
      items: byId.emails?.items ?? [],
    },
    {
      id: 'websites',
      title: 'Websites Discovered',
      icon: '🌐',
      description: 'Websites, articles, and public references',
      items: [
        ...(byId.links?.items ?? []),
        ...uniqueMatches
          .flatMap((m) => (m.profile_urls ?? []).map((url, i) => ({
            id: `web_${m.match_id}_${i}`,
            label: m.platform || 'profile',
            value: url,
            confidence: m.confidence,
            source: m.source,
            provenance: `reverse_image:${m.match_type}`,
          }))),
      ],
    },
    {
      id: 'organizations',
      title: 'Organizations',
      icon: '🏢',
      description: 'Companies, schools, and affiliations',
      items: [
        ...(byId.organizations?.items ?? []),
        ...uniqueMatches.flatMap((m) =>
          (m.organizations ?? []).map((org, i) => ({
            id: `org_${m.match_id}_${i}`,
            label: 'organization',
            value: org,
            confidence: m.confidence,
            source: m.source,
            provenance: m.match_url,
          })),
        ),
      ],
    },
    {
      id: 'events',
      title: 'Events',
      icon: '📅',
      description: 'Appearances, conferences, and dated references',
      items: byId.events?.items ?? [],
    },
    {
      id: 'projects',
      title: 'Projects',
      icon: '🚀',
      description: 'Repositories, portfolios, and project mentions',
      items: byId.projects?.items ?? [],
    },
    {
      id: 'timeline',
      title: 'Timeline',
      icon: '⏱',
      description: 'Chronological intelligence events',
      items: byId.timeline?.items ?? [],
    },
    {
      id: 'intelligence_graph',
      title: 'Intelligence Graph',
      icon: '🕸',
      description: 'Connected entities and relationships',
      items: byId.paths?.items ?? [],
    },
    {
      id: 'evidence_chains',
      title: 'Evidence Chains',
      icon: '⛓',
      description: 'Image → Match → Profile → Organization paths',
      items: chains.map(chainToItem),
    },
    {
      id: 'confidence_breakdown',
      title: 'Confidence Breakdown',
      icon: '📊',
      description: 'Signal weights: face, hash, reverse image, account linkage',
      items: [...confidenceItems, ...hashItems],
    },
  ];
}
