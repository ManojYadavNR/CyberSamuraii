export type QueryType = 'username' | 'email' | 'phone' | 'domain' | 'image' | 'infra' | 'auto';

export type ToolStatus = 'pending' | 'running' | 'done' | 'failed';

export interface ToolProgress {
  tool: string;
  status: ToolStatus;
  success?: boolean;
  execution_time_ms?: number;
  error?: string;
  detail?: string;
}

export interface LinkedAccount {
  entity_id?: string;
  platform: string;
  handle: string;
  url?: string;
  email?: string;
  verified?: boolean;
  fusion_score?: number;
  sources?: string[];
  display_name?: string;
  bio?: string;
  location?: string;
  avatar_url?: string;
  website?: string;
  organizations?: string[];
  extracted_intelligence?: Record<string, unknown>;
}

export interface FieldProvenance {
  field: string;
  value: string;
  source_entity_id?: string;
  source_entity_type?: string;
  source_platform?: string;
  source_tool?: string;
  source_ref?: string;
  extraction_strategy?: string;
  confidence?: number;
}

export interface PlatformProfile {
  entity_id: string;
  platform: string;
  handle: string;
  url?: string;
  verified?: boolean;
  sources?: string[];
  fusion_score?: number;
  display_name?: string;
  bio?: string;
  location?: string;
  website?: string;
  email?: string;
  avatar_url?: string;
  organizations?: string[];
  aliases?: string[];
  usernames?: string[];
  public_links?: string[];
  public_metadata?: Record<string, unknown>;
  extracted_fields?: FieldProvenance[];
}

export interface UnifiedPersonProfile {
  seed_query: string;
  platform_count: number;
  verified_platform_count: number;
  names: FieldProvenance[];
  aliases: FieldProvenance[];
  usernames: FieldProvenance[];
  bios: FieldProvenance[];
  locations: FieldProvenance[];
  emails: FieldProvenance[];
  websites: FieldProvenance[];
  organizations: FieldProvenance[];
  images: FieldProvenance[];
  public_links: FieldProvenance[];
  search_findings?: FieldProvenance[];
  platform_profiles: PlatformProfile[];
  primary_display_name?: string;
  primary_bio?: string;
  primary_location?: string;
  primary_avatar?: string;
}

export interface EvidenceExtractionOutput {
  entities_enriched: number;
  fields_extracted: number;
  platforms_analyzed: number;
  extraction_strategies: string[];
  unified_profile?: UnifiedPersonProfile;
  lead_visuals?: LeadVisual[];
  lead_screenshots_captured?: number;
  google_search_intel?: {
    discovered_keywords?: Array<{
      phrase: string;
      category: string;
      source_url?: string;
      source_title?: string;
      source_snippet?: string;
      score?: number;
    }>;
    follow_up_queries?: string[];
    seed_hit_count?: number;
    highlights?: Array<{
      title: string;
      url: string;
      snippet: string;
      platform: string;
      topic: string;
      serp_phase?: string;
      trigger_keyword?: string;
      preview_url?: string;
    }>;
    social_posts?: Array<{
      title: string;
      url: string;
      snippet: string;
      platform: string;
      topic: string;
      serp_phase?: string;
      trigger_keyword?: string;
      preview_url?: string;
    }>;
    instagram_posts?: Array<{
      title: string;
      url: string;
      snippet: string;
      platform: string;
      topic: string;
      preview_url?: string;
    }>;
    facebook_posts?: Array<{
      title: string;
      url: string;
      snippet: string;
      platform: string;
      topic: string;
      preview_url?: string;
    }>;
    google_highlights?: Array<{
      title: string;
      url: string;
      snippet: string;
      platform: string;
      topic: string;
      preview_url?: string;
    }>;
    hackathon_wins?: Array<{
      hackathon: string;
      placement: string;
      title: string;
      url: string;
      snippet: string;
      platform: string;
      preview_url?: string;
      source?: string;
    }>;
    colleges?: Array<{
      college: string;
      page_name?: string;
      page_url?: string;
      title: string;
      url: string;
      snippet: string;
      platform: string;
      preview_url?: string;
    }>;
    employment?: Array<{
      employer: string;
      title: string;
      url: string;
      snippet: string;
      platform: string;
      preview_url?: string;
    }>;
  };
  samurai_social_intel?: Record<string, unknown>;
  linguistic_analysis?: LinguisticAnalysisOutput;
}

export interface LinguisticAnalysisOutput {
  seed_query?: string;
  artifacts_analyzed?: number;
  total_characters?: number;
  engine_mode?: string;
  models_used?: Record<string, string>;
  language_profile?: {
    primary?: string;
    distribution?: Record<string, number>;
    scripts?: Record<string, number>;
  };
  named_entities?: Array<{
    text: string;
    kind: string;
    source_ref?: string;
    confidence?: number;
  }>;
  topics?: Array<{
    topic: string;
    score: number;
    evidence_snippets?: string[];
    model?: string;
  }>;
  sentiment_overview?: Record<string, unknown>;
  style_fingerprints?: Array<Record<string, unknown>>;
  cross_links?: Array<{
    kind: string;
    sources?: string[];
    detail?: string;
    score?: number;
  }>;
  contradictions?: Array<{ type?: string; detail?: string }>;
  threat_flags?: Array<Record<string, unknown>>;
  keywords?: string[];
  corpus_sample?: Array<Record<string, unknown>>;
  artifact_insights?: Array<{
    source_ref?: string;
    source_tool?: string;
    source_platform?: string | null;
    language?: string;
    sentiment?: { label: string; confidence?: number; model?: string } | null;
    entity_count?: number;
    char_count?: number;
  }>;
}

export interface LeadVisual {
  lead_id: string;
  lead_type: string;
  title: string;
  url: string;
  snippet?: string;
  source_domain?: string;
  image_url?: string | null;
  thumbnail_url?: string | null;
  visual_source?: string;
  confidence?: number;
  priority_score?: number;
}

export interface InvestigationTreeNode {
  node_id: string;
  node_type: 'seed' | 'evidence' | 'lead' | 'hop' | 'profile';
  label: string;
  value?: string | null;
  parent_id?: string | null;
  children_ids?: string[];
  depth: number;
  status?: string | null;
  feature?: string | null;
  lead_type?: string | null;
  provenance?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface InvestigationTree {
  root_id: string;
  seed_query: string;
  nodes: InvestigationTreeNode[];
  total_evidence_nodes: number;
  total_lead_nodes: number;
  total_hop_nodes: number;
  max_depth: number;
}

export interface IdentityProfile {
  seed_query: string;
  confidence_score: number;
  primary_name?: string;
  primary_bio?: string;
  primary_location?: string;
  primary_avatar?: string;
  names: FieldProvenance[];
  aliases: FieldProvenance[];
  usernames: FieldProvenance[];
  photos: FieldProvenance[];
  emails: FieldProvenance[];
  phones: FieldProvenance[];
  domains: FieldProvenance[];
  websites: FieldProvenance[];
  organizations: FieldProvenance[];
  companies: FieldProvenance[];
  schools: FieldProvenance[];
  achievements: FieldProvenance[];
  projects: FieldProvenance[];
  events: FieldProvenance[];
  appearances: FieldProvenance[];
  publications: FieldProvenance[];
  bios: FieldProvenance[];
  locations: FieldProvenance[];
  public_links: FieldProvenance[];
  search_findings?: FieldProvenance[];
  social_accounts: FieldProvenance[];
  platform_profiles: PlatformProfile[];
  supporting_evidence: Array<{
    field: string;
    value: string;
    confidence: number;
    source_platform?: string;
    source_tool?: string;
    source_ref?: string;
    extraction_strategy?: string;
  }>;
  relationships: Array<{
    relation_type: string;
    target: string;
    confidence: number;
    source_ref?: string;
  }>;
  timeline: Array<{
    timestamp: string;
    event_type: string;
    description: string;
    source?: string;
    confidence: number;
  }>;
  investigation_tree?: InvestigationTree;
  verified_platform_count: number;
  total_evidence_fields: number;
  enrichment_passes: number;
}

export interface CorrelationEvidence {
  type: string;
  score: number;
  weight: number;
  detail?: string;
  conflicting?: boolean;
}

export interface AccountCluster {
  account_cluster_id: string;
  linked_accounts: LinkedAccount[];
  linked_account_refs: string[];
  confidence_score: number;
  evidence: CorrelationEvidence[];
  explainability: string[];
}

export interface FusionEntity {
  entity_id?: string;
  type: string;
  value: string;
  canonical_value?: string;
  aliases?: string[];
  normalized_value?: string;
  sources?: string[];
  reliability_score?: number;
  fusion_score?: number;
  first_seen?: string;
  last_seen?: string;
  metadata?: Record<string, unknown>;
  evidence?: Array<{
    tool: string;
    timestamp: string;
    raw_source_ref: string;
    source_confidence: number;
    raw_payload?: Record<string, unknown>;
  }>;
}

export interface ToolResultFull {
  tool: string;
  success: boolean;
  execution_time_ms: number;
  error?: string;
  data?: Array<Record<string, unknown>>;
  raw_output?: string;
}

export interface GraphEvidence {
  source_tool?: string;
  source_ref?: string;
  source_platform?: string;
  strategy?: string;
  confidence?: number;
  detail?: string;
}

export interface KnowledgeGraphNode {
  node_id: string;
  node_type: string;
  label: string;
  value?: string;
  fusion_score?: number;
  metadata?: Record<string, unknown>;
}

export interface KnowledgeGraphEdge {
  edge_id: string;
  source_id: string;
  target_id: string;
  relation: string;
  weight?: number;
  evidence?: GraphEvidence[];
}

export interface ReasoningPath {
  path_id: string;
  seed: string;
  node_ids: string[];
  labels: string[];
  relations: string[];
  confidence: number;
  summary: string;
}

export interface GraphOutput {
  node_count: number;
  edge_count: number;
  clusters: Array<{ cluster_id: string; members: string[]; algorithm: string; modularity?: number }>;
  influence_scores: Array<{ node_id: string; node_type: string; pagerank: number; betweenness: number }>;
  suspicious_networks: Array<{ network_id: string; network_type: string; members: string[]; confidence: number; indicators: string[] }>;
  warnings?: string[];
  neo4j_exported?: boolean;
  graph_engine_version?: string;
  knowledge_graph_nodes?: KnowledgeGraphNode[];
  knowledge_graph_edges?: KnowledgeGraphEdge[];
  reasoning_paths?: ReasoningPath[];
}

export interface InvestigationResult {
  feature: string;
  query: string;
  query_normalized?: string;
  warnings?: string[];
  execution_mode?: string;
  tool_results: ToolResultFull[];
  merged_results?: Array<Record<string, unknown>>;
  confirmed_findings?: Array<Record<string, unknown>>;
  public_profile_data?: Array<Record<string, unknown>>;
  investigation_leads?: Array<Record<string, unknown>>;
  scan_summary?: Record<string, unknown>;
  discovery?: DiscoveryOutput;
  evidence_extraction?: EvidenceExtractionOutput;
  identity_profile?: IdentityProfile;
  reverse_image_discovery?: ReverseImageDiscoveryOutput;
  image_correlation?: ImageCorrelationOutput;
  fusion?: {
    fusion_score: number;
    investigation_id?: string;
    deduplicated_entities: FusionEntity[];
    evidence_map?: Record<string, unknown>;
    raw_evidence_index?: Record<string, string[]>;
  };
  correlation?: {
    clusters: AccountCluster[];
    total_clusters: number;
    total_accounts_analyzed: number;
    signal_availability?: Record<string, boolean>;
    warnings?: string[];
    correlation_engine_version?: string;
  };
  graph?: GraphOutput;
  confidence_raw_inputs?: Array<{ source_tool: string; field: string; value: unknown; weight: number }>;
  tools_succeeded: number;
  tools_failed: number;
  total_execution_time_ms: number;
}

export interface ReviewRecord {
  review_id: string;
  cluster_id: string;
  decision: 'approve' | 'reject' | 'suspicious';
  reviewer: string;
  notes: string;
  timestamp: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export type BackendToolHealth = 'healthy' | 'unhealthy' | 'not_installed' | 'missing_api_key';

export interface DiscoveryHop {
  hop_id: string;
  depth: number;
  query: string;
  feature: string;
  lead_type: string;
  parent_lead_id?: string | null;
  status: 'completed' | 'failed' | 'skipped';
  entities_found?: number;
  leads_spawned?: number;
  execution_time_ms?: number;
  error?: string | null;
  reason?: string;
}

export interface DiscoveryTimelineEvent {
  event_id: string;
  timestamp: string;
  phase: string;
  message: string;
  detail?: string | null;
  depth?: number | null;
  query?: string | null;
}

export interface DiscoveryLead {
  lead_id: string;
  query: string;
  lead_type: string;
  feature: string;
  depth: number;
  priority: number;
  source_entity_id?: string | null;
  source_entity_type?: string | null;
  source_query?: string | null;
  reason?: string;
  metadata?: Record<string, unknown>;
}

export interface DiscoveryConfig {
  enabled: boolean;
  max_depth: number;
  max_hops: number;
  max_leads_per_hop: number;
  max_total_leads: number;
}

export interface DiscoveryOutput {
  enabled: boolean;
  seed_query: string;
  seed_query_type: string;
  total_hops: number;
  total_leads_discovered: number;
  total_leads_expanded: number;
  max_depth_reached: number;
  stop_reason: string;
  total_execution_time_ms: number;
  hops: DiscoveryHop[];
  timeline: DiscoveryTimelineEvent[];
  pending_leads?: DiscoveryLead[];
  visited?: string[];
  config?: DiscoveryConfig;
  investigation_tree?: InvestigationTree;
}

export interface ReverseImageMatch {
  match_id: string;
  source: string;
  match_type: string;
  match_url: string;
  page_url?: string | null;
  title?: string | null;
  snippet?: string | null;
  platform?: string | null;
  confidence: number;
  evidence_path?: string[];
  provenance?: Record<string, unknown>;
  profile_urls?: string[];
  organizations?: string[];
  publications?: string[];
}

export interface EvidenceChainLink {
  step: string;
  value: string;
  source?: string | null;
  confidence?: number;
}

export interface EvidenceChain {
  chain_id: string;
  seed_image: string;
  links: EvidenceChainLink[];
  terminal_lead?: string | null;
  confidence: number;
}

export interface ReverseImageDiscoveryOutput {
  seed_image: string;
  sources_run?: string[];
  sources_failed?: string[];
  matches: ReverseImageMatch[];
  generated_leads?: DiscoveryLead[];
  evidence_chains?: EvidenceChain[];
  total_matches: number;
}

export interface IdentityCandidate {
  candidate_id: string;
  label: string;
  confidence: number;
  reasons?: string[];
  linked_accounts?: string[];
  face_match_score?: number | null;
  image_similarity_score?: number | null;
  hash_similarity_score?: number | null;
  evidence_paths?: string[][];
}

export interface DetectedFace {
  face_id: string;
  person_index: number;
  source_tool: string;
  confidence: number;
  quality_score?: number | null;
  bbox?: number[];
  crop_path?: string | null;
  crop_preview_url?: string | null;
  embedding_signature?: string | null;
}

export interface ImageCorrelationOutput {
  seed_image: string;
  seed_preview_url?: string | null;
  detected_faces?: DetectedFace[];
  identity_candidates: IdentityCandidate[];
  face_matches: Array<Record<string, unknown>>;
  reverse_matches: ReverseImageMatch[];
  hash_signatures?: Record<string, string>;
  similarity_signature?: string | null;
  confidence_breakdown?: Record<string, number>;
  evidence_chains?: EvidenceChain[];
}
