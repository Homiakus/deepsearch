# DeepSearch System Architecture

**Version:** 1.0.0  
**Language/Runtime:** Python 3.11+  
**Framework:** FastAPI, Crawlee / Playwright, Typer, SQLAlchemy AsyncIO, Qdrant, Redis  
**Specification:** `rule.md` & `cycle-rule.md`  

---

## 1. Executive Architecture Summary

DeepSearch is an **Adaptive Web Scraping & Retrieval Platform** designed around the core principle of **Minimal Effective Cost (§2)**. The platform automatically determines the static complexity, JavaScript dependencies, API availability, and visual needs of target URLs to route requests dynamically through low-cost HTTP requests, direct API extraction, headless browser rendering, or visual multivector screenshot retrieval.

The software architecture follows a **Clean Layered Architecture (Dependency DAG)** where high-level orchestration depends on explicit abstract protocols and typed data models rather than concrete third-party SDKs or storage drivers.

---

## 2. Layered Architecture & Dependency Rule

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                              ENTRYPOINTS                               │
 │  CLI (scraper/cli/main.py)  │  REST API (scraper/api/routes.py)       │
 │  Dashboard UI (scraper/ui)  │  MCP Server (scraper/mcp/server.py)      │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        APPLICATION ORCHESTRATION                       │
 │  DeepSearchPipeline (scraper/pipeline/search_pipeline.py)              │
 │  AdaptiveAcquisitionEngine (scraper/acquisition/engine.py)             │
 │  RequestFrontier Scheduler (scraper/control/scheduler.py)              │
 │  CostPlanner (scraper/control/planner.py)                              │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                              DOMAIN LOGIC                              │
 │  PageClassifier (page_classifier.py) │ ExtractionEngine (extraction/)   │
 │  Deduplicator (deduplicator.py)      │ SearchEngine (search_engine.py)  │
 │  SelfHealing (self_healing.py)       │ OCR Engine (ocr.py)              │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                         CONTRACTS & INTERFACES                         │
 │  PageIntelligence, CapturedArtifact, CrawlRequest, SearchResultItem   │
 │  BaseSettings Configuration (scraper/config.py)                       │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     ▲
                                     │
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        INFRASTRUCTURE ADAPTERS                         │
 │  HTTPFetcher (httpx)          │ BrowserPoolManager (playwright)        │
 │  ContentAddressableStore (zstd)│ Async SQLAlchemy DB (postgresql)       │
 │  VectorStoreAdapter (qdrant)  │ HostRateLimiter (token bucket)         │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Package & Module Breakdown

### 3.1 `scraper.config` & Settings Hierarchy
- **`ExecutionMode` Enum**: Configures execution levels: `FAST`, `BALANCED`, `COMPLETE`, `RESEARCH`, `ARCHIVE`.
- **Pydantic `Settings`**: Centralized, environment-aware configuration with nested models (`AdaptiveConfig`, `RobotsConfig`, `RateLimitConfig`, `SecurityConfig`, `BudgetConfig`, `CostWeights`).

### 3.2 `scraper.acquisition` (Multi-level Fetch Engine)
- **`AdaptiveAcquisitionEngine`**: Coordinates execution strategy across L0 (Cache), L1 (HTTP), L2 (Direct API), L3 (Playwright Chromium), and L4-L5 (Visual/PixelRAG).
- **`HTTPFetcher`**: Asynchronous HTTP client using `httpx` with SSRF pre-resolution and header spoofing.
- **`BrowserPoolManager`**: Manages Playwright Chromium browser instances, context recycling, network request/response logging, and page rendering.
- **`PageClassifier`**: Analyzes raw HTML DOM structure to compute `static_score`, `js_dependency_score`, `api_score`, `visual_score`, and frame detection.
- **`ProxyManager` & `SessionManager`**: Handles proxy rotation, IP validation, cookie persistence, and session headers.
- **`MediaDownloader`**: Async downloader for image, video, audio, and binary document assets.

### 3.3 `scraper.control` (Crawl Control & Rate Governance)
- **`RequestFrontier`**: Priority queue managing discovered `CrawlRequest` states and crawl depth limits.
- **`CostPlanner`**: Calculates cost estimates for fetching strategies based on configured `CostWeights`.
- **`HostRateLimiter`**: Token bucket algorithm enforcing per-host RPS and concurrent request limits with dynamic adjustment on 429/503 responses.
- **`BudgetTracker`**: Enforces per-job hard limits on maximum pages, depth, network bytes, browser execution time, and LLM token budgets.

### 3.4 `scraper.discovery` (Link & Rule Engine)
- **`links.py`**: Fast HTML link parser using `selectolax` to extract internal/external links, XML sitemaps, and canonical references.
- **`robots.py`**: Parses `robots.txt` rules and checks User-Agent path permissions and Crawl-Delay directives.

### 3.5 `scraper.extraction` (Content Transformation)
- **`engine.py`**: Main extraction pipeline integrating `trafilatura`, `BeautifulSoup`, and `selectolax`.
- **`markdown.py`**: Converts raw HTML into sanitized, token-optimized `clean_markdown` and `fit_markdown`.
- **`table_extractor.py`**: Parses complex HTML tables into Markdown, CSV, JSON, and structured HTML schemas.
- **`self_healing.py`**: Elements fingerprinting (DOM path, attributes, text similarity) to auto-repair broken CSS/XPath selectors.
- **`ocr.py`**: Tesseract OCR engine for text extraction from images and visual document scans.

### 3.6 `scraper.normalization` (Deduplication & Sanitization)
- **`canonicalizer.py`**: Normalizes URLs by standardizing schemes, stripping tracking parameters (`utm_*`, `fbclid`), and sorting query arguments.
- **`deduplicator.py`**: Applies BLAKE3 exact content hashing and 64-bit SimHash Hamming distance checks to prevent duplicate crawling and indexing.

### 3.7 `scraper.storage` (Data Persistence)
- **`cas.py`**: Content Addressable Storage (CAS) on local filesystem, compressed with `zstandard` (`zstd`) and keyed by BLAKE3 hash.
- **`db.py` & `models.py`**: SQLAlchemy AsyncIO ORM definitions for `CrawlJob`, `PageArtifact`, `CrawlRequestRecord`, and metadata.
- **`vector_store.py`**: Qdrant client adapter for dense text vector search and multivector visual tile embeddings.

### 3.8 `scraper.visual` (Visual Retrieval & PixelRAG)
- **`tiling.py`**: Partitions high-resolution screenshots into spatial grids (`Pillow`) for visual document retrieval.
- **`pixel_rag.py`**: Generates multi-vector representations for layout visual elements, charts, and spatial tables.

### 3.9 `scraper.monitoring` (Observability & Metrics)
- **`telemetry.py`**: OpenTelemetry trace context and Prometheus metrics tracking:
  - Total HTTP/Browser requests and status codes
  - Browser Escalation Ratio (target < 25%)
  - Useful Data Bytes vs Network Bytes ratio
  - Request duration histograms

### 3.10 `scraper.search` & `scraper.pipeline`
- **`SearchEngine`**: High-level search interface dispatching text vector, visual multivector, and hybrid search.
- **`DeepSearchPipeline`**: Autonomous end-to-end research engine. Executes research queries, recursively discovers pages, extracts content, builds RAG chunks, and packages a structured `.zip` archive containing `files/` (links & media) and `rag/` (LLM-ready context).

### 3.11 Interface Entrypoints
- **`scraper.api`**: FastAPI application exposing REST endpoints (`/api/v1/*`).
- **`scraper.cli`**: Typer CLI application for command-line control (`scraper crawl`, `scraper inspect`, `scraper extract`, `scraper search`, `scraper research`, `scraper mcp`).
- **`scraper.ui`**: Web UI monitoring dashboard served at `/ui`.
- **`scraper.mcp`**: Stdio-based Model Context Protocol (MCP) server integration for Claude Desktop and Claude Code.

---

## 4. End-to-End Processing Lifecycle

```text
 1. REQUEST DISCOVERY: Canonicalize URL -> Check Robots.txt -> Acquire Host Token
 2. ADAPTIVE ACQUISITION: Check CAS Cache -> Inspect Page -> Route to HTTP / API / Playwright Browser
 3. CLASSIFICATION: Compute static_score, js_dependency_score, api_score, visual_score
 4. DEDUPLICATION: Check Canonical URL Hash -> BLAKE3 Content Hash -> SimHash Hamming Distance
 5. EXTRACTION: HTML -> Clean Markdown + Tables (Markdown/CSV/JSON) + Media Assets + OCR
 6. STORAGE: Write Zstd compressed content to CAS -> Save Metadata to PostgreSQL
 7. INDEXING: Generate Chunks -> Index Text & Visual Multivectors in Qdrant
 8. PIPELINE / EXPORT: Package results for REST API response, CLI output, or Research Archive (.zip)
```

---

## 5. Security & Isolation Boundaries

- **SSRF Protection**: All network fetchers (`HTTPFetcher`, `BrowserPoolManager`) perform pre-flight DNS resolution to block access to private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`).
- **Payload Limits**: Strict response size caps (`100 MB` raw, `500 MB` decompressed).
- **Rate Limit Governance**: Token bucket rate limiting per target hostname protects target web servers from denial-of-service.
- **Graceful Resource Teardown**: Async context managers handle cleanup of browser contexts, HTTP connection pools, and database sessions during process termination.
