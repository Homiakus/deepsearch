# DeepSearch REST API Examples

Base API URL: `http://localhost:8080/api/v1`

---

## Environment Setup

```bash
export DS='http://localhost:8080/api/v1'
export API_KEY='dev-secret'
```

---

## 1. System Health Check

```bash
curl -X GET "$DS/health"
```

**Response:**
```json
{
  "status": "ok",
  "app": "DeepSearch Adaptive Scraper",
  "version": "1.0.0"
}
```

---

## 2. Telemetry & Performance Metrics

```bash
curl -X GET "$DS/metrics/summary"
```

**Response:**
```json
{
  "total_requests": 142,
  "successful_requests": 138,
  "failed_requests": 4,
  "http_strategy_count": 115,
  "browser_strategy_count": 27,
  "browser_escalation_ratio": 0.19,
  "total_bytes_downloaded": 45210982,
  "useful_data_bytes": 38102450
}
```

---

## 3. URL Inspection Mode (§57)

Analyzes a target URL, calculates Page Intelligence metrics (`static_score`, `js_dependency_score`, `visual_score`, API detection), and returns the recommended acquisition strategy.

```bash
curl -X POST "$DS/inspect" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://news.ycombinator.com"
  }'
```

**Response:**
```json
{
  "url": "https://news.ycombinator.com",
  "canonical_url": "https://news.ycombinator.com",
  "http_status": 200,
  "content_type": "text/html; charset=utf-8",
  "static_score": 0.95,
  "js_dependency_score": 0.05,
  "detected_apis_count": 0,
  "tables_count": 4,
  "canvas_detected": false,
  "visual_score": 0.1,
  "recommended_strategy": "HTTP",
  "estimated_cost": 1.0
}
```

---

## 4. Start Adaptive Crawl Job (§55)

Initiates an asynchronous crawling job for a domain or starting URL.

```bash
curl -X POST "$DS/crawl" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "max_depth": 3,
    "max_pages": 100,
    "mode": "balanced"
  }'
```

**Response:**
```json
{
  "job_id": "c7a6f2e9-411a-49bf-a83d-6b08e5699411",
  "status": "RUNNING",
  "url": "https://example.com",
  "max_depth": 3,
  "max_pages": 100
}
```

---

## 5. Get Crawl Job Status

Retrieves execution metrics and frontier state for an active or completed crawl job.

```bash
curl -X GET "$DS/crawl/c7a6f2e9-411a-49bf-a83d-6b08e5699411"
```

**Response:**
```json
{
  "job_id": "c7a6f2e9-411a-49bf-a83d-6b08e5699411",
  "stats": {
    "pending_count": 12,
    "in_flight_count": 3,
    "completed_count": 85
  }
}
```

---

## 6. Text Vector Search

Performs semantic vector retrieval against indexed page text chunks.

```bash
curl -X POST "$DS/search/text" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "adaptive web crawling token bucket rate limit",
    "limit": 5
  }'
```

**Response:**
```json
[
  {
    "url": "https://example.com/docs/rate-limiting",
    "title": "Rate Limiting Architecture",
    "score": 0.94,
    "snippet": "The host-aware scheduler uses a token bucket rate limiter with dynamic backoff...",
    "retrieval_type": "text_vector"
  }
]
```

---

## 7. Visual Multivector Search (PixelRAG)

Performs multivector retrieval on visual page screenshots and layout tiles.

```bash
curl -X POST "$DS/search/visual" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "system architecture diagram showing rate limiter",
    "limit": 5
  }'
```

**Response:**
```json
[
  {
    "url": "https://example.com/architecture",
    "title": "Architecture Overview Diagram",
    "score": 0.88,
    "snippet": "Visual tile layout matching architecture diagram boundaries.",
    "retrieval_type": "visual_multivector"
  }
]
```

---

## 8. Hybrid Search (Text + Visual)

Combines text vector similarity and visual multivector ranking for search queries.

```bash
curl -X POST "$DS/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "data ingestion pipeline performance metrics",
    "limit": 10
  }'
```

**Response:**
```json
[
  {
    "url": "https://example.com/telemetry",
    "title": "Telemetry & Metrics Summary",
    "score": 0.92,
    "snippet": "Prometheus tracking of useful data bytes vs network bytes...",
    "retrieval_type": "hybrid"
  }
]
```

---

## 9. Execute DeepSearch Research Pipeline

Executes an end-to-end research workflow: searches queries across preferred sources, crawls discovered URLs adaptively, extracts Markdown & structured data, builds RAG text chunks, and packages an output archive containing `files/` (links & media) and `rag/` (LLM-ready context).

```bash
curl -X POST "$DS/research" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "distributed vector databases performance comparison",
    "domain": "databases",
    "preferred_sources": ["https://qdrant.tech", "https://milvus.io"],
    "depth": 2,
    "max_pages": 30,
    "mode": "research",
    "export_archive": true
  }'
```

**Response:**
```json
{
  "query": "distributed vector databases performance comparison",
  "total_pages_processed": 24,
  "total_rag_chunks": 158,
  "archive_path": "deepsearch_a1b2c3d4.zip",
  "manifest": {
    "query": "distributed vector databases performance comparison",
    "timestamp": "2026-08-12T11:20:00Z",
    "files_count": 24,
    "rag_chunks_count": 158
  }
}
```
