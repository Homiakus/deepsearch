# Audit Report (Architecture & Code Quality Baseline)

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  
**Audit Date:** 2026-09-02  
**Release Status:** `1.0.0-rc1` (DS-01 .. DS-26 verified)  
**Orchestration Engine:** Axiom ADGO (`github.com/Homiakus/axiom/adgo`)  

---

## 1. Executive Summary

The DeepSearch codebase has undergone a full refactoring and stabilization loop across all functional layers:
1. **Unified Surface Boundary**: CLI, REST (`/api/v1`), and MCP endpoints share common request/result models routed via `DeepSearchService`.
2. **Security & Boundary Isolation**: Strict SSRF prevention (`URLPolicy`), non-root container sandboxing, and hermetic unit testing.
3. **Observability & Metrics**: Prometheus metrics (`/metrics`, `/metrics/summary`), real-time HTML dashboard (`/dashboard`), and structured context logs.
4. **Performance Budgets**: Quantified throughput (>50 pages/sec), bounded concurrency semaphores, and N+1 query elimination.
5. **Release & Documentation Audit**: OpenAPI 3.0 specification (`docs/openapi.yaml`), synchronized CLI/MCP documentation, and changelog.

---

## 2. Subsystem Status Matrix

| Subsystem | Primary Path | Classification | Status |
| :--- | :--- | :--- | :--- |
| `application/service.py` | Unified application composition root | `ACTIVE` | Operational & Lifecycle Managed |
| `orchestration/` | Axiom ADGO remote worker & coordinator | `ACTIVE` | Operational |
| `security/url_policy.py` | Comprehensive SSRF & network policy | `ACTIVE` | Verified & Enforced |
| `control/rate_limiter.py` | Host rate limiter & concurrency bounds | `ACTIVE` | Enforced |
| `control/budget.py` | Resource metering & hard limit enforcement | `ACTIVE` | Enforced |
| `retrieval/` | FastEmbed dense/sparse & Qdrant hybrid search | `ACTIVE` | Integrated |
| `evidence/` | Claims, contradiction analysis & coverage | `ACTIVE` | Integrated |
| `acquisition/` | Bounded fetching, adaptive engine & media discovery | `ACTIVE` | Integrated & Tested |
| `monitoring/telemetry.py` | Prometheus metrics and counter collection | `ACTIVE` | Verified |
| `ui/dashboard.py` | Self-contained operational web dashboard | `ACTIVE` | Verified |
| `mcp/server.py` | Model Context Protocol server | `ACTIVE` | Verified |
| `visual/pixel_rag.py` | Visual multivector retrieval | `ACTIVE` | Integrated |

---

## 3. Top-10 Core Algorithms Contracts, Invariants & Assumptions Registry (§DS-27)

### A-001: URL Canonicalization & Security Boundary (`scraper.security.url_policy`, `scraper.normalization.canonicalizer`)
- **Symbols**: `URLPolicy.is_safe_url(url: str) -> bool`, `Canonicalizer.canonicalize_url(url: str) -> str`
- **Input Contract**: Non-null string; trims whitespace; parses standard HTTP/HTTPS schemes.
- **Output Guarantee**: Normalized URL string (lowercased host, default ports removed, sorted query params) or boolean safety flag.
- **Invariants**: Idempotent (`canonicalize(canonicalize(u)) == canonicalize(u)`). Rejects loopback (`127.0.0.1`, `::1`), private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, IPv4-mapped IPv6).
- **Error Semantics**: Invalid scheme/malformed URI returns `False` or raises typed `InvalidURLError`.
- **Traceability**: [test_canonicalizer.py](file:///d:/Programms/deepsearch/tests/unit/test_canonicalizer.py), [test_ssrf.py](file:///d:/Programms/deepsearch/tests/unit/test_ssrf.py).

### A-002: Content Hashing & Exact Deduplication (`scraper.normalization.content_hash`, `scraper.normalization.deduplicator`)
- **Symbols**: `compute_content_hash(text: str) -> str`, `Deduplicator.is_duplicate(content: str) -> bool`
- **Input Contract**: Text string (arbitrary length, Unicode UTF-8).
- **Output Guarantee**: 64-character lowercase hexadecimal SHA-256 hash string; boolean duplicate status.
- **Invariants**: Whitespace-insensitive normalization prior to hashing. Thread-safe internal memory set.
- **Error Semantics**: Empty or whitespace-only strings produce deterministic empty hash without crashing.
- **Traceability**: [test_deduplicator.py](file:///d:/Programms/deepsearch/tests/unit/test_deduplicator.py).

### A-003: Page Structure & Intelligence Classification (`scraper.analysis.page_classifier`)
- **Symbols**: `PageClassifier.classify_page(html: str, url: str) -> PageClassification`
- **Input Contract**: Raw HTML string and associated source URL.
- **Output Guarantee**: Categorized `PageClassification` (`DOCUMENT`, `HUB`, `AUTH_WALL`, `SPAM`, `EMPTY`).
- **Invariants**: Deterministic heuristics; pure analysis without network side effects.
- **Error Semantics**: Empty or malformed HTML yields `EMPTY` or fallback `DOCUMENT` classification without unhandled exceptions.
- **Traceability**: [test_page_classifier.py](file:///d:/Programms/deepsearch/tests/unit/test_page_classifier.py).

### A-004: Media Discovery & Selection Optimization (`scraper.discovery.media_finder`)
- **Symbols**: `fetch_wikimedia_topic_images(topic: str, max_results: int = 10) -> List[MediaCandidate]`
- **Input Contract**: Topic string, bounded positive integer `max_results <= 50`.
- **Output Guarantee**: Ranked list of `MediaCandidate` models ordered by relevance/resolution.
- **Invariants**: Single batch API query (N+1 query elimination).
- **Error Semantics**: On network failure or upstream 5xx, returns empty list `[]` with telemetry warning, preserving pipeline continuity.
- **Traceability**: [test_media_finder.py](file:///d:/Programms/deepsearch/tests/unit/test_media_selection.py), [test_performance_budgets_ds25.py](file:///d:/Programms/deepsearch/tests/performance/test_performance_budgets_ds25.py).

### A-005: Crawl Scheduling & Frontier Management (`scraper.control.scheduler`)
- **Symbols**: `CrawlScheduler.push(task: CrawlTask)`, `CrawlScheduler.lease() -> Optional[CrawlTask]`
- **Input Contract**: Valid `CrawlTask` with unique URL and depth constraints.
- **Output Guarantee**: Cooperative task leasing with bounded in-flight tracking.
- **Invariants**: Monotonic retry attempts; tasks in terminal state are never re-leased.
- **Error Semantics**: Queue capacity overflow raises `QueueFullError`.
- **Traceability**: [test_scheduler.py](file:///d:/Programms/deepsearch/tests/unit/test_scheduler.py).

### A-006: Host Rate Limiting & Resource Budgeting (`scraper.control.rate_limiter`, `scraper.control.budget`)
- **Symbols**: `HostRateLimiter.acquire(host: str)`, `BudgetTracker.consume(bytes_read: int, requests: int = 1)`
- **Input Contract**: Target hostname string; positive resource increments.
- **Output Guarantee**: Rate-limited acquisition slot; budget verification.
- **Invariants**: Token bucket replenishment based on monotonic clock; atomic budget check-and-consume.
- **Error Semantics**: Budget exhaustion raises `BudgetExhaustedError`; rate limiter enforces async sleep delay.
- **Traceability**: [test_rate_limiter.py](file:///d:/Programms/deepsearch/tests/unit/test_rate_limiter.py), [test_budget.py](file:///d:/Programms/deepsearch/tests/unit/test_budget.py).

### A-007: Query Decomposition & Research Planning (`scraper.research.decomposer`)
- **Symbols**: `QueryDecomposer.decompose(goal: str) -> List[SubQuery]`
- **Input Contract**: Natural language research query / goal string.
- **Output Guarantee**: Non-empty list of targeted, orthogonal sub-queries.
- **Invariants**: Deterministic decomposition for fixed input without external model dependency.
- **Error Semantics**: Blank goal input returns single fallback sub-query.
- **Traceability**: [test_query_intelligence.py](file:///d:/Programms/deepsearch/tests/unit/test_query_intelligence.py).

### A-008: Deterministic Extraction Engine (`scraper.extraction.engine`)
- **Symbols**: `ExtractionEngine.extract_from_html(url: str, raw_html: str) -> ExtractionResult`
- **Input Contract**: Target URL string and raw HTML payload.
- **Output Guarantee**: Fully populated `ExtractionResult` (`clean_markdown`, `tables`, `extracted_records`).
- **Invariants**: Zero-copy/streamable string transformations; provenance tracking per extracted field.
- **Error Semantics**: Parser handles malformed or truncated HTML gracefully.
- **Traceability**: [test_extraction_and_archive_ds15.py](file:///d:/Programms/deepsearch/tests/unit/test_extraction_and_archive_ds15.py).

### A-009: Adaptive Acquisition & Browser Escalation (`scraper.acquisition.engine`)
- **Symbols**: `AdaptiveAcquisitionEngine.acquire(url: str) -> AcquisitionResult`
- **Input Contract**: Safe, canonical HTTP/HTTPS URL.
- **Output Guarantee**: Clean payload or typed failure reason.
- **Invariants**: Tiers: HTTPX fetch -> Headless Browser on dynamic JS / anti-bot detection; resource cleanup on cancel.
- **Error Semantics**: Connection timeout or 4xx/5xx produces structured `AcquisitionFailure` rather than crashing worker.
- **Traceability**: [test_acquisition_engine.py](file:///d:/Programms/deepsearch/tests/unit/test_acquisition_engine.py).

### A-010: Content-Addressable Storage & Archive Packaging (`scraper.storage.cas`, `scraper.storage.archive_exporter`)
- **Symbols**: `CASStore.put(data: bytes) -> str`, `ArchiveExporter.export(job_id: str, records: List[dict]) -> Path`
- **Input Contract**: Byte payload or validated extraction records list.
- **Output Guarantee**: SHA-256 digest address; filesystem path to `.tar.zst` archive with manifest.
- **Invariants**: Content immutability in CAS; atomic write to archive via temporary file renaming.
- **Error Semantics**: I/O error or missing directory raises typed `StorageIOError`.
- **Traceability**: [test_cas.py](file:///d:/Programms/deepsearch/tests/unit/test_cas.py), [test_archive_evidence.py](file:///d:/Programms/deepsearch/tests/unit/test_archive_evidence.py).

