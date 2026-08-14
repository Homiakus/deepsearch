# Module Index

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  

---

| Subsystem / Package | Module Name | Primary Responsibility | Public Interface | Key Dependencies | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Config** | `scraper.config` | Central BaseSettings & sub-configurations | `settings`, `ExecutionMode` | `pydantic-settings` | `STABLE` |
| **Acquisition** | `scraper.acquisition.engine` | Orchestrate page acquisition strategy (L0-L5) | `AdaptiveAcquisitionEngine.acquire_page` | `HTTPFetcher`, `BrowserPoolManager` | `STABLE` |
| **Acquisition** | `scraper.acquisition.http_fetcher` | Direct async HTTP client with SSRF pre-checks | `HTTPFetcher.fetch` | `httpx`, `SecurityConfig` | `STABLE` |
| **Acquisition** | `scraper.acquisition.browser_pool` | Playwright Chromium pool manager | `BrowserPoolManager.fetch_page` | `playwright` | `STABLE` |
| **Acquisition** | `scraper.acquisition.page_classifier` | Calculate Page Intelligence metrics | `PageClassifier.classify_page` | `selectolax` | `STABLE` |
| **Acquisition** | `scraper.acquisition.media_downloader` | Async media asset downloader | `MediaDownloader.download` | `httpx` | `STABLE` |
| **Control** | `scraper.control.scheduler` | Priority request queue & Crawl Frontier | `RequestFrontier.add_request` | `Redis`, `CrawlRequest` | `STABLE` |
| **Control** | `scraper.control.rate_limiter` | Token bucket host rate limiting | `HostRateLimiter.acquire` | `RateLimitConfig` | `STABLE` |
| **Control** | `scraper.control.budget` | Resource limit tracking per crawl job | `BudgetTracker.check_and_consume` | `BudgetConfig` | `STABLE` |
| **Discovery** | `scraper.discovery.links` | Link extraction & sitemap parsing | `extract_links_from_html` | `selectolax`, `bs4` | `STABLE` |
| **Discovery** | `scraper.discovery.seed_finder` | Multi-source seed discovery | `discover_diverse_seeds` | `httpx` | `STABLE` |
| **Extraction** | `scraper.extraction.markdown` | HTML-to-Clean-Markdown conversion | `convert_html_to_markdown` | `trafilatura`, `markdownify` | `STABLE` |
| **Extraction** | `scraper.extraction.table_extractor` | HTML/Markdown table parser | `extract_tables_from_html` | `bs4`, `selectolax` | `STABLE` |
| **Extraction** | `scraper.extraction.self_healing` | Self-healing CSS selector matcher | `SelfHealingSelectorEngine` | `selectolax` | `STABLE` |
| **Extraction** | `scraper.extraction.ocr` | Tesseract OCR visual text extraction | `OCREngine.extract_text` | `pytesseract`, `PIL` | `STABLE` |
| **Normalization** | `scraper.normalization.canonicalizer` | Canonical URL formatting & param stripping | `canonicalize_url` | `urllib.parse` | `STABLE` |
| **Normalization** | `scraper.normalization.deduplicator` | BLAKE3 hashing & SimHash distance | `Deduplicator.compute_hashes` | `zstandard`, `blake3` | `STABLE` |
| **Storage** | `scraper.storage.cas` | Content Addressable Storage engine | `ContentAddressableStore.put` | `zstandard` | `STABLE` |
| **Storage** | `scraper.storage.db` | SQLAlchemy ORM models & session factory | `get_async_session`, ORM Models | `sqlalchemy` | `STABLE` |
| **Storage** | `scraper.storage.vector_store` | Qdrant vector store adapter | `VectorStoreAdapter` | `qdrant-client` | `STABLE` |
| **Pipeline** | `scraper.pipeline.search_pipeline` | Autonomous research pipeline execution | `DeepSearchPipeline.execute` | `AdaptiveAcquisitionEngine` | `STABLE` |
| **MCP** | `scraper.mcp.server` | FastMCP stdio server | `run_mcp_server` | `mcp` | `STABLE` |
| **Monitoring** | `scraper.monitoring.telemetry` | Telemetry metrics & Prometheus | `telemetry.record_request` | `prometheus_client` | `STABLE` |
| **API** | `scraper.api.routes` | REST API endpoint handlers | `router` | `fastapi` | `STABLE` |
| **CLI** | `scraper.cli.main` | Command line application | `app` | `typer`, `rich` | `STABLE` |
