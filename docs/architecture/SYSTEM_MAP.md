# System Map (Target Architecture with Axiom ADGO)

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  
**Version:** 1.0.0  
**Runtime:** Python 3.11+ / Go 1.26+ / Rust 1.85+  

---

## 1. Directory & Package Structure

```text
deepsearch/
├── orchestrator/                # Go Axiom ADGO Durable Control Plane
│   ├── cmd/
│   │   └── deepsearch-orchestrator/main.go
│   ├── internal/
│   ├── plan/research.go     # Immutable ResearchPlan & activity graph
│   ├── server/api.go        # HTTP API for run control & status
│   ├── server/workers.go    # ADGO remote worker endpoints
│   ├── config/config.go     # Orchestrator configuration
│   ├── mapping/models.go    # Data mapping DTOs
│   └── activities/          # Activity types & mapping
│   ├── go.mod
│   └── go.sum
│
├── rust/                        # Rust Acquisition Worker Plane
│   └── acquisition-worker/      # High-performance browser/URL worker
│       ├── Cargo.toml
│       └── src/
│           ├── main.rs          # Local API server & entrypoint
│           ├── planner.rs       # Minimal Effective Browser capability planner
│           ├── security/        # Unified SSRF, DNS, and redirect policy
│           ├── backends/        # HTTP, Spider, Servo, Chromium, BrowserOxide, Blitz
│           ├── artifacts/       # CAS artifact writer & manifests
│           ├── adgo/            # Axiom ADGO batch worker client & activity
│           └── service/         # Local development REST API
│
├── scraper/                     # Core Python Execution Engine
│   ├── application/             # Application Boundary & Orchestration Handlers
│   │   ├── research_service.py  # ResearchApplicationService (single entrypoint)
│   │   ├── context.py           # ResearchExecutionContext & runtime container
│   │   ├── models.py            # Application DTOs (ResearchRequest/Result)
│   │   └── activities/          # Bounded activity handlers
│   │       ├── discovery.py
│   │       ├── acquisition.py
│   │       ├── extraction.py
│   │       ├── normalization.py
│   │       ├── indexing.py
│   │       ├── evidence.py
│   │       └── export.py
│   ├── orchestration/           # ADGO Remote Worker Protocol Client
│   │   ├── axiom_client.py      # HTTP client for ADGO coordinator
│   │   ├── axiom_worker.py      # Long-polling loop & task dispatch
│   │   ├── registry.py          # Activity handler registry
│   │   ├── errors.py            # Typed failure classifications
│   │   └── idempotency.py       # Deterministic idempotency hashing
│   ├── domain/                  # Rich Domain Models
│   │   └── document.py          # Structured Document representation
│   ├── evidence/                # Evidence-Driven Reasoning Layer
│   │   ├── models.py            # Claim, Evidence, Contradiction, Gap
│   │   ├── store.py             # In-memory & persisted evidence store
│   │   ├── builder.py           # Evidence extraction from chunks
│   │   └── coverage.py          # Information gain & gap coverage evaluator
│   ├── retrieval/               # Hybrid Retrieval & Embedding
│   │   ├── chunking.py          # Structure-aware hierarchical chunking
│   │   ├── embeddings.py        # FastEmbed dense & sparse embeddings
│   │   ├── reranker.py          # Cross-encoder reranker
│   │   └── service.py           # Hybrid retrieval engine (dense+sparse+RRF)
│   ├── security/                # Unified Security Policy
│   │   └── url_policy.py        # Strict SSRF, CIDR, DNS & size validation
│   ├── quality/                 # Multi-signal Content Quality
│   │   ├── models.py            # Quality metrics & decision enum
│   │   └── content_quality.py   # Heuristic & structural quality evaluator
│   ├── acquisition/             # Multi-level page fetch engine (L0-L5)
│   │   ├── engine.py            # AdaptiveAcquisitionEngine
│   │   ├── crawlee_adapter.py   # Crawlee RequestQueue batch crawler
│   │   ├── browser_pool.py      # Playwright Chromium browser context pool
│   │   ├── http_fetcher.py      # Async HTTPX client wrapper
│   │   └── page_classifier.py   # Page Intelligence heuristics
│   ├── control/                 # Crawl governance
│   │   ├── planner.py           # CostPlanner & strategy escalation logic
│   │   ├── rate_limiter.py      # TokenBucket & HostRateLimiter
│   │   └── budget.py            # BudgetTracker & resource metering
│   ├── discovery/               # Multi-source Discovery Architecture
│   │   ├── providers/           # Discovery provider adapters
│   │   └── robots.py            # Robots.txt parser & policy checker
│   ├── extraction/              # Structural & semantic content extraction
│   │   ├── engine.py            # Main extraction pipeline
│   │   ├── markdown.py          # HTML-to-Clean-Markdown conversion
│   │   ├── table_extractor.py   # HTML/Markdown table parser
│   │   ├── self_healing.py      # Resilient CSS/XPath selector matcher
│   │   └── ocr.py               # Tesseract OCR engine
│   ├── normalization/           # Data sanitization & deduplication
│   │   ├── canonicalizer.py     # URL normalization
│   │   └── deduplicator.py      # BLAKE3 hashing & SimHash distance
│   ├── storage/                 # Data persistence & vector indexing
│   │   ├── cas.py               # Content Addressable Storage (zstd compressed)
│   │   ├── db.py                # Async SQLAlchemy engine
│   │   └── vector_store.py      # Qdrant client adapter for embeddings
│   ├── visual/                  # Visual capture & PixelRAG (EXPERIMENTAL)
│   │   ├── tiling.py            # Screenshot grid partitioning
│   │   └── pixel_rag.py         # Visual multivector embedding & search
│   ├── monitoring/              # Observability & telemetry
│   │   └── telemetry.py         # TelemetryTracker with ADGO execution dimensions
│   ├── api/                     # REST API Service
│   │   ├── app.py               # FastAPI application factory & auth middleware
│   │   └── routes.py            # FastAPI endpoints delegating to ResearchService
│   ├── cli/                     # Command Line Interface
│   │   └── main.py              # Typer CLI application (`scraper`)
│   └── mcp/                     # Model Context Protocol
│       └── server.py            # FastMCP stdio server
├── tests/                       # Test Pyramid (unit, contract, integration, security)
├── evals/                       # Research Quality Benchmark Suite
├── migrations/                  # Database schema migrations
└── docs/                        # Project Documentation
```

---

## 2. Inventory of Entrypoints

| Entrypoint Type | Path / Symbol | Responsibility | Status |
| :--- | :--- | :--- | :--- |
| **CLI** | `scraper.cli.main:app` | Command-line execution (`inspect`, `crawl`, `extract`, `search`, `research`, `mcp`) | `ACTIVE` |
| **REST API** | `scraper.api.app:app` | HTTP API built with FastAPI (asynchronous job contracts) | `ACTIVE` |
| **MCP Server** | `scraper.mcp.server:mcp` | Stdio FastMCP server for LLM clients | `ACTIVE` |
| **Application Service** | `scraper.application.research_service:ResearchApplicationService` | Core application boundary | `ACTIVE` |
| **Go Orchestrator** | `orchestrator/cmd/deepsearch-orchestrator` | Axiom ADGO coordinator service | `ACTIVE` |
| **Rust Worker** | `rust/acquisition-worker` | High-throughput URL/browser execution worker (`/v1/acquire`) | `ACTIVE` |
| **Python Worker** | `scraper.orchestration.axiom_worker:AxiomRemoteWorker` | Remote activity execution worker | `ACTIVE` |
| **Dashboard** | `scraper.ui.dashboard:dashboard_app` | Administrative web dashboard (`/ui`) | `ACTIVE` |
