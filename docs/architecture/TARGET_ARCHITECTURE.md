# Target Architecture Specification

**Project:** DeepSearch — Adaptive Web Scraping & Retrieval Platform  
**Target pattern:** Durable control plane + bounded worker planes + canonical epistemic promotion  
**Normative update:** 2026-09-06

---

## 1. Core ownership model

DeepSearch MUST have one owner for each class of truth:

```text
Axiom ADGO -> execution truth
SncSinCore -> canonical knowledge truth
Rust workers -> high-throughput acquisition execution
Python -> research algorithms, adaptation and domain logic
```

No public surface or compatibility adapter may create a second authoritative lifecycle or evidence authority.

---

## 2. Canonical runtime topology

```text
 +-------------------------------------------------------------+
 |                         ENTRYPOINTS                         |
 |        CLI            REST API             MCP             |
 +-----------------------------+-------------------------------+
                               |
                               v
 +-------------------------------------------------------------+
 |                    APPLICATION BOUNDARY                     |
 |  validates public DTOs and delegates lifecycle operations   |
 +-----------------------------+-------------------------------+
                               |
                               v
 +-------------------------------------------------------------+
 |                        AXIOM ADGO                            |
 | canonical durable research lifecycle / retries / leases /   |
 | cancellation / idempotency / execution status               |
 +-----------------------------+-------------------------------+
                               |
             +-----------------+-----------------+
             |                 |                 |
             v                 v                 v
      Python activities   Rust acquisition   Epistemic activities
             |                 |                 |
             +-----------------+-----------------+
                               |
                               v
                         Raw artifacts
                               |
                               v
                         Candidate SIH
                               |
                               v
 +-------------------------------------------------------------+
 |                  CANONICALIZATION GATE                      |
 | source identity / provenance / negation / attribution /     |
 | contradiction / temporal context / merge / confidence       |
 +-----------------------------+-------------------------------+
                               |
                   accept / reject / quarantine
                               |
                               v
                         Canonical SIH
                               |
                               v
 +-------------------------------------------------------------+
 |                         SncSinCore                           |
 | canonical versioned epistemic memory and evidence queries   |
 +-----------------------------+-------------------------------+
                               |
              +----------------+----------------+
              |                                 |
              v                                 v
     vector/lexical recall                 graph activation
              +----------------+----------------+
                               |
                               v
                    verified evidence artifact
                               |
                               v
                         LLM / consumer
```

---

## 3. Normative invariants

1. **Single execution owner.** Production research runs MUST be created, loaded, cancelled and observed through Axiom ADGO.
2. **No direct canonical ingestion.** Heuristic/probabilistic extraction MUST produce Candidate SIH, never Canonical SIH directly.
3. **Canonical promotion is explicit.** Every canonical proposition MUST have a promotion/canonicalization decision and provenance.
4. **Assurance is explicit.** `VERIFIED`, `DEGRADED`, `UNVERIFIED` and `UNAVAILABLE` states MUST not be conflated.
5. **Fail-open evidence is forbidden.** A lexical or local fallback MUST NOT masquerade as SncSin-verified evidence.
6. **Retrieval is not authority.** Dense/sparse/vector ranking generates candidates; epistemic validation determines evidence status.
7. **Policy failures are terminal.** A security-policy rejection MUST NOT trigger browser, Rust or external-provider escalation.
8. **TLS verification is a production invariant.** Unsafe TLS is allowed only as an explicit development override and MUST be observable.
9. **Leases require ownership proof.** Expired/retried work MUST use fencing/lease generations so stale workers cannot commit accepted completion.
10. **Domain concurrency is a hard bound.** Saturated domains wait; the scheduler MUST NOT lease anyway.
11. **Mutable state is scoped.** Exploratory/candidate knowledge belongs to an explicit run workspace/corpus scope.
12. **Background tasks are owned.** Every spawned async task belongs to a structured lifecycle, budget and cancellation tree.
13. **Archive and runtime knowledge agree.** Exported SIH MUST derive from the same canonical committed artifact used by runtime memory.
14. **Optimization cannot weaken guarantees silently.** Approximate indexes MUST be tested against the correctness contract they claim.
15. **Release claims are revision-local.** Reliability/FI closure requires gates that executed successfully on the released architecture revision.

---

## 4. Layer dependency rule

```text
ENTRYPOINTS
    |
APPLICATION PORTS / DTOs
    |
DURABLE ORCHESTRATION (Axiom)
    |
ACTIVITY / DOMAIN SERVICES
    |
CONTRACTS
    ^
    |
INFRASTRUCTURE ADAPTERS
```

Rules:

- entrypoints MUST NOT own durable business state;
- domain logic MUST NOT import CLI/REST/MCP entrypoints;
- worker adapters MUST communicate through versioned contracts;
- infrastructure adapters MUST NOT define epistemic truth semantics;
- SncSin canonicalization/epistemic contracts are upstream of final evidence presentation.

---

## 5. Research lifecycle contract

The canonical lifecycle is:

```text
StartOrLoad
  -> Normalize / Plan
  -> Discover
  -> Rank / Schedule
  -> Acquire
  -> Extract
  -> Candidate SIH
  -> Canonicalize
  -> Commit Canonical SIH
  -> Evaluate Evidence/Coverage
  -> Build Archive
  -> Complete
```

Cancellation, retry and crash recovery MUST preserve this lifecycle through Axiom state rather than process-local Python dictionaries/tasks.

---

## 6. Epistemic memory model

DeepSearch distinguishes two stores/concepts:

```text
RunWorkspace
    - candidate claims
    - unresolved contradictions
    - temporary evidence
    - extraction uncertainty

CanonicalMemory
    - accepted/promoted propositions
    - versioned provenance
    - deterministic corpus identity
    - auditable promotion history
```

Promotion from `RunWorkspace` to `CanonicalMemory` is an explicit transaction and MUST be replayable/auditable.

---

## 7. Acquisition boundary

All acquisition paths MUST obey one normalized policy decision:

```text
URL input
  -> canonicalize
  -> security / SSRF / protocol / DNS policy
  -> ALLOWED ? backend selection : terminal POLICY_VIOLATION
  -> HTTP / browser / Rust / external fetch / media
```

A backend failure may escalate only when the failure classification permits escalation.

Recommended failure classes:

```text
TRANSIENT
BACKEND_UNAVAILABLE
RATE_LIMIT
CONTENT_FAILURE
POLICY_VIOLATION
```

`POLICY_VIOLATION` is terminal.

---

## 8. Retrieval boundary

Final evidence assembly MUST use the following separation:

```text
recall-oriented candidate retrieval
  -> lexical / dense / source prior / graph activation
  -> candidate set
  -> SncSin evidence-subgraph evaluation
  -> coverage / contradiction / provenance
  -> verified context artifact
```

Search-only UX MAY expose unverified candidates, but it MUST label them as search candidates rather than verified evidence.

---

## 9. Concurrency rules

- executable leases belong to Axiom wherever practical;
- any local lease requires renewal/fencing semantics;
- stale lease holders cannot commit after a newer generation exists;
- `max_active_per_domain` is never bypassed;
- pipeline stages use structured concurrency (`TaskGroup` or owned task registry);
- stage exit implies all owned tasks completed or were cancelled/joined;
- temporary resource cleanup happens only after child work is terminated.

---

## 10. Verification requirements

The target architecture is considered implemented only when tests prove:

- restart-safe Axiom-owned research lifecycle;
- idempotent `StartOrLoad` across API replicas;
- Candidate SIH cannot bypass canonicalization;
- degraded epistemic fallback cannot emit verified assurance;
- run/corpus isolation prevents evidence leakage;
- terminal security failures cannot escalate to alternate backends;
- TLS verification is enabled in production paths;
- lease expiry races cannot create duplicate accepted completion;
- domain concurrency bounds hold under stateful tests;
- near-duplicate indexing is differential-tested against brute-force Hamming search;
- no unowned async tasks remain after completion/cancellation;
- canonical SncSin state replays to the same corpus digest;
- Python/Rust/Go clean baselines pass before mutation testing.

See [`ARCHITECTURAL_LEVERAGE_AND_FRAGILITY_AUDIT_2026-09-06.md`](./ARCHITECTURAL_LEVERAGE_AND_FRAGILITY_AUDIT_2026-09-06.md) for the detailed rationale and DS-43..DS-52 roadmap.
