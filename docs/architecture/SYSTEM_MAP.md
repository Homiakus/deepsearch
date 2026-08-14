# System Map (AS-IS)

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  
**Version:** 1.0.0  
**Runtime:** Python 3.11+  

---

## 1. Directory & Package Structure

```text
deepsearch/
├── scraper/                     # Core Python Package
│   ├── config.py                # Global settings & configuration models (Pydantic Settings)
│   ├── acquisition/             # Multi-level page fetch engine (L0-L5)
│   │   ├── engine.py            # AdaptiveAcquisitionEngine & CapturedArtifact
│   │   ├── browser_pool.py      # Playwright Chromium browser context pool
│   │   ├── http_fetcher.py      # Async HTTPX client wrapper with SSRF protection
│   │   ├── page_classifier.py   # Page Intelligence heuristics & scoring
│   │   ├── proxy_manager.py     # Proxy rotation & validation
│   │   ├── session_manager.py   # Session state management & cookie store
│   │   └── media_downloader.py  # Async image/video/binary downloader
│   ├── control/                 # Crawl orchestration & rate governance
│   │   ├── scheduler.py         # RequestFrontier & CrawlRequest state queue
│   │   ├── planner.py           # CostPlanner & strategy escalation logic
│   │   ├── rate_limiter.py      # TokenBucket & HostRateLimiter
│   │   └── budget.py            # BudgetTracker & limit enforcer
│   ├── discovery/               # URL discovery & crawling rules
│   │   ├── links.py             # HTML/Sitemap link extraction & canonical checks
│   │   ├── robots.py            # Robots.txt parser & policy checker
│   │   └── seed_finder.py       # Multi-source seed discovery (ArXiv, Wikipedia, etc.)
│   ├── extraction/              # Structural & semantic content extraction
│   │   ├── engine.py            # Main extraction pipeline (trafilatura, bs4, selectolax)
│   │   ├── markdown.py          # HTML-to-Clean-Markdown conversion
│   │   ├── table_extractor.py   # HTML/Markdown table parser & normalizer
│   │   ├── self_healing.py      # Resilient CSS/XPath selector matcher
│   │   └── ocr.py               # Tesseract OCR engine for visual text extraction
│   ├── normalization/           # Data sanitization & deduplication
│   │   ├── canonicalizer.py     # URL normalization & tracking param stripper
│   │   └── deduplicator.py      # Blake3 content hashing & SimHash near-duplicate check
│   ├── storage/                 # Data persistence & vector indexing
│   │   ├── cas.py               # Content Addressable Storage (zstd compressed)
│   │   ├── db.py                # Async SQLAlchemy engine & session factory
│   │   ├── models.py            # SQLAlchemy ORM models (CrawlJob, PageArtifact, etc.)
│   │   └── vector_store.py      # Qdrant client adapter for embeddings
│   ├── visual/                  # Visual capture & PixelRAG retrieval
│   │   ├── tiling.py            # Screenshot grid partitioning (Pillow)
│   │   └── pixel_rag.py         # Visual multivector embedding & search
│   ├── monitoring/              # Observability & telemetry
│   │   └── telemetry.py         # TelemetryTracker (OpenTelemetry & Prometheus metrics)
│   ├── search/                  # Local search engine
│   │   └── search_engine.py     # Hybrid text & visual search dispatcher
│   ├── pipeline/                # Autonomous research pipeline
│   │   └── search_pipeline.py   # DeepSearchPipeline (archive generator)
│   ├── api/                     # REST API Service
│   │   ├── app.py               # FastAPI application factory
│   │   └── routes.py            # 9 FastAPI endpoints (/inspect, /crawl, /search, /research, etc.)
│   ├── cli/                     # Command Line Interface
│   │   └── main.py              # Typer CLI application (`scraper`)
│   ├── ui/                      # Dashboard UI
│   │   └── dashboard.py         # Web UI dashboard
│   └── mcp/                     # Model Context Protocol
│       └── server.py            # FastMCP stdio server
├── tests/                       # Test Suite
│   └── unit/                    # 18 Unit test modules (50 test cases)
├── docs/                        # Project Documentation
├── migrations/                  # Database schema migrations
├── pyproject.toml               # Package dependencies & build configuration
└── rule.md / cycle-rule.md      # Technical specification & master prompt
```

---

## 2. Inventory of Entrypoints

| Entrypoint Type | Path / Symbol | Responsibility | Status |
| :--- | :--- | :--- | :--- |
| **CLI** | `scraper.cli.main:app` | Command-line execution (`inspect`, `crawl`, `extract`, `search`, `research`, `mcp`) | Operational |
| **REST API** | `scraper.api.app:app` | HTTP API built with FastAPI (9 async endpoints) | Operational |
| **MCP Server** | `scraper.mcp.server:mcp` | Stdio FastMCP server for LLM clients | Operational |
| **Dashboard** | `scraper.ui.dashboard:dashboard_app` | Administrative web dashboard (`/ui`) | Operational |
| **Worker Engine** | `scraper.acquisition.engine:AdaptiveAcquisitionEngine` | Core runtime execution driver for fetching | Operational |
| **Research Engine**| `scraper.pipeline.search_pipeline:DeepSearchPipeline` | Autonomous research & archive packager | Operational |

---

## 3. Storage & Infrastructure Dependencies

- **Database:** PostgreSQL (SQLAlchemy AsyncIO + AsyncPG) for jobs, page metadata, and records.
- **Cache/Queue:** Redis for locks, session caches, and Request Frontier state management.
- **Vector DB:** Qdrant for text vector search & visual PixelRAG multivectors.
- **File System:** Local Content Addressable Storage (`./data/storage`) with zstandard compression and BLAKE3 keys.
