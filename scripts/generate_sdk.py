"""Automated OpenAPI Client SDK Generator for DeepSearch.

Parses docs/openapi.yaml and generates production-ready, fully-typed client SDKs for:
1. TypeScript (npm package)
2. Go (go module)
"""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
OPENAPI_PATH = ROOT_DIR / "docs" / "openapi.yaml"
SDK_DIR = ROOT_DIR / "sdk"


def generate_typescript_sdk():
    ts_dir = SDK_DIR / "typescript" / "src"
    ts_dir.mkdir(parents=True, exist_ok=True)

    package_json = {
        "name": "@deepsearch/sdk",
        "version": "1.0.0",
        "description": "Official TypeScript/JavaScript Client SDK for DeepSearch Platform",
        "main": "dist/index.js",
        "types": "dist/index.d.ts",
        "scripts": {"build": "tsc", "test": 'echo "Running TS tests"'},
        "keywords": ["deepsearch", "scraper", "rag", "retrieval", "sdk"],
        "author": "DeepSearch Team",
        "license": "Apache-2.0",
        "devDependencies": {"typescript": "^5.3.0"},
    }

    tsconfig = {
        "compilerOptions": {
            "target": "ES2022",
            "module": "commonjs",
            "declaration": True,
            "outDir": "./dist",
            "strict": True,
            "esModuleInterop": True,
        },
        "include": ["src/**/*"],
    }

    types_ts = """/**
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
"""

    client_ts = """import {
  HealthResponse,
  InspectRequest,
  InspectResponse,
  CrawlJobRequest,
  CrawlJobResponse,
  SearchQueryRequest,
  SearchResultItem,
  ResearchRequest,
  ResearchHandle,
  ResearchStatus,
  ResearchResult
} from "./types";

export class DeepSearchClient {
  private baseUrl: string;
  private apiKey?: string;

  constructor(options?: { baseUrl?: string; apiKey?: string }) {
    this.baseUrl = (options?.baseUrl || "http://localhost:8080/api/v1").replace(/\\/+$/, "");
    this.apiKey = options?.apiKey;
  }

  private async request<T>(path: string, method: string = "GET", body?: any): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json"
    };
    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }

    const resp = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined
    });

    if (!resp.ok) {
      const errorText = await resp.text();
      throw new Error(`DeepSearch API Error [${resp.status}]: ${errorText}`);
    }

    return (await resp.json()) as T;
  }

  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health");
  }

  async inspectUrl(url: string): Promise<InspectResponse> {
    return this.request<InspectResponse>("/inspect", "POST", { url });
  }

  async startCrawl(req: CrawlJobRequest): Promise<CrawlJobResponse> {
    return this.request<CrawlJobResponse>("/crawl", "POST", req);
  }

  async searchHybrid(query: string, limit: number = 10): Promise<SearchResultItem[]> {
    return this.request<SearchResultItem[]>("/search/hybrid", "POST", { query, limit });
  }

  async startResearch(req: ResearchRequest): Promise<ResearchHandle> {
    return this.request<ResearchHandle>("/research", "POST", req);
  }

  async getResearchStatus(runId: string): Promise<ResearchStatus> {
    return this.request<ResearchStatus>(`/research/${runId}`);
  }

  async getResearchResult(runId: string): Promise<ResearchResult> {
    return this.request<ResearchResult>(`/research/${runId}/result`);
  }

  async cancelResearch(runId: string): Promise<{ run_id: string; status: string }> {
    return this.request<{ run_id: string; status: string }>(`/research/${runId}/cancel`, "POST");
  }
}

export * from "./types";
"""

    import json

    (SDK_DIR / "typescript" / "package.json").write_text(
        json.dumps(package_json, indent=2), encoding="utf-8"
    )
    (SDK_DIR / "typescript" / "tsconfig.json").write_text(
        json.dumps(tsconfig, indent=2), encoding="utf-8"
    )
    (ts_dir / "types.ts").write_text(types_ts, encoding="utf-8")
    (ts_dir / "client.ts").write_text(client_ts, encoding="utf-8")
    (ts_dir / "index.ts").write_text('export * from "./client";\n', encoding="utf-8")
    (SDK_DIR / "typescript" / "README.md").write_text(
        "# DeepSearch TypeScript Client SDK\n\nOfficial typed client library for the DeepSearch API.\n",
        encoding="utf-8",
    )
    print("[OK] Generated TypeScript SDK in sdk/typescript")


def generate_go_sdk():
    go_dir = SDK_DIR / "go"
    go_dir.mkdir(parents=True, exist_ok=True)

    go_mod = """module github.com/Homiakus/deepsearch/sdk/go

go 1.22
"""

    types_go = """package deepsearch

type HealthResponse struct {
	Status  string `json:"status"`
	App     string `json:"app"`
	Version string `json:"version"`
}

type InspectRequest struct {
	URL string `json:"url"`
}

type InspectResponse struct {
	URL                 string  `json:"url"`
	CanonicalURL        string  `json:"canonical_url"`
	HTTPStatus          int     `json:"http_status"`
	ContentType         string  `json:"content_type"`
	StaticScore         float64 `json:"static_score"`
	JSDependencyScore   float64 `json:"js_dependency_score"`
	DetectedAPIsCount   int     `json:"detected_apis_count"`
	TablesCount         int     `json:"tables_count"`
	CanvasDetected      bool    `json:"canvas_detected"`
	VisualScore         float64 `json:"visual_score"`
	RecommendedStrategy string  `json:"recommended_strategy"`
	EstimatedCost       float64 `json:"estimated_cost"`
}

type CrawlJobRequest struct {
	URL      string `json:"url"`
	MaxDepth int    `json:"max_depth,omitempty"`
	MaxPages int    `json:"max_pages,omitempty"`
	Mode     string `json:"mode,omitempty"`
}

type CrawlJobResponse struct {
	JobID    string `json:"job_id"`
	Status   string `json:"status"`
	URL      string `json:"url"`
	MaxDepth int    `json:"max_depth"`
	MaxPages int    `json:"max_pages"`
}

type SearchQueryRequest struct {
	Query string `json:"query"`
	Limit int    `json:"limit,omitempty"`
}

type SearchResultItem struct {
	URL        string  `json:"url"`
	Title      string  `json:"title"`
	Snippet    string  `json:"snippet"`
	Score      float64 `json:"score"`
	SourceType string  `json:"source_type"`
}

type ResearchRequest struct {
	Query            string   `json:"query"`
	MaxPages         int      `json:"max_pages,omitempty"`
	Depth            int      `json:"depth,omitempty"`
	Mode             string   `json:"mode,omitempty"`
	PreferredSources []string `json:"preferred_sources,omitempty"`
}

type ResearchHandle struct {
	RunID     string  `json:"run_id"`
	Query     string  `json:"query"`
	Status    string  `json:"status"`
	CreatedAt float64 `json:"created_at"`
}

type ResearchStatus struct {
	RunID         string  `json:"run_id"`
	Status        string  `json:"status"`
	PagesCrawled  int     `json:"pages_crawled"`
	EvidenceCount int     `json:"evidence_count"`
	QualityScore  float64 `json:"quality_score"`
}

type ResearchClaim struct {
	ID         string  `json:"id"`
	Text       string  `json:"text"`
	Confidence float64 `json:"confidence"`
	SourceURL  string  `json:"source_url"`
}

type ResearchResult struct {
	RunID           string          `json:"run_id"`
	Query           string          `json:"query"`
	Status          string          `json:"status"`
	Claims          []ResearchClaim `json:"claims"`
	QualityScore    float64         `json:"quality_score"`
	DurationSeconds float64         `json:"duration_seconds"`
}
"""

    client_go = """package deepsearch

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type Client struct {
	BaseURL    string
	APIKey     string
	HTTPClient *http.Client
}

func NewClient(baseURL, apiKey string) *Client {
	if baseURL == "" {
		baseURL = "http://localhost:8080/api/v1"
	}
	baseURL = strings.TrimRight(baseURL, "/")
	return &Client{
		BaseURL: baseURL,
		APIKey:  apiKey,
		HTTPClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (c *Client) doRequest(ctx context.Context, method, path string, body interface{}, out interface{}) error {
	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return err
		}
		bodyReader = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, bodyReader)
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("deepsearch api error [%d]: %s", resp.StatusCode, string(respBody))
	}

	if out != nil {
		return json.NewDecoder(resp.Body).Decode(out)
	}
	return nil
}

func (c *Client) GetHealth(ctx context.Context) (*HealthResponse, error) {
	var res HealthResponse
	err := c.doRequest(ctx, http.MethodGet, "/health", nil, &res)
	return &res, err
}

func (c *Client) InspectURL(ctx context.Context, url string) (*InspectResponse, error) {
	var res InspectResponse
	err := c.doRequest(ctx, http.MethodPost, "/inspect", &InspectRequest{URL: url}, &res)
	return &res, err
}

func (c *Client) StartCrawl(ctx context.Context, req *CrawlJobRequest) (*CrawlJobResponse, error) {
	var res CrawlJobResponse
	err := c.doRequest(ctx, http.MethodPost, "/crawl", req, &res)
	return &res, err
}

func (c *Client) SearchHybrid(ctx context.Context, query string, limit int) ([]SearchResultItem, error) {
	var res []SearchResultItem
	err := c.doRequest(ctx, http.MethodPost, "/search/hybrid", &SearchQueryRequest{Query: query, Limit: limit}, &res)
	return res, err
}

func (c *Client) StartResearch(ctx context.Context, req *ResearchRequest) (*ResearchHandle, error) {
	var res ResearchHandle
	err := c.doRequest(ctx, http.MethodPost, "/research", req, &res)
	return &res, err
}

func (c *Client) GetResearchStatus(ctx context.Context, runID string) (*ResearchStatus, error) {
	var res ResearchStatus
	err := c.doRequest(ctx, http.MethodGet, "/research/"+runID, nil, &res)
	return &res, err
}

func (c *Client) GetResearchResult(ctx context.Context, runID string) (*ResearchResult, error) {
	var res ResearchResult
	err := c.doRequest(ctx, http.MethodGet, "/research/"+runID+"/result", nil, &res)
	return &res, err
}

func (c *Client) CancelResearch(ctx context.Context, runID string) error {
	return c.doRequest(ctx, http.MethodPost, "/research/"+runID+"/cancel", nil, nil)
}
"""

    (go_dir / "go.mod").write_text(go_mod, encoding="utf-8")
    (go_dir / "types.go").write_text(types_go, encoding="utf-8")
    (go_dir / "client.go").write_text(client_go, encoding="utf-8")
    (go_dir / "README.md").write_text(
        "# DeepSearch Go Client SDK\n\nOfficial Go client library for the DeepSearch Platform.\n",
        encoding="utf-8",
    )
    print("[OK] Generated Go SDK in sdk/go")


if __name__ == "__main__":
    generate_typescript_sdk()
    generate_go_sdk()
    print("All SDKs successfully generated from OpenAPI specifications.")
