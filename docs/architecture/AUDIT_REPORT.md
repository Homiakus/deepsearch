# Audit Report — Current Architecture Baseline

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  
**Baseline date:** 2026-09-06  
**Previous baseline:** 2026-09-02 / DS-34  
**Detailed current audit:** [`ARCHITECTURAL_LEVERAGE_AND_FRAGILITY_AUDIT_2026-09-06.md`](./ARCHITECTURAL_LEVERAGE_AND_FRAGILITY_AUDIT_2026-09-06.md)

---

## 1. Executive status

DeepSearch is a strong but still converging polyglot architecture. The repository now contains:

- Go + Axiom ADGO durable orchestration;
- Python research/application pipeline;
- Rust acquisition worker plane;
- SncSinCore epistemic memory integration;
- ranked frontier, budgets and rate limiting;
- deterministic extraction and structured archives;
- vector retrieval and epistemic query paths;
- property/state/fault/mutation-oriented reliability tooling.

The major architecture risk is no longer absence of subsystems. It is **parallel ownership**: more than one component can own research lifecycle, retrieval authority or epistemic state.

The current hardening strategy is therefore:

```text
one execution owner  -> Axiom ADGO
one canonical knowledge promotion path -> Candidate SIH -> Gate -> Canonical SIH
one verified evidence authority -> SncSinCore
one terminal acquisition security policy -> all backends
```

The detailed evidence, risk analysis and implementation plan are maintained in the linked 2026-09-06 audit.

---

## 2. Correction to the previous “FI = 0” claim

The 2026-09-02 audit stated that all fragility classes were closed, the overall Fragility Index was zero and the full Python/Rust/Go verification was green.

That statement must now be treated as **historical evidence for the earlier revision, not as a current release fact**.

After the SncSinCore integration on head `0d81d18a33956c6d60db95d4f9bd904a78025966`, the mutation workflow does not pass its baseline in all languages:

- Python baseline: one failing archive-path sanitization test;
- Go baseline: dependency resolution for `github.com/Homiakus/SncSinCore` fails on the clean GitHub runner before tests/mutations execute;
- Rust baseline: passes.

Therefore:

```text
current residual FI != proven zero
```

A fragility class may only be marked closed when its verification gates execute successfully on the architecture revision being released.

---

## 3. Current subsystem classification

| Subsystem | Path | Current role | Audit state |
| --- | --- | --- | --- |
| Public application boundary | `scraper/application/service.py` | REST/CLI/MCP composition | ACTIVE |
| Python research lifecycle | `scraper/application/research_service.py` | In-memory run owner | FRAGILE / must become adapter |
| Axiom ADGO | `orchestrator/` | Durable workflow/control plane | ACTIVE / target canonical owner |
| Rust acquisition worker | `rust/acquisition-worker/` | High-throughput acquisition | ACTIVE / evolving |
| Adaptive acquisition | `scraper/acquisition/` | HTTP/browser/external fallback | ACTIVE / security hardening required |
| Ranked frontier | `scraper/control/ranked_frontier.py` | Crawl scoring/leasing | ACTIVE / lease/backpressure hardening required |
| Candidate extraction | `scraper/extraction/` | Deterministic/heuristic structure extraction | ACTIVE |
| SIH compiler | `scraper/extraction/sih_compiler.py` | Candidate epistemic structure generation | ACTIVE / must not directly define canonical truth |
| SncSinCore integration | `orchestrator/internal/epistemic/` | Epistemic graph/query engine | ACTIVE / persistence & isolation hardening required |
| Epistemic Python client | `scraper/retrieval/epistemic_client.py` | SncSin transport/fallback | ACTIVE / fail-open semantics must be removed |
| Vector retrieval | `scraper/search/search_engine.py` | Dense/sparse retrieval/rerank | ACTIVE / should become candidate-generation layer |
| Archive exporter | `scraper/storage/archive_exporter.py` | Research evidence package | ACTIVE / should consume canonical SIH artifact |

---

## 4. P0 architectural risks

### FRAG-CP-001 — Dual research control plane

`DefaultResearchApplicationService` owns runs in Python memory and directly executes `DeepSearchPipeline`, while Axiom ADGO separately provides durable execution.

**Required closure:** all public research lifecycle operations route through Axiom `StartOrLoad` and durable state.

Tracked as **DS-43**.

### FRAG-EPI-001 — Candidate knowledge can be mistaken for canonical knowledge

Current SIH compilation derives high fixed belief/evidence values from Markdown structure.

**Required closure:** separate Candidate SIH from Canonical SIH with an explicit canonicalization/promotion gate.

Tracked as **DS-44**.

### FRAG-EPI-002 — Fail-open epistemic fallback

When the SncSin daemon is unavailable, the Python client can create accepted lexical-match paths with strong scores and full coverage semantics.

**Required closure:** explicit assurance levels and fail-closed verified mode; fallback is never semantically equivalent to verified SncSin output.

Tracked as **DS-45**.

### FRAG-CONC-001 — Lease expiry can duplicate work

The local frontier can requeue expired leases without a fencing/heartbeat mechanism while slow work may still be executing.

**Required closure:** Axiom-owned executable leases or lease ID + fencing token + heartbeat.

Tracked as **DS-46**.

### FRAG-CONC-002 — Domain concurrency bound is currently soft

When every candidate domain is saturated, the frontier can fall back to leasing the first item anyway.

**Required closure:** wait rather than violate `max_active_per_domain`.

Tracked as **DS-46**.

### FRAG-SEC-001 — Acquisition security semantics are not fully terminal

The HTTP fetcher contains a TLS path with certificate verification disabled, and acquisition fallback topology needs a typed terminal policy error contract.

**Required closure:** TLS verification on in production and `POLICY_VIOLATION -> never escalate` across HTTP/browser/Rust/external/media paths.

Tracked as **DS-47**.

---

## 5. P1 architectural risks

### FRAG-RET-001 — Two retrieval authorities

Vector/hybrid search can still produce final evidence-like search results independently of SncSinCore.

**Target:** vector/lexical/rerank layers generate recall candidates; SncSinCore determines verified evidence status.

Tracked as **DS-48**.

### FRAG-DEDUP-001 — SimHash candidate completeness cliff

The current four-block near-duplicate prefilter is not complete for all fingerprints within the configured Hamming threshold after the brute-force fallback stops applying at larger corpus sizes.

**Target:** completeness-preserving MIH/multi-probe scheme with brute-force differential property tests.

Tracked as **DS-49**.

### FRAG-EPI-003 — Full corpus rebuild on incremental ingestion

The Go epistemic wrapper reconstructs/reopens the complete corpus for each ingestion delta.

**Target:** incremental persistent SncSin corpus with WAL/snapshots/versioning.

Tracked as **DS-50**.

### FRAG-EPI-004 — `run_id` is not a true memory isolation key

Run-scoped exploratory knowledge and shared canonical knowledge are not yet separate storage concepts.

**Target:** `RunWorkspace -> promotion -> CanonicalMemory`.

Tracked as **DS-51**.

### FRAG-ASYNC-001 — Unowned pipeline tasks

Some binary expansion work is created with fire-and-forget `asyncio.create_task` semantics.

**Target:** structured concurrency, budget ownership and deterministic cancellation.

Tracked as **DS-52**.

---

## 6. Canonical target architecture

```text
CLI / REST / MCP
       |
       v
Application API
       |
       v
Axiom ADGO
canonical run owner
       |
       +----------+-----------+
       |          |           |
       v          v           v
   Discovery  Acquisition  Extraction
                  |           |
             Rust worker      v
                           Candidate SIH
                                |
                                v
                       Canonicalization Gate
                                |
                         accept / quarantine
                                |
                                v
                           Canonical SIH
                                |
                                v
                            SncSinCore
                                |
          vector/lexical candidates + graph activation
                                |
                                v
                     verified evidence artifact
```

See [`TARGET_ARCHITECTURE.md`](./TARGET_ARCHITECTURE.md) for normative architecture rules.

---

## 7. Current hardening roadmap

| ID | Priority | Objective |
| --- | --- | --- |
| DS-43 | P0 | Make Axiom the canonical research lifecycle owner |
| DS-44 | P0 | Candidate SIH -> Canonicalization Gate -> Canonical SIH |
| DS-45 | P0 | Explicit assurance levels and fail-closed verified semantics |
| DS-46 | P0 | Frontier fencing, heartbeat and hard domain backpressure |
| DS-47 | P0 | Unified terminal acquisition security boundary |
| DS-48 | P1 | Retrieval candidates separated from epistemic authority |
| DS-49 | P1 | Correct completeness-preserving near-duplicate index |
| DS-50 | P1 | Incremental persistent SncSin corpus |
| DS-51 | P1 | Run workspace to canonical memory promotion |
| DS-52 | P1 | Structured concurrency / no unowned async work |

Full implementation details and acceptance criteria are in [`ARCHITECTURAL_LEVERAGE_AND_FRAGILITY_AUDIT_2026-09-06.md`](./ARCHITECTURAL_LEVERAGE_AND_FRAGILITY_AUDIT_2026-09-06.md).

---

## 8. Release definition of done after this audit

A production-readiness claim requires current-revision evidence for all of the following:

- [ ] Axiom is the sole production research lifecycle owner.
- [ ] Candidate SIH cannot write directly into canonical knowledge.
- [ ] Verified epistemic responses cannot silently degrade to lexical fallback.
- [ ] Run/corpus isolation is explicit.
- [ ] Acquisition policy violations are terminal across every backend.
- [ ] Production TLS verification is enabled.
- [ ] Domain concurrency is a hard bound.
- [ ] Lease expiry cannot create two accepted executions for the same generation.
- [ ] No pipeline stage leaves unowned background tasks.
- [ ] Near-duplicate lookup is differential-tested against brute force.
- [ ] SncSin state survives restart/replay with deterministic corpus identity.
- [ ] Python, Go and Rust baselines pass from clean checkout.
- [ ] Mutation tests execute after baseline and leave zero critical surviving mutants.

Until those gates are demonstrated, DeepSearch should be described as **architecturally advanced with explicit P0/P1 hardening work**, rather than as a zero-fragility completed release.
