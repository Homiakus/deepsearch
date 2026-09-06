# Migration Plan

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  

---

## Migration Status

- [x] **Phase 1: Legacy Codebase Replacement**: Legacy Go documents and contracts replaced with Python 3.11+ `scraper` platform specs.
- [x] **Phase 2: Core Subsystems Alignment**: Unified `scraper.acquisition`, `scraper.control`, `scraper.extraction`, `scraper.normalization`, `scraper.storage`.
- [x] **Phase 3: Extended Features Integration**: Media Downloader, Tesseract OCR, Multi-source Seed Discovery, DeepSearch Research Pipeline.
- [x] **Phase 4: Interface & Agent Integration**: Typer CLI, FastAPI REST endpoints, FastMCP stdio server.
- [x] **Phase 5: Polyglot & Epistemic Integration**: Axiom ADGO Go orchestrator, Rust acquisition worker plane and SncSinCore epistemic integration introduced.
- [ ] **Phase 6: Canonical Architecture Hardening (DS-43..DS-52)**: collapse parallel control/evidence paths into one execution and knowledge-promotion spine.

---

## Phase 6 — Canonical Architecture Hardening

Detailed rationale, fragility analysis and acceptance criteria: [`ARCHITECTURAL_LEVERAGE_AND_FRAGILITY_AUDIT_2026-09-06.md`](./ARCHITECTURAL_LEVERAGE_AND_FRAGILITY_AUDIT_2026-09-06.md).

Execution order:

1. **DS-43 / P0 — Canonical Axiom Research Ownership**  
   Route all production research lifecycle operations through Axiom ADGO; eliminate Python in-memory lifecycle as an authority.

2. **DS-44 / P0 — Candidate SIH -> Canonicalization Gate -> Canonical SIH**  
   Prevent heuristic extraction from writing directly into canonical knowledge.

3. **DS-45 / P0 — Epistemic Assurance & Fail-Closed Semantics**  
   Make degraded/unverified fallback explicit and impossible to confuse with SncSinCore-verified evidence.

4. **DS-46 / P0 — Frontier Lease/Fencing/Backpressure**  
   Enforce hard domain concurrency and stale-worker fencing.

5. **DS-47 / P0 — Unified Acquisition Security Boundary**  
   Make policy failures terminal across all acquisition backends and require production TLS verification.

6. **DS-48 / P1 — Retrieval Candidate/Authority Separation**  
   Keep vector/lexical retrieval as a recall layer and require epistemic validation for final evidence.

7. **DS-49 / P1 — Correct Near-Duplicate Multi-Index Search**  
   Remove the corpus-size correctness cliff and prove candidate completeness against brute force.

8. **DS-50 / P1 — Incremental Persistent SncSin Corpus**  
   Replace full-corpus rebuild ingestion with versioned incremental commits, persistence and deterministic replay.

9. **DS-51 / P1 — Run Workspace -> Canonical Memory Promotion**  
   Separate exploratory run-scoped knowledge from shared canonical memory.

10. **DS-52 / P1 — Structured Concurrency**  
    Remove unowned background tasks and bind all child work to lifecycle, cancellation and budgets.

### Phase 6 release gate

Phase 6 is complete only when:

- all public research execution is Axiom-owned;
- canonical knowledge can only enter through the promotion gate;
- verified evidence never silently degrades;
- security policy failures cannot escape through backend fallback;
- lease/domain concurrency invariants pass stateful tests;
- no unowned async work remains;
- near-duplicate lookup matches brute-force correctness inside the configured threshold;
- SncSin state is persistent/replayable;
- clean Python, Go and Rust baselines are green;
- mutation gates execute on the same release revision with zero critical surviving mutants.
