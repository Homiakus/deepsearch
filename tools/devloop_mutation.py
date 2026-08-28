"""Mutation-test adapters for Python, Rust, and Go."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from tools.devloop_core import (
    ROOT,
    DevLoopError,
    Task,
    diff_paths,
    git_output,
    run,
    untracked_paths,
)

_MUTMUT_VERSION = "3.7.0"
_CARGO_MUTANTS_VERSION = "27.1.0"
_GREMLINS_VERSION = "0.6.0"


def require_binary(name: str, hint: str) -> None:
    """Require an external mutation engine with an actionable install hint."""
    if shutil.which(name) is None:
        raise DevLoopError(f"{name} is required; run: {hint}")


def python_mutation_targets(base_ref: str) -> list[str]:
    """Map changed production Python files to mutmut wildcard targets."""
    modules: list[str] = []
    for path in diff_paths(base_ref):
        if path.startswith("scraper/") and path.endswith(".py"):
            module = path.removesuffix(".py").replace("/", ".")
            modules.append(module.removesuffix(".__init__"))
    return sorted(set(modules))


def _python_tests_changed(base_ref: str) -> bool:
    return any(
        path.startswith("tests/") and path.endswith(".py")
        for path in diff_paths(base_ref)
    )


def _python_source_is_untracked() -> bool:
    return any(
        path.startswith("scraper/") and path.endswith(".py")
        for path in untracked_paths()
    )


def _clear_mutmut_workspace() -> None:
    shutil.rmtree(ROOT / "mutants", ignore_errors=True)


def _mutmut_prefix() -> list[str]:
    return ["uv", "run", "--with", f"mutmut=={_MUTMUT_VERSION}", "mutmut"]


def _enforce_mutmut_stats(
    *,
    min_score: float,
    require_zero_survivors: bool,
) -> None:
    """Turn mutmut's CI JSON into an actual quality gate."""
    stats_path = ROOT / "mutants" / "mutmut-cicd-stats.json"
    if not stats_path.exists():
        raise DevLoopError("mutmut did not produce mutmut-cicd-stats.json")

    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    total = int(stats.get("total", 0))
    skipped = int(stats.get("skipped", 0))
    killed = int(stats.get("killed", 0))
    tested = max(total - skipped, 0)
    score = 100.0 if tested == 0 else (killed / tested) * 100.0

    risk_keys = ("survived", "timeout", "suspicious", "no_tests", "untested")
    risky = sum(int(stats.get(key, 0)) for key in risk_keys)
    print(
        "Python mutation gate: "
        f"score={score:.1f}% killed={killed} total={total} "
        f"skipped={skipped} risky={risky}",
        flush=True,
    )

    if score < min_score:
        raise DevLoopError(
            f"Python mutation score {score:.1f}% is below {min_score:.1f}%"
        )
    if require_zero_survivors and risky:
        raise DevLoopError(
            f"Python mutation gate has {risky} surviving/uncertain mutants"
        )


def run_python_mutation(
    base_ref: str,
    full: bool,
    *,
    min_score: float,
    require_zero_survivors: bool,
) -> None:
    """Run clean, score-enforced Python mutation testing."""
    targets = python_mutation_targets(base_ref)
    tests_changed = _python_tests_changed(base_ref)

    if not full and not targets and not tests_changed:
        print("Python mutation: no changed Python source/tests; skipped.")
        return

    # A tests-only change must prove that it did not weaken the existing suite.
    # New untracked source cannot be represented by a Git diff, so use full scope.
    effective_full = (
        full or (tests_changed and not targets) or _python_source_is_untracked()
    )
    _clear_mutmut_workspace()

    command = [*_mutmut_prefix(), "run"]
    if not effective_full:
        command.extend(f"{module}*" for module in targets)
    run(command)
    run([*_mutmut_prefix(), "export-cicd-stats"])
    _enforce_mutmut_stats(
        min_score=min_score,
        require_zero_survivors=require_zero_survivors,
    )


def _rust_changes(base_ref: str) -> tuple[list[str], bool]:
    source: list[str] = []
    tests_changed = False
    for path in diff_paths(base_ref):
        if not path.startswith("rust/acquisition-worker/") or not path.endswith(".rs"):
            continue
        if path.startswith("rust/acquisition-worker/tests/"):
            tests_changed = True
        else:
            source.append(path)
    return source, tests_changed


def _rust_source_is_untracked() -> bool:
    return any(
        path.startswith("rust/acquisition-worker/")
        and path.endswith(".rs")
        and not path.startswith("rust/acquisition-worker/tests/")
        for path in untracked_paths()
    )


def run_rust_mutation(base_ref: str, full: bool) -> None:
    """Run cargo-mutants, using diff scope only when the diff is representable."""
    crate = ROOT / "rust" / "acquisition-worker"
    require_binary(
        "cargo-mutants",
        f"cargo install --locked cargo-mutants --version {_CARGO_MUTANTS_VERSION}",
    )
    source, tests_changed = _rust_changes(base_ref)
    if not full and not source and not tests_changed:
        print("Rust mutation: no changed Rust source/tests; skipped.")
        return

    effective_full = (
        full or (tests_changed and not source) or _rust_source_is_untracked()
    )
    if effective_full:
        run(
            ["cargo", "mutants", "--no-shuffle", "--timeout", "300"],
            cwd=crate,
        )
        return

    relative_diff = git_output(
        "diff",
        "--relative=rust/acquisition-worker",
        base_ref,
        "--",
        "rust/acquisition-worker",
    )
    if not relative_diff.strip():
        raise DevLoopError("Rust source changed but diff-scoped mutation got no diff")

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".diff", delete=False
    ) as handle:
        handle.write(relative_diff)
        diff_path = Path(handle.name)
    try:
        run(
            [
                "cargo",
                "mutants",
                "--no-shuffle",
                "--in-diff",
                str(diff_path),
                "--timeout",
                "300",
            ],
            cwd=crate,
        )
    finally:
        diff_path.unlink(missing_ok=True)


def _go_changed(base_ref: str) -> bool:
    return any(
        path.startswith("orchestrator/") and path.endswith(".go")
        for path in diff_paths(base_ref)
    )


def run_go_mutation(base_ref: str, full: bool) -> None:
    """Run module-scoped Gremlins with explicit efficacy/coverage thresholds."""
    module = ROOT / "orchestrator"
    require_binary(
        "gremlins",
        f"go install github.com/go-gremlins/gremlins/cmd/gremlins@v{_GREMLINS_VERSION}",
    )
    if not full and not _go_changed(base_ref):
        print("Go mutation: no changed Go source/tests; skipped.")
        return

    # Gremlins --diff has had monorepo path-matching regressions. The Go module is
    # small enough that a module-scoped run is a safer test-of-tests gate.
    run(
        [
            "gremlins",
            "unleash",
            "--threshold-efficacy",
            "80",
            "--threshold-mcover",
            "70",
        ],
        cwd=module,
    )


def run_mutation(
    *,
    config: dict[str, Any],
    base_ref: str,
    full: bool,
    languages: set[str],
) -> None:
    """Dispatch mutation testing for requested languages."""
    mutation = config.get("mutation", {})
    min_score = float(mutation.get("python_min_score", 80.0))
    require_zero = bool(mutation.get("python_require_zero_survivors", True))

    if "python" in languages:
        run_python_mutation(
            base_ref,
            full,
            min_score=min_score,
            require_zero_survivors=require_zero,
        )
    if "rust" in languages:
        run_rust_mutation(base_ref, full)
    if "go" in languages:
        run_go_mutation(base_ref, full)


def mutation_required(config: dict[str, Any], task: Task) -> bool:
    """Return whether this plan risk class requires test-of-tests."""
    required = {str(item) for item in config["mutation"]["required_priorities"]}
    return task.priority in required


def bootstrap_mutation_tools() -> None:
    """Install non-Python mutation engines at pinned versions."""
    run(f"cargo install --locked cargo-mutants --version {_CARGO_MUTANTS_VERSION}")
    run(f"go install github.com/go-gremlins/gremlins/cmd/gremlins@v{_GREMLINS_VERSION}")
