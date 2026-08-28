# DeepSearch Platform Roadmap

**Status:** Canonical Roadmap (§DS-01)  
**Readiness Tiers:** `Stable` (verified end-to-end), `Experimental` (active implementation), `Disabled / Planned` (specification in REFACTOR_PLAN).

---

## 🟢 1. Stable Features (Verified in Core Pipeline)

- [x] **Autonomous Research Pipeline**: End-to-end multi-provider discovery (ArXiv, Europe PMC, PubMed, Wikipedia, Anna's Archive), adaptive acquisition, extraction, and dual-format `.zip` export with `files/` and `rag/` LLM context.
- [x] **Page Intelligence & Inspection**: Runtime DOM scoring of static markup, JS dependency, API availability, and strategy selection.
- [x] **Multi-Interface Access**: Single application service behind Typer CLI (`scraper`), FastAPI REST service (`:8080`), and FastMCP stdio server.
- [x] **Markdown & Table Extraction**: Trafilatura/selectolax extraction producing Clean Markdown, Fit Markdown, and tables (CSV/JSON/MD).
- [x] **Content Addressable Storage (CAS)**: Local filesystem CAS compressed with `zstandard` and keyed by BLAKE3 / SHA-256 hash.
- [x] **URL Canonicalization & Deduplication**: Tracking parameter stripping (`utm_*`, `fbclid`), exact content hashing, and 64-bit SimHash near-deduplication.
- [x] **Academic Discovery Providers**: Integrated OpenAlex, Crossref, Semantic Scholar, Europe PMC, PubMed, and ArXiv discovery.
- [x] **Direct Open Access PDF Resolver**: Unpaywall and DOI-based automated PDF retrieval.
- [x] **Obsidian / Zotero Export**: Direct export of research pipeline archives to Obsidian Knowledge Vaults and Zotero CSL-JSON / RIS.

---

## 🟡 2. Experimental Features

- [ ] **Hybrid Search Engine**: Dense semantic (FastEmbed) and sparse lexical retrieval over local Qdrant index. Returns explicit `INDEX_EMPTY` / `NOT_CONFIGURED` state when unpopulated.
- [ ] **Host Rate Limiting & Resource Budgeting**: Token bucket rate limiter and budget tracker (formal integration across all network boundaries in DS-06, DS-07).
- [ ] **Rust Acquisition Worker Core**: Contracts, planner, security boundary, registry, local API and HTTP execution skeleton exist, but browser/crawler capabilities must not be considered production-ready until the runtime reality gates pass.
- [ ] **Acquisition Runtime Reality Gate (P0)**: Make backend descriptors truthful, add executable capability-conformance tests, and prevent STUB engines from active routing. Tracked in `docs/architecture/RUST_BROWSER_EXECUTION_PLAN_ADDENDUM_2026-08-27.md` (`DS-RB56`–`DS-RB59`).
- [ ] **Real Spider.rs Execution Backend (P0)**: Replace the current HTTP wrapper named `SpiderBackend` with an actual Spider.rs adapter while keeping `RankedFrontier` as the research-level scheduler. Tracked in `DS-RB60`–`DS-RB65`.
- [ ] **Real Rust Chromium/CDP Backend (P0)**: Replace the current HTTP fallback implementation behind `ChromiumBackend` with actual browser execution, capability conformance, bounded pooling and crash recovery. Tracked in `DS-RB66`–`DS-RB69`.

---

## 🔴 3. Disabled / Planned Features (Tracked in `docs/architecture/REFACTOR_PLAN.md` and acquisition addendum)

- [ ] **Scrapling Difficult-Page Fallback**: Optional high-cost fallback tier for explicitly classified difficult/protected pages; must remain outside the normal HTTP hot path and pass security/resource gates (`DS-RB70`–`DS-RB73`).
- [ ] **Crawlee Ownership Decision**: Either implement a real isolated Crawlee adapter or remove the dependency/name from the production path; do not run a second authoritative frontier (`DS-RB74`–`DS-RB76`).
- [ ] **Acquisition Cost/Utility Routing**: Optimize expected accepted evidence per acquisition cost using persistent version-aware domain telemetry (`DS-RB77`–`DS-RB79`).
- [ ] **Acquisition Test-of-Tests Hardening**: Multidimensional edge-space, differential backend tests, soak/chaos and Rust mutation testing (`DS-RB80`–`DS-RB84`).
- [ ] **PixelRAG Visual Search**: Real VLM multivector model weights (ColPali/Qwen2-VL) integration (currently returns HTTP 501 `capability_unavailable`).
- [ ] **Native PaddleOCR Extraction**: Integration with production OCR runtime (currently disabled when native binaries are absent).
- [ ] **Distributed PostgreSQL & Redis Streams Queue**: High-throughput distributed task queue (DS-13).
