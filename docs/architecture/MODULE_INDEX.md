# Module Index

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  

---

### Status Legend
- `ACTIVE`: Participates in the primary execution path and has test verification.
- `EXPERIMENTAL`: Available via explicit opt-in / feature flag.
- `STUB`: API exists as a baseline interface, being replaced with real implementation.
- `DEPRECATED`: Retained only during migration to Axiom ADGO and unified application boundary.

---

| Subsystem / Package | Module Name | Primary Responsibility | Public Interface | Key Dependencies | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Application** | `scraper.application.research_service` | Single application boundary for Research | `ResearchApplicationService` | `pydantic` | `ACTIVE` |
| **Config** | `scraper.config` | Central BaseSettings & sub-configurations | `settings`, `ExecutionMode` | `pydantic-settings` | `ACTIVE` |
| **Acquisition** | `scraper.acquisition.engine` | Orchestrate page acquisition strategy (L0-L5) | `AdaptiveAcquisitionEngine.acquire_page` | `HTTPFetcher`, `BrowserPoolManager` | `ACTIVE` |
| **Acquisition** | `scraper.acquisition.http_fetcher` | Direct async HTTP client with SSRF pre-checks | `HTTPFetcher.fetch` | `httpx`, `SecurityConfig` | `ACTIVE` |
| **Acquisition** | `scraper.acquisition.browser_pool` | Playwright Chromium pool manager | `BrowserPoolManager.fetch_page` | `playwright` | `ACTIVE` |
| **Acquisition** | `scraper.acquisition.crawlee_adapter` | Crawlee RequestQueue bounded crawl engine | `CrawleeBatchCrawler` | `crawlee` | `ACTIVE` |
| **Acquisition** | `scraper.acquisition.page_classifier` | Calculate Page Intelligence metrics | `PageClassifier.classify_page` | `selectolax` | `ACTIVE` |
| **Acquisition** | `scraper.acquisition.media_downloader` | Async media asset downloader | `MediaDownloader.download` | `httpx` | `ACTIVE` |
| **Control** | `scraper.control.scheduler` | Priority request queue & Crawl Frontier | `RequestFrontier.add_request` | `Redis`, `CrawlRequest` | `DEPRECATED` |
| **Control** | `scraper.control.rate_limiter` | Token bucket host rate limiting | `HostRateLimiter.acquire` | `RateLimitConfig` | `ACTIVE` |
| **Control** | `scraper.control.budget` | Resource limit tracking per crawl job | `BudgetTracker.check_and_consume` | `BudgetConfig` | `ACTIVE` |
| **Security** | `scraper.security.url_policy` | Unified URL validation & SSRF defense | `URLSecurityPolicy` | `ipaddress`, `socket` | `ACTIVE` |
| **Discovery** | `scraper.discovery.providers` | Multi-source discovery provider registry | `DiscoveryProviderRegistry` | `httpx` | `ACTIVE` |
| **Extraction** | `scraper.extraction.markdown` | HTML-to-Clean-Markdown conversion | `convert_html_to_markdown` | `trafilatura`, `markdownify` | `ACTIVE` |
| **Extraction** | `scraper.extraction.table_extractor` | HTML/Markdown table parser | `extract_tables_from_html` | `bs4`, `selectolax` | `ACTIVE` |
| **Extraction** | `scraper.extraction.self_healing` | Self-healing CSS selector matcher | `SelfHealingSelectorEngine` | `selectolax` | `ACTIVE` |
| **Extraction** | `scraper.extraction.ocr` | Tesseract OCR visual text extraction | `OCREngine.extract_text` | `pytesseract`, `PIL` | `ACTIVE` |
| **Domain** | `scraper.domain.document` | Structured Document representation | `Document`, `Section`, `TableBlock` | `pydantic` | `ACTIVE` |
| **Retrieval** | `scraper.retrieval.chunking` | Structure-aware hierarchical chunking | `StructureAwareChunker` | `re` | `ACTIVE` |
| **Retrieval** | `scraper.retrieval.embeddings` | Dense and sparse vector generation | `EmbeddingEngine` | `fastembed` | `ACTIVE` |
| **Retrieval** | `scraper.retrieval.reranker` | Cross-encoder reranking | `Reranker` | `fastembed` | `ACTIVE` |
| **Evidence** | `scraper.evidence.store` | Evidence, claims and contradiction store | `EvidenceStore` | `pydantic` | `ACTIVE` |
| **Normalization** | `scraper.normalization.canonicalizer` | Canonical URL formatting & param stripping | `canonicalize_url` | `urllib.parse` | `ACTIVE` |
| **Normalization** | `scraper.normalization.deduplicator` | BLAKE3 hashing & SimHash distance | `Deduplicator.compute_hashes` | `zstandard`, `blake3` | `ACTIVE` |
| **Storage** | `scraper.storage.cas` | Content Addressable Storage engine | `ContentAddressableStore.put` | `zstandard` | `ACTIVE` |
| **Storage** | `scraper.storage.db` | SQLAlchemy ORM models & session factory | `get_async_session`, ORM Models | `sqlalchemy` | `ACTIVE` |
| **Storage** | `scraper.storage.vector_store` | Qdrant vector store adapter | `VectorStoreAdapter` | `qdrant-client` | `ACTIVE` |
| **Orchestration** | `scraper.orchestration.axiom_worker` | Python worker client for Axiom ADGO | `AxiomRemoteWorker` | `httpx` | `ACTIVE` |
| **Visual** | `scraper.visual.pixel_rag` | Vision-Language multi-vector retrieval | `PixelRAGEngine` | `PIL` | `EXPERIMENTAL` |
| **Pipeline** | `scraper.pipeline.search_pipeline` | Autonomous research pipeline execution | `DeepSearchPipeline.execute` | `AdaptiveAcquisitionEngine` | `DEPRECATED` |
| **MCP** | `scraper.mcp.server` | FastMCP stdio server | `run_mcp_server` | `mcp` | `ACTIVE` |
| **Monitoring** | `scraper.monitoring.telemetry` | Telemetry metrics & Prometheus | `telemetry.record_request` | `prometheus_client` | `ACTIVE` |
| **API** | `scraper.api.routes` | REST API endpoint handlers | `router` | `fastapi` | `ACTIVE` |
| **CLI** | `scraper.cli.main` | Command line application | `app` | `typer`, `rich` | `ACTIVE` |
