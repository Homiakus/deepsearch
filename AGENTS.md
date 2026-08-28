# DeepSearch coding-agent protocol

Use `docs/architecture/REFACTOR_PLAN.md` as the canonical engineering plan and
`tools/devloop.py` as its execution control plane.

For implementation work:

1. Run `python tools/devloop.py next-task` and work on that `DS-*` task only.
2. Read the generated task packet from `DEEPSEARCH_TASK_PACKET`.
3. Characterize current behavior before production changes.
4. Add a minimal failing counterexample for defects.
5. Treat edge cases as a multidimensional space; use the generated pairwise matrix and
   explicit 3-way interactions for security/state/retry/budget/concurrency coupling.
6. Keep unit tests hermetic and inject network/browser/storage failures at boundaries.
7. Never weaken, delete, skip, or broadly mock a test merely to make a gate green.
8. Never edit the devloop policy, edge model, runner, or CI gate from a plan iteration.
9. Keep the change inside the configured file/line diff budget, including new files.
10. P0/P1 changes require mutation testing after full ordinary tests pass.
11. One successful plan task equals one atomic commit.
12. Push to `main` only after all required gates pass; never force-push.

A clean baseline is a prerequisite for autonomous semantic repair. If the baseline is
red, classify and stabilize it explicitly instead of attributing inherited failures to
the next plan task.

Operational details are in `docs/architecture/CYCLIC_DEVELOPMENT_LOOP.md`.
