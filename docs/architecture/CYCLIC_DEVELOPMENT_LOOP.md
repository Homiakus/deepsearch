# Cyclic Development, Verification, and Controlled Auto-Repair Loop

**Status:** operational control plane for the canonical DeepSearch engineering plan  
**Canonical plan:** `docs/architecture/REFACTOR_PLAN.md`  
**Runner:** `tools/devloop.py`  
**Machine state:** `.deepsearch/devloop-state.json`  
**Edge-space model:** `.deepsearch/edge-space.json`

## 1. Purpose

The loop turns the existing engineering plan into an executable sequence of small,
verifiable changes. It does not create a second roadmap. `REFACTOR_PLAN.md` remains the
source of truth; the loop selects the next `DS-*` section, builds its task packet,
checks the resulting diff, records completion, and can fast-forward the successful
atomic commit to `main`.

The design is fail-closed. A red clean baseline, failed test, mutation survivor,
diff-budget violation, protected-path modification, branch mismatch, or
non-fast-forward push stops the iteration.

## 2. Control loop

```text
clean main
    ↓
FAST GATES on the unmodified baseline
    ↓
select next DS-* task from REFACTOR_PLAN.md
    ↓
create task packet + plan fingerprint
    ↓
derive pairwise multidimensional edge matrix
    ↓
characterize current behavior / minimal counterexample
    ↓
smallest implementation change
    ↓
mechanical fix on already-changed files only
    ↓
FAST GATES
    ↓
controlled semantic repair (0..2 rounds, opt-in)
    ↓
FULL GATES
    ↓
risk gate: mutation testing for P0/P1
    ↓
diff budget + protected-path check
    ↓
record successful plan state
    ↓
one atomic commit
    ↓
optional normal fast-forward push to main
```

The loop never force-pushes. If remote `main` moves, a normal Git push rejects the
update and the rebased tree must be revalidated.

### Why the clean-baseline gate exists

A coding agent must not see an inherited failure and "repair" unrelated code under the
next plan task. Therefore semantic auto-repair is disabled in effect until the clean
baseline itself passes the fast gate. Baseline stabilization is explicit work, not a
side effect of an unrelated task.

## 3. Canonical-plan semantics

The parser consumes headings of the form:

```text
### DS-27 — ...
**Приоритет:** P0
```

Completion is stored separately in `.deepsearch/devloop-state.json`. Each completed
task stores a fingerprint of the exact plan section. Editing that canonical section
reopens the task automatically, so stale "done" state cannot survive a changed
requirement.

A task that appears already implemented is still revalidated. The correct iteration
may add evidence/tests only instead of unnecessary production churn.

## 4. Multidimensional edge-case space

Flat lists such as "null / zero / max" are insufficient because DeepSearch failures
usually emerge from interactions. The committed model has six orthogonal axes:

| Axis | Values/examples |
| --- | --- |
| input shape | empty, singleton, typical, near-limit |
| boundary relation | below, exact, above, invalid/overflow |
| ordering | canonical, reversed, duplicate-heavy, adversarial |
| state | fresh, partial, retrying, cancelled |
| dependency | healthy, timeout, malformed, partial failure |
| concurrency | single, parallel, racy interleaving |

`generate_pairwise_cases()` builds a deterministic pairwise covering array. Every
value of every axis therefore co-occurs with every value of every other axis without
paying the full Cartesian-product cost.

Pairwise coverage is the floor. Critical coupled risks also have explicit 3-way
interactions:

- redirect/security-boundary/rebinding behavior;
- budget × retry × cancellation;
- dedup/order × partial failure;
- input size/boundary × corrupt dependency output.

Numeric and temporal boundaries should sample `x-ε`, `x`, `x+ε` or discrete
equivalents. Stateful code is tested as traces: retry, cancellation, lease expiry,
duplicate delivery, partial commit, and recovery sequences.

Every confirmed defect keeps its minimal reproducer. If the defect generalizes, the
edge model itself is extended so the class cannot hide behind a different concrete
input.

## 5. Testing layers

### 5.1 Fast gates

Fast gates reject cheap failures early:

- Python compile;
- Ruff lint and formatting;
- hermetic pytest suite;
- Rust tests;
- Go tests.

The exact commands are versioned in `.deepsearch/devloop.toml`.

### 5.2 Full gates

Before a task can be committed, the loop additionally runs:

- complete pytest suite with slow-test visibility;
- wheel build;
- Rust `fmt`, `clippy -D warnings`, and full tests;
- Go race detector.

Existing repository CI remains an independent execution environment. The local loop
mirrors its critical checks so failures are detected before push whenever possible.

### 5.3 Test-of-tests / mutation testing

Coverage proves execution; mutation testing asks whether the tests notice plausible
wrong behavior.

| Language | Engine | Targeted policy |
| --- | --- | --- |
| Python | `mutmut 3.7.0` | changed `scraper.*` modules; tests-only ⇒ full Python scope |
| Rust | `cargo-mutants 27.1.0` | Git-diff scope; tests-only/untracked source ⇒ full crate |
| Go | Gremlins `0.6.0` | full `orchestrator` module when Go changes |

For P0/P1 tasks mutation testing is mandatory after ordinary full gates pass.

Python is not treated as green merely because `mutmut run` exits successfully. The
runner exports `mutmut-cicd-stats.json` and enforces a score of at least 80%. In the
critical targeted gate, surviving/timeout/suspicious/no-test mutants are rejected.
Equivalent mutants must be explicitly investigated instead of silently lowering the
gate.

`cargo-mutants` already returns non-zero when mutants are missed or time out. Gremlins
is run with efficacy ≥80% and mutant-coverage ≥70% thresholds.

The Go adapter deliberately uses module scope instead of `--diff`: this avoids a
class of monorepo path-matching failures where a diff-scoped run can produce a false
green by selecting no mutants.

The mutation workflow supports:

- pull-request differential runs;
- targeted runs after direct production-code pushes to `main`;
- scheduled/manual full mutation sweeps;
- artifacts for survivor investigation.

## 6. Controlled auto-repair

### Tier 0 — deterministic mechanical repair

Only already-changed files may be mechanically rewritten:

- Ruff fix/format for changed Python;
- rustfmt through the acquisition-worker crate when Rust changed;
- `gofmt -w` for changed Go files.

The post-fix diff budget runs immediately afterwards. Mechanical repair cannot expand
into an unnoticed repository-wide rewrite.

### Tier 1 — bounded semantic repair

An external coding agent may be supplied via `--semantic-autofix-cmd`. It receives the
same task packet with `DEEPSEARCH_REPAIR_MODE=1`. It is capped at two rounds. Each
round is followed by diff containment, mechanical formatting, another containment
check, and the complete fast gate.

Semantic repair is allowed only when driven by a failing test, reproduced
counterexample, invariant, type/contract failure, or mutation survivor.

### Tier 2 — never auto-approve

The loop must not silently solve a failure by:

- deleting, skipping, weakening, or broadly mocking the failing test;
- changing security policy;
- widening a public contract merely to accept bad output;
- changing schema semantics;
- changing dependency versions without the canonical task requiring it;
- regenerating large snapshots/goldens without explicit justification;
- changing the loop, edge model, or CI gate from inside a plan iteration;
- force-pushing or bypassing failed checks.

## 7. Diff containment

Default per-iteration budget:

- at most **12 files**;
- at most **900 added+deleted line-equivalents**.

Tracked and untracked files are both counted. Large binary additions receive a byte
based line-equivalent cost, so an agent cannot bypass the limit by adding an untracked
binary.

The policy, edge model, devloop implementation, agent protocol, and devloop/mutation
workflows are protected paths during plan execution. This prevents an agent from
making a red gate green by rewriting the gate itself.

## 8. Agent contract

The coding agent is external and provider-agnostic. It receives:

```text
DEEPSEARCH_TASK_ID
DEEPSEARCH_TASK_PRIORITY
DEEPSEARCH_TASK_PACKET
DEEPSEARCH_EDGE_CASES_JSON
```

The agent modifies the current working tree only. It does not choose the roadmap item;
the runner does.

Controlled semantic repair receives the same contract plus:

```text
DEEPSEARCH_REPAIR_MODE=1
```

## 9. Commands

Inspect the next canonical task:

```bash
python tools/devloop.py next-task
python tools/devloop.py next-task --json
```

Generate the edge matrix:

```bash
python tools/devloop.py edge-space \
  --output .deepsearch/runtime/edge-cases.json
```

Run validation:

```bash
python tools/devloop.py validate --fast
python tools/devloop.py validate
```

Install Rust/Go mutation engines once:

```bash
python tools/devloop.py bootstrap-mutation-tools
```

Run targeted test-of-tests for current changes:

```bash
python tools/devloop.py mutation --scope targeted --base-ref HEAD
```

Run the canonical plan loop:

```bash
python tools/devloop.py loop \
  --agent-cmd "<coding-agent command>" \
  --semantic-autofix-cmd "<repair-agent command>" \
  --push
```

Omit `--semantic-autofix-cmd` when semantic repair must be manual. The first semantic
failure then stops the iteration.

## 10. Failure recovery

An iteration stops on the first unsatisfied invariant. Recovery order:

1. preserve the exact failing command and smallest reproducer;
2. classify production defect vs test weakness vs environment vs equivalent mutant;
3. fix only the classified cause;
4. rerun fast gates;
5. rerun full gates;
6. rerun relevant mutation scope;
7. commit only after the whole chain is green.

A failed iteration does **not** persist an "attempt" change into the tracked state file,
so the next run does not deadlock on its own dirty bookkeeping. Completion state is
written only after all required gates pass.

## 11. Definition of done for the loop

The control plane is healthy when:

- next-task selection is deterministic;
- changed canonical requirements reopen completed tasks;
- pairwise generation reports zero uncovered value pairs;
- critical coupled dimensions have explicit higher-order cases;
- untracked additions cannot bypass diff limits;
- mechanical autofix cannot rewrite unrelated files unnoticed;
- a red clean baseline stops semantic auto-repair;
- P0/P1 tasks cannot commit without required mutation gates;
- Python mutation score/survivors are converted into an actual failing gate;
- tests-only changes cannot make mutation testing silently skip the language;
- implementation agents cannot modify protected control-plane files;
- no semantic repair can exceed the configured rounds/diff budget;
- a push cannot force-update `main`;
- CI independently checks the harness and mutation layers.
