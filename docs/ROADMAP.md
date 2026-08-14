# DeepSearch Platform Roadmap

---

## 🟢 Implemented Features (v1.0.0)

- [x] **Minimal Effective Cost Decision Policy (§2)**: Dynamic routing across L0 Cache, L1 HTTP, L2 API, L3 Playwright Browser, L4-L5 Visual/PixelRAG.
- [x] **Page Intelligence Engine (§7)**: Automatic scoring of `static_score`, `js_dependency_score`, `api_score`, `visual_score`, and canvas detection.
- [x] **Host-Aware Rate Limiter (§12, §23)**: Token bucket algorithm with adaptive feedback on 429/503 responses and full jitter exponential backoff.
- [x] **Resource Budget Tracker (§101)**: Job limits for max pages, depth, bytes, browser seconds, LLM tokens, and visual pages.
- [x] **URL Canonicalization & Stripping (§17)**: Strips tracking parameters (`utm_*`, `fbclid`) and standardizes query components.
- [x] **3-Level Deduplication (§17)**: Canonical URL hash, BLAKE3 content hash, and 64-bit SimHash Hamming distance.
- [x] **Content Addressable Storage (CAS)**: Local filesystem CAS compressed with `zstandard` (`zstd`) and keyed by BLAKE3 hash.
- [x] **Markdown Extraction Pipeline (§35)**: HTML to token-optimized `clean_markdown` and `fit_markdown`.
- [x] **Table Extraction (§36)**: Converts tables simultaneously to HTML, JSON, CSV, and Markdown.
- [x] **Self-Healing Selectors (§60)**: DOM element fingerprinting for auto-repairing broken CSS/XPath selectors.
- [x] **Media Downloader & OCR Engine**: Downloads embedded media and applies Tesseract OCR for visual document extraction.
- [x] **Multi-Source Seed Discovery**: Automatic seed URLs discovery from ArXiv API, Wikipedia (EN/RU), and domain-specific sources.
- [x] **Autonomous Research Pipeline**: End-to-end research execution with structured `.zip` archive output containing `files/` (links & media) and `rag/` (LLM context).
- [x] **Model Context Protocol (MCP) Integration**: Native stdio FastMCP server (`scraper mcp`) exposing `inspect_url`, `crawl_domain`, `extract_markdown`, `hybrid_search`, `run_research_pipeline`, and `discover_seeds`.
- [x] **REST API Server**: FastAPI service with 9 async endpoints and interactive Swagger UI (`/docs`).
- [x] **Typer CLI**: Command line interface for `inspect`, `crawl`, `extract`, `search`, `research`, and `mcp`.
- [x] **Observability**: Prometheus metrics tracking Browser Escalation Ratio and useful data ratio.
- [x] **Security Protection**: SSRF pre-flight DNS resolution blocking private subnets.

---

## 🟡 Short-Term Roadmap (Q3 2026)

- [ ] **Distributed Request Queue Adapter**: Production Redis Streams / Celery task queue backend for high-concurrency distributed crawling.
- [ ] **Expanded VLM Visual Embeddings**: Integration of Qwen2-VL / ColPali for advanced multimodal PixelRAG visual document indexing.
- [ ] **S3 / MinIO CAS Backend Adapter**: Remote object storage backend for compressed CAS buckets.
- [ ] **Dynamic Cookie & Auth Session Persistence**: Vault integration for encrypted session cookies and HTTP headers.

---

## 🔜 Long-Term Vision (Q4 2026 - 2027)

- [ ] **Real-time Streaming Research Web UI**: SSE (Server-Sent Events) live crawling telemetry and visual graph rendering.
- [ ] **Automated OpenAPI Client SDK Generation**: TypeScript and Go client SDK generators for the REST API.
- [ ] **Obsidian / Zotero Exporter Plugin**: Direct export of research pipeline archives to Obsidian vaults and Zotero libraries.
