import type { InvestigationResult } from '../types';

export interface LinguisticLanguageProfile {
  primary?: string;
  distribution?: Record<string, number>;
  scripts?: Record<string, number>;
}

export interface LinguisticNamedEntity {
  text: string;
  kind: string;
  source_ref?: string;
  confidence?: number;
}

export interface LinguisticTopic {
  topic: string;
  score: number;
  evidence_snippets?: string[];
  model?: string;
}

export interface LinguisticSentimentScore {
  label: string;
  confidence?: number;
  model?: string;
}

export interface LinguisticArtifactInsight {
  source_ref?: string;
  source_tool?: string;
  source_platform?: string | null;
  language?: string;
  sentiment?: LinguisticSentimentScore | null;
  entity_count?: number;
  char_count?: number;
}

export interface LinguisticStyleFingerprint {
  source_key: string;
  avg_word_length?: number;
  vocabulary_richness?: number;
  hashtag_rate?: number;
  emoji_rate?: number;
  exclamation_rate?: number;
}

export interface LinguisticCrossLink {
  kind: string;
  sources?: string[];
  detail?: string;
  score?: number;
}

export interface LinguisticTextArtifact {
  source_tool?: string;
  source_platform?: string | null;
  source_ref?: string;
  text?: string;
  char_count?: number;
  detected_language?: string;
}

export interface LinguisticAnalysis {
  seed_query?: string;
  artifacts_analyzed?: number;
  total_characters?: number;
  engine_mode?: string;
  models_used?: Record<string, string>;
  language_profile?: LinguisticLanguageProfile;
  named_entities?: LinguisticNamedEntity[];
  topics?: LinguisticTopic[];
  sentiment_overview?: Record<string, unknown>;
  style_fingerprints?: LinguisticStyleFingerprint[];
  cross_links?: LinguisticCrossLink[];
  contradictions?: Array<{ type?: string; detail?: string }>;
  threat_flags?: Array<Record<string, unknown>>;
  keywords?: string[];
  corpus_sample?: LinguisticTextArtifact[];
  artifact_insights?: LinguisticArtifactInsight[];
  identity_signals?: Array<{ kind?: string; text?: string; score?: number; source?: string }>;
  corpus_quality?: Record<string, unknown>;
}

export function linguisticFromResult(result?: InvestigationResult | null): LinguisticAnalysis | null {
  const raw = result?.evidence_extraction?.linguistic_analysis;
  if (!raw || typeof raw !== 'object') return null;
  if ((raw.artifacts_analyzed ?? 0) < 1) return null;
  return raw as LinguisticAnalysis;
}

export function languageLabel(code?: string): string {
  const map: Record<string, string> = {
    en: 'English',
    hi: 'Hindi',
    hinglish: 'Hinglish',
    ur: 'Urdu',
    unknown: 'Unknown',
  };
  return map[code ?? ''] ?? (code || 'Unknown');
}

export function sentimentColor(label?: string): string {
  if (label === 'positive') return 'text-emerald-400';
  if (label === 'negative') return 'text-rose-400';
  return 'text-slate-400';
}

export function entityKindIcon(kind: string): string {
  const k = kind.toLowerCase();
  if (k === 'person') return '👤';
  if (k === 'organization') return '🏢';
  if (k === 'location') return '📍';
  if (k === 'email') return '✉️';
  if (k === 'url') return '🔗';
  if (k === 'phone') return '📞';
  if (k === 'handle') return '@';
  return '•';
}

export function engineBadge(mode?: string): { label: string; variant: 'success' | 'warn' } {
  if (mode === 'ml') return { label: 'ML Engine', variant: 'success' };
  return { label: 'Heuristic', variant: 'warn' };
}
