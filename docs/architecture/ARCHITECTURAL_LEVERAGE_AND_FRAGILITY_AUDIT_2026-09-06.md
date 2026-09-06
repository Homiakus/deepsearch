# DeepSearch Architectural Leverage & Fragility Audit

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  
**Audit date:** 2026-09-06  
**Audited branch:** `main`  
**Audited head before this document:** `0d81d18a33956c6d60db95d4f9bd904a78025966`  
**Scope:** architecture, runtime ownership, epistemic integrity, concurrency, security boundaries, retrieval semantics, scaling cliffs, CI evidence.

---

## 1. Executive conclusion

DeepSearch has accumulated several strong subsystems: Axiom ADGO durable orchestration, Python research logic, a Rust acquisition worker plane, SncSinCore epistemic memory, a ranked crawl frontier, structured extraction, archive generation, vector retrieval, and a substantial reliability test suite.

The highest-value next step is **not adding more capabilities**. It is collapsing the system around a single execution spine and a single epistemic truth path.

The target invariant is:

```text
Axiom owns WHEN/WHAT executes.
SncSinCore owns WHAT may be treated as canonical knowledge.
Rust owns high-throughput acquisition execution.
Python owns research algorithms, adaptation and domain logic.
```

At the moment, several of these responsibilities are implemented twice or can bypass one another. That creates architectural fragility despite strong individual components.

### Highest-ROI changes

| Priority | Leverage point | Expected effect |
| --- | --- | --- |
| P0 | Make Axiom ADGO the single owner of research lifecycle | Real durability, recovery, idempotency, cancellation and scale |
| P0 | Introduce `Candidate SIH -> Canonicalization Gate -> Canonical SIH` | Protects epistemic integrity and prevents ingestion errors from becoming “truth” |
| P0 | Remove fail-open epistemic fallback semantics | Prevents degraded lexical matching from being presented as verified evidence |
| P0 | Fix frontier lease/backpressure semantics | Prevents duplicate work, domain-limit violations and concurrency races |
| P0 | Enforce one terminal security boundary for all acquisition backends | Prevents policy failures from being reinterpreted as retryable backend failures |
| P1 | Make vector retrieval candidate-generation only | Unifies search semantics around epistemic validation rather than parallel authorities |
| P1 | Replace current near-duplicate candidate scheme with a completeness-preserving index | Removes a correctness cliff above ~1000 indexed documents |
| P1 | Make SncSin ingestion incremental and persistent | Avoids corpus rebuild scaling cliffs and enables large corpora |

---

## 2. Architectural fragility: two control planes

### Observed state

The target architecture describes the Go Axiom ADGO orchestrator as the durable control plane. The Go path already has the right primitives:

- immutable research plan;
- `StartOrLoad` semantics;
- durable store (`Pebble` in production configuration);
- activity leases, retries and coordinator loop;
- remote worker protocol;
- status and cancellation APIs.

Relevant code:

- `orchestrator/internal/plan/research.go`
- `orchestrator/internal/server/api.go`
- `orchestrator/cmd/deepsearch-orchestrator/main.go`

However, the public Python research path still owns a second lifecycle implementation:

- `scraper/application/research_service.py` stores `_runs`, `_results`, `_idempotency_map` and `_tasks` in process memory;
- `DefaultResearchApplicationService._execute_run()` creates and executes `DeepSearchPipeline` directly;
- API/CLI/MCP can therefore run research without the Go durable owner.

Current effective shape:

```text
REST / MCP / CLI
       |
       +--> Python in-memory ResearchApplicationService --> DeepSearchPipeline
       |
       +--> separate Go Axiom ADGO control plane
```

### Failure modes

1. API process restart loses Python-owned status/results/tasks.
2. Multiple API replicas can disagree about run state.
3. Python idempotency is process-local.
4. Axiom retries, durable checkpoints and lease recovery are bypassed.
5. Cancellation semantics differ by entry path.
6. Testing one path does not prove correctness of the other.

### Required architecture

```text
REST / MCP / CLI
       |
       v
ResearchApplicationPort
       |
       v
Axiom ADGO (canonical run owner)
       |
       +--> Python activity workers
       +--> Rust acquisition workers
       +--> SncSin epistemic activities
```

### Required invariant

> No public research entrypoint may create or own a research execution outside Axiom ADGO.

---

## 3. Epistemic fragility: ingestion currently overstates certainty

`compile_markdown_to_sih()` in `scraper/extraction/sih_compiler.py` currently maps document structure directly into epistemic objects. In particular, headings become propositions with high fixed belief and paragraphs become evidence with high fixed belief/evidence quality.

Structural Markdown position is not evidence confidence.

A paragraph may contain:

- quoted claims;
- negation;
- hypotheses;
- historical claims superseded later in the same document;
- claims attributed to another source;
- contradictory statements;
- uncertainty language;
- conclusions unsupported by the provided text.

If extraction writes these directly into canonical epistemic memory, ingestion error becomes knowledge corruption.

### Required pipeline

```text
Raw document
    |
    v
Deterministic extraction
    |
    v
Candidate SIH
    |
    +-- claim candidates
    +-- evidence spans
    +-- provenance
    +-- uncertainty
    +-- unresolved relations
    |
    v
Canonicalization Gate
    |
    +-- source identity
    +-- claim normalization
    +-- citation grounding
    +-- contradiction detection
    +-- duplicate/entity resolution
    +-- temporal/context validation
    +-- independent-source analysis
    +-- confidence calibration
    |
    +--> reject / quarantine
    |
    v
Canonical SIH
```

### Hard rule

> Probabilistic or heuristic extraction MUST NOT write directly to canonical knowledge.

The archive and runtime memory must be derived from the same accepted canonical artifact so they cannot diverge.

---

## 4. Epistemic fail-open fallback is unsafe

`scraper/retrieval/epistemic_client.py` falls back to an in-memory deterministic simulation when the SncSinCore daemon is unavailable.

The current fallback:

- keeps nodes in process memory;
- does not isolate fallback storage by run/corpus;
- uses lexical token matching;
- creates accepted evidence paths;
- assigns high fixed path scores;
- may report full coverage when lexical matches exist.

This is a dangerous assurance downgrade because transport failure can silently change the meaning of “verified evidence”.

### Required assurance model

Introduce an explicit assurance enum, for example:

```text
VERIFIED
DEGRADED
UNVERIFIED
UNAVAILABLE
```

Required invariant:

```text
DEGRADED != VERIFIED
```

A fallback may preserve UX and produce candidate material, but it MUST NOT emit a response semantically equivalent to a SncSinCore-validated artifact.

Fallback storage, if retained, must be scoped at minimum by:

```text
tenant / corpus / run / document
```

and must never share unqualified global node arrays between independent research executions.

---

## 5. SncSinCore is not yet the mandatory main ingestion path

The research pipeline currently compiles SIH in `ArchiveExporter`, writing `sih/sih_corpus.json` into the exported research artifact. Runtime ingestion exists through the epistemic API/client, but the main research execution does not enforce a canonical SIH commit as an obligatory stage.

This permits two truths:

```text
Research archive SIH != runtime SncSin memory
```

### Required design

```text
Extraction
    |
    v
Candidate SIH
    |
    v
Canonicalization Gate
    |
    v
Canonical SIH Commit
    |\
    | +--> SncSinCore runtime memory
    +----> immutable archive/export
```

The exported SIH must be the exact canonical committed artifact (or a cryptographically linked representation of it), not an independently regenerated structure.

---

## 6. RankedFrontier lease and backpressure fragility

`RankedFrontier` in `scraper/control/ranked_frontier.py` uses expiring leases. A lease can expire while a worker is still processing a slow browser/PDF task. There is no frontier-level heartbeat/fencing token in the local pipeline path.

Possible race:

```text
Worker A leases X
     |
     | processing > lease TTL
     v
lease expires -> X requeued -> Worker B leases X

A and B now execute the same candidate
```

### Required fix

Preferred solution: make Axiom the owner of executable leases and keep RankedFrontier as a deterministic scoring/selection structure.

If local leasing remains, introduce:

- `lease_id`;
- monotonically increasing fencing token;
- heartbeat/renewal;
- completion validation against current fencing token;
- explicit abandoned-lease transition.

### Domain limit violation

`lease_next()` currently falls back to the first queue item if all eligible domains are already at `max_active_per_domain`.

That makes the configured “max” a soft suggestion.

Required behavior:

```text
no eligible candidate
      -> WAIT on condition
```

not “lease anyway”.

---

## 7. `/crawl` currently violates its semantic contract

`JobRequest` contains `max_depth` and `max_pages`, but the in-process `JobService._run_job()` currently acquires only the initial URL and finishes.

Therefore a request that looks like:

```text
/crawl
max_depth=5
max_pages=100
```

can behave as a one-page fetch.

This is a contract integrity issue, not merely an implementation gap.

### Required action

Do not develop a second crawler scheduler inside `JobService`.

Either:

1. temporarily rename/restrict the endpoint to fetch semantics; or
2. route `/crawl` to the same Axiom + RankedFrontier research execution spine.

The preferred target is option 2.

---

## 8. Near-duplicate detector has a correctness cliff

`scraper/normalization/near_duplicate.py` uses a 64-bit SimHash divided into four 16-bit blocks. Candidate generation requires at least one equal block, with a fallback full scan only below a corpus-size threshold (or at larger Hamming thresholds).

For Hamming threshold 12, two fingerprints can differ by exactly three bits in each 16-bit block:

```text
block 1: 3 differences
block 2: 3 differences
block 3: 3 differences
block 4: 3 differences
---------------------
total: 12 differences
```

No block is identical, despite total Hamming distance satisfying the duplicate threshold.

Once the full-scan fallback is disabled for larger collections, such pairs can become false negatives.

### Required property

For every indexed pair `A`, `B`:

```text
Hamming(A, B) <= threshold
    => candidate_generation(A) contains B
```

### Required action

Replace the current prefilter with a completeness-preserving Multi-Index Hash / multi-probe scheme and add property-based differential tests against brute-force Hamming search.

Also remove global cross-run near-duplicate state. Deduplication state should belong to an explicit corpus/run context unless deliberately configured as global canonical deduplication.

---

## 9. Acquisition security boundary is not fully terminal

The central `URLSecurityPolicy` is a strong base, but the acquisition topology still allows policy semantics to be blurred across fallback layers.

### TLS verification

The main HTTP fetcher currently constructs `httpx.AsyncHTTPTransport(... verify=False ...)` on paths used by production acquisition.

For an evidence-oriented system this undermines source integrity.

Required invariant:

```text
TLS verification ON by default and mandatory in production.
```

Any unsafe TLS override must be explicit, development-only and surfaced in telemetry/artifact provenance.

### Terminal policy errors

The adaptive engine can treat a failed HTTP attempt as a reason to try browser/Keenable fallbacks. Security policy failures must never be treated as ordinary acquisition failures.

Introduce a typed failure taxonomy such as:

```text
TRANSIENT
BACKEND_UNAVAILABLE
RATE_LIMIT
CONTENT_FAILURE
POLICY_VIOLATION
```

Hard rule:

```text
POLICY_VIOLATION -> terminal, never escalate to another backend
```

Every backend (HTTP, browser, Rust worker, external fetch service, media downloader) must enter through the same normalized policy decision or provide a proof-equivalent boundary.

---

## 10. Retrieval still has two authorities

`SearchEngine` exposes `search_epistemic()`, but ordinary `search_text`, `search_documents`, `search_evidence` and `search_hybrid` still execute vector retrieval/reranking independently.

The desired architecture is not “vector RAG OR epistemic graph”. The stronger architecture is:

```text
Query
  |
  v
Candidate retrieval
  +-- lexical
  +-- dense vectors
  +-- graph activation
  +-- source priors
  |
  v
large recall-oriented candidate set
  |
  v
SncSinCore evidence-subgraph construction
  |
  v
coverage / contradiction / provenance validation
  |
  v
final verified context artifact
```

Vector retrieval remains valuable, but it becomes a recall engine rather than an epistemic authority.

### Required invariant

> No final “evidence” response may be accepted solely because it ranked highly in dense/sparse retrieval.

---

## 11. SncSin ingestion has an O(N^2)-like growth path

`orchestrator/internal/epistemic/engine.go` currently rebuilds the full in-memory corpus/library on ingestion by copying existing nodes/edges, appending deltas and reopening `epmemory`.

Repeated small ingests therefore repeatedly rebuild growing state.

This is acceptable for small corpora but becomes a scaling cliff for long-running or large knowledge bases.

### Required SncSinCore capability

Move toward:

- incremental graph commits;
- incremental indexes;
- versioned canonical state;
- WAL/snapshot persistence;
- atomic delta validation;
- explicit corpus identifiers;
- deterministic replay.

DeepSearch should submit validated deltas instead of reconstructing the entire corpus.

---

## 12. `run_id` is not yet an isolation boundary for epistemic memory

Transport DTOs contain `run_id`, but the Go epistemic engine ultimately ingests nodes and edges into a single engine corpus without using `run_id` as an isolation key.

Two distinct concepts must be represented explicitly:

```text
RunWorkspace
    |
    | promotion after canonicalization
    v
CanonicalMemory
```

`run_id` should identify a research workspace/provenance scope. Canonical memory should be a separately identified, versioned corpus.

This allows exploratory hypotheses and unresolved contradictions to exist without contaminating shared canonical knowledge.

---

## 13. Structured concurrency violation in pipeline expansion

The crawl expansion path creates fire-and-forget tasks for some binary media downloads using `asyncio.create_task(...)` without retaining/awaiting ownership.

Consequences:

- tasks may outlive their pipeline stage;
- cancellation does not propagate reliably;
- temporary workspace cleanup can race active downloads;
- work can escape PDF/media budgets;
- failures can become unobserved.

### Required pattern

Use structured concurrency (`asyncio.TaskGroup` or equivalent owned task set) with:

- explicit semaphore;
- budget accounting before/after work;
- cancellation propagation;
- bounded queue capacity;
- completion joined before stage exit.

Hard invariant:

> No pipeline stage may spawn unowned background work.

---

## 14. CI evidence invalidates the previous “FI = 0” release assertion

The previous architecture audit recorded a fully green polyglot baseline, zero residual fragility and completed mutation validation.

At audited head `0d81d18a33956c6d60db95d4f9bd904a78025966`, the mutation workflow is not green:

- Python mutation job fails at baseline tests before mutation execution;
- Go mutation job fails at baseline setup because the SncSinCore dependency cannot be resolved by the clean GitHub runner;
- Rust mutation baseline passes.

Therefore the previous statement “all 100% green / FI=0 / ready production release” is not a current fact.

### Required release invariant

```text
clean checkout
    |
    v
all language baselines green
    |
    v
mutation phase actually executes
    |
    v
critical surviving mutants = 0
```

A mutation score from an earlier revision cannot close a fragility risk after major architecture changes unless the relevant gate executes again on the new head.

---

# 15. Target architecture

```text
                 +------------------+
CLI / REST / MCP | Application API  |
                 +---------+--------+
                           |
                           v
                  +-----------------+
                  |   Axiom ADGO    |
                  | canonical run   |
                  | control plane   |
                  +--------+--------+
                           |
            +--------------+---------------+
            |              |               |
            v              v               v
        Discovery      Acquisition      Extraction
                           |
                     Rust workers
                           |
                           v
                     Raw artifacts
                           |
                           v
                      Candidate SIH
                           |
                           v
                 +--------------------+
                 | Canonicalization   |
                 | Gate               |
                 +---------+----------+
                           |
                  reject   | canonical
                     <-----+----->
                           |
                           v
                      SncSinCore
                    Canonical Memory
                           |
               +-----------+-----------+
               |                       |
               v                       v
     vector/lexical candidates    graph activation
               +-----------+-----------+
                           |
                           v
                    Evidence Query
                           |
                           v
                coverage / conflicts
                           |
                           v
                  Context Artifact
                           |
                           v
                    LLM / consumer
```

---

# 16. Implementation roadmap

The following work items extend the existing DS numbering and are intentionally ordered by leverage rather than feature visibility.

## DS-43 — Canonical Axiom Research Ownership

**Priority:** P0  
**Goal:** remove the second in-memory research control plane.

### Changes

- implement `AxiomResearchApplicationService` as the production implementation of `ResearchApplicationService`;
- route REST, CLI and MCP research commands through Axiom `StartOrLoad`;
- map Axiom execution state into existing public DTOs;
- make cancellation/status/result read from the durable execution/store;
- retain local in-process service only as an explicit test/dev adapter, not production default.

### Acceptance criteria

- process restart does not lose run state;
- duplicate idempotency key resolves to the same durable execution;
- two API replicas observe identical state;
- no public research route directly creates `DeepSearchPipeline` execution tasks.

---

## DS-44 — Candidate SIH and Canonicalization Gate

**Priority:** P0

### Changes

- introduce candidate SIH DTOs distinct from canonical SncSin node types;
- preserve exact source spans/provenance;
- represent uncertainty/negation/attribution explicitly;
- implement canonicalization decisions: accept, reject, quarantine, merge, supersede;
- assign confidence only after validation/calibration;
- produce a canonical artifact digest.

### Acceptance criteria

- heuristic extraction cannot directly emit canonical nodes;
- every canonical proposition traces to source spans and canonicalization decision;
- contradiction and negation counterexamples are covered by regression tests.

---

## DS-45 — Epistemic Assurance and Fail-Closed Semantics

**Priority:** P0

### Changes

- add `AssuranceLevel` to epistemic responses;
- mark fallback responses `DEGRADED` or `UNVERIFIED`;
- remove fixed high-confidence fallback scores;
- isolate fallback workspaces by corpus/run;
- allow strict consumers to request `VERIFIED_ONLY`.

### Acceptance criteria

- daemon outage can never return a response indistinguishable from SncSin-verified output;
- no cross-run fallback evidence leakage;
- REST/MCP/CLI expose assurance state consistently.

---

## DS-46 — Frontier Lease, Fencing and Hard Backpressure

**Priority:** P0

### Changes

- move executable leases to Axiom where possible;
- otherwise add lease renewal and fencing tokens;
- make `max_active_per_domain` a hard invariant;
- add state-machine/property tests for lease expiry during active work;
- prove at-most-one accepted completion per fencing generation.

### Acceptance criteria

- no duplicate accepted execution after lease expiry race;
- saturated domains wait instead of violating configured limit;
- cancellation releases leases deterministically.

---

## DS-47 — Unified Acquisition Security Boundary

**Priority:** P0

### Changes

- TLS verification enabled by default and required in production;
- introduce typed acquisition failure classes;
- make policy failures terminal;
- require every HTTP/browser/Rust/external/media acquisition path to apply the central URL policy or a validated equivalent;
- add escalation tests proving `POLICY_VIOLATION` never switches backend.

### Acceptance criteria

- no production path uses `verify=False`;
- SSRF/policy denial cannot be bypassed through a fallback provider;
- security classification survives across worker/process boundaries.

---

## DS-48 — Retrieval Candidate/Authority Separation

**Priority:** P1

### Changes

- define a recall-oriented `CandidateRetriever` contract;
- use dense/sparse/RRF/reranking to produce candidates only;
- pass selected candidates/evidence into SncSinCore query construction;
- make “evidence” endpoints require epistemic validation;
- retain candidate-only endpoints for diagnostic/search UX.

### Acceptance criteria

- final evidence responses contain SncSin artifact/coverage/provenance;
- vector rank alone cannot yield verified status;
- benchmark recall and verification precision separately.

---

## DS-49 — Correct Near-Duplicate Multi-Index Search

**Priority:** P1

### Changes

- replace incomplete 4x16-bit exact-block candidate lookup;
- add brute-force differential oracle tests;
- property-test thresholds across random fingerprints;
- isolate detector state by run/corpus;
- benchmark candidate count and latency at 1k/10k/100k/1M fingerprints.

### Acceptance criteria

- zero false negatives relative to brute-force Hamming search inside configured threshold;
- no discontinuous correctness change at 1000 documents.

---

## DS-50 — Incremental Persistent SncSin Corpus

**Priority:** P1

### Changes

- define corpus identity/version contract;
- submit ingestion deltas rather than full rebuilds;
- add WAL/snapshot/replay semantics in SncSinCore integration;
- make commit idempotent and digest-addressed;
- expose graph/index size and commit latency telemetry.

### Acceptance criteria

- amortized ingestion no longer rebuilds the complete corpus per document;
- crash/restart reproduces the same canonical corpus digest;
- repeated identical delta is idempotent.

---

## DS-51 — Run Workspace -> Canonical Memory Promotion

**Priority:** P1

### Changes

- introduce explicit run workspace identity;
- keep candidate/unresolved knowledge run-scoped;
- implement promotion transaction into canonical corpus;
- maintain provenance from canonical proposition back to originating run/document/spans.

### Acceptance criteria

- independent runs cannot contaminate one another before promotion;
- canonical graph can be reconstructed from accepted promotion events.

---

## DS-52 — Structured Concurrency and Owned Background Work

**Priority:** P1

### Changes

- replace unowned `asyncio.create_task` calls in pipeline stages;
- use `TaskGroup`/owned task registries;
- include media/PDF tasks in run budgets;
- join/cancel all stage work before temporary workspace cleanup.

### Acceptance criteria

- zero unowned tasks after pipeline completion/cancel;
- workspace cleanup cannot race an active downloader;
- fault-injection tests show deterministic cancellation propagation.

---

# 17. Recommended execution order

```text
DS-43  Axiom ownership
  |
  +--> DS-46 frontier/lease semantics
  +--> DS-52 structured concurrency

DS-44  Candidate SIH / Canonicalization
  |
  +--> DS-45 assurance model
  +--> DS-51 workspace promotion
  +--> DS-50 incremental SncSin persistence
  +--> DS-48 retrieval authority separation

DS-47  unified security boundary   (may proceed in parallel)
DS-49  near-duplicate correctness  (may proceed in parallel)
```

The first release gate after this audit should prioritize DS-43 through DS-47 before new user-visible features.

---

# 18. Updated architecture principles

1. **One execution owner.** A research run has exactly one canonical lifecycle owner: Axiom ADGO.
2. **One knowledge promotion path.** Canonical knowledge enters SncSinCore only through the canonicalization gate.
3. **No silent assurance downgrade.** Degraded retrieval is explicitly marked and never masquerades as verified evidence.
4. **Policy failures are terminal.** Security decisions cannot be bypassed by backend escalation.
5. **Leases require fencing.** Expiry alone is insufficient to guarantee single execution.
6. **Search and evidence are different contracts.** Retrieval optimizes recall; epistemic validation determines evidence status.
7. **Run state is scoped.** Mutable exploratory state belongs to a run workspace, not global singletons.
8. **Background work is owned.** Every spawned task belongs to a structured lifecycle and budget.
9. **Performance optimizations may not weaken correctness.** Approximate indexes require a proof/tested completeness contract for the guarantees they claim.
10. **Release claims follow current CI evidence.** Reliability/FI can only be closed by gates executed on the current architecture revision.

---

# 19. Release gate derived from this audit

A future production-ready claim requires all of the following:

- [ ] public research lifecycle is Axiom-owned;
- [ ] Candidate SIH cannot bypass canonicalization;
- [ ] epistemic assurance level is explicit and fail-closed for verified consumers;
- [ ] acquisition security policy is terminal and TLS verification is enabled;
- [ ] domain concurrency and lease fencing properties pass stateful tests;
- [ ] no unowned async work remains in the pipeline;
- [ ] near-duplicate search is differential-tested against brute force;
- [ ] SncSin corpus persistence/replay is deterministic;
- [ ] Python, Go and Rust baselines all pass from clean checkout;
- [ ] mutation tests actually execute after baseline and critical surviving mutants are zero;
- [ ] documentation audit reports current residual risks rather than assuming FI=0.

Until these are demonstrated, DeepSearch should be described as a strong evolving architecture with known P0/P1 hardening work, not as a zero-fragility completed architecture.
