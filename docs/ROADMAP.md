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
- [ ] **Rust Acquisition Worker Sidecar**: Native Rust worker for high-performance HTTP acquisition with zero-copy decompression.

---

## 🔴 3. Disabled / Planned Features (Tracked in `docs/architecture/REFACTOR_PLAN.md`)

- [ ] **PixelRAG Visual Search**: Real VLM multivector model weights (ColPali/Qwen2-VL) integration (currently returns HTTP 501 `capability_unavailable`).
- [ ] **Native PaddleOCR Extraction**: Integration with production OCR runtime (currently disabled when native binaries are absent).
- [ ] **Distributed PostgreSQL & Redis Streams Queue**: High-throughput distributed task queue (DS-13).
