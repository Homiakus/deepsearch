# Target Architecture Specification

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  
**Target Pattern:** Clean Layered Architecture (Dependency Rule DAG)  

---

## 1. Architectural Layers & Dependency Rule

```text
 ┌───────────────────────────────────────────────────────────────┐
 │                          ENTRYPOINTS                          │
 │      CLI (scraper.cli)       │     REST API (scraper.api)     │
 │      UI (scraper.ui)         │     MCP (scraper.mcp)          │
 └───────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
 ┌───────────────────────────────────────────────────────────────┐
 │                   APPLICATION ORCHESTRATION                   │
 │ (AdaptiveAcquisitionEngine, DeepSearchPipeline, Scheduler)   │
 └───────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
 ┌───────────────────────────────────────────────────────────────┐
 │                         DOMAIN LOGIC                          │
 │ (PageClassifier, Deduplicator, SelfHealingEngine, OCR)        │
 └───────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
 ┌───────────────────────────────────────────────────────────────┐
 │                    CONTRACTS & CONFIGURATION                  │
 │ (PageIntelligence, CapturedArtifact, BaseSettings Config)     │
 └───────────────────────────────┬───────────────────────────────┘
                                 ▲
                                 │
 ┌───────────────────────────────────────────────────────────────┐
 │                    INFRASTRUCTURE ADAPTERS                    │
 │ (ContentAddressableStore, AsyncSQLAlchemy, QdrantAdapter)     │
 └───────────────────────────────────────────────────────────────┘
```

---

## 2. Invariants & Rules

1. **DAG Structure**: Lower-level domain and contract packages MUST NOT import higher-level entrypoints or orchestration logic.
2. **Explicit Data Models**: Pydantic models (`CapturedArtifact`, `PageIntelligence`, `CrawlRequest`) transfer state across boundaries.
3. **SSRF Boundary**: All HTTP fetchers execute DNS pre-checks before opening socket connections.
4. **Resource Bounds**: All concurrency pools support async context managers for clean termination.
