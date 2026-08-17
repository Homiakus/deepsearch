import {
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
    this.baseUrl = (options?.baseUrl || "http://localhost:8080/api/v1").replace(/\/+$/, "");
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
