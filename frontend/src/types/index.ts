export type QueryType = 'username' | 'email' | 'phone' | 'domain' | 'image' | 'infra' | 'auto';

export type ToolStatus = 'pending' | 'running' | 'done' | 'failed';

export interface ToolProgress {
  tool: string;
  status: ToolStatus;
  success?: boolean;
  execution_time_ms?: number;
  error?: string;
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
  graph?: {
    node_count: number;
    edge_count: number;
    clusters: Array<{ cluster_id: string; members: string[]; algorithm: string; modularity?: number }>;
    influence_scores: Array<{ node_id: string; node_type: string; pagerank: number; betweenness: number }>;
    suspicious_networks: Array<{ network_id: string; network_type: string; members: string[]; confidence: number; indicators: string[] }>;
    warnings?: string[];
    neo4j_exported?: boolean;
  };
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
