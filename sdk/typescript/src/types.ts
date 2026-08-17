/**
 * DeepSearch Typed Interfaces & Models
 */

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
}

export interface InspectRequest {
  url: string;
}

export interface InspectResponse {
  url: string;
  canonical_url: string;
  http_status: number;
  content_type: string;
  static_score: number;
  js_dependency_score: number;
  detected_apis_count: number;
  tables_count: number;
  canvas_detected: boolean;
  visual_score: number;
  recommended_strategy: string;
  estimated_cost: number;
}

export interface CrawlJobRequest {
  url: string;
  max_depth?: number;
  max_pages?: number;
  mode?: "fast" | "balanced" | "complete" | "research" | "archive";
}

export interface CrawlJobResponse {
  job_id: string;
  status: string;
  url: string;
  max_depth: number;
  max_pages: number;
}

export interface SearchQueryRequest {
  query: string;
  limit?: number;
}

export interface SearchResultItem {
  url: string;
  title: string;
  snippet: string;
  score: number;
  source_type: string;
}

export interface ResearchRequest {
  query: string;
  max_pages?: number;
  depth?: number;
  mode?: string;
  preferred_sources?: string[];
}

export interface ResearchHandle {
  run_id: string;
  query: string;
  status: string;
  created_at: number;
}

export interface ResearchStatus {
  run_id: string;
  status: string;
  pages_crawled: number;
  evidence_count: number;
  quality_score: number;
}

export interface ResearchResult {
  run_id: string;
  query: string;
  status: string;
  claims: Array<{ id: string; text: string; confidence: number; source_url: string }>;
  quality_score: number;
  duration_seconds: number;
}
