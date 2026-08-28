"""Core primitives for the DeepSearch development loop."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import subprocess
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / ".deepsearch" / "devloop.toml"
_TASK_HEADING = re.compile(r"^###\s+(DS-\d+)\s+[—-]\s+(.+?)\s*$")
_PRIORITY = re.compile(r"^\*\*Приоритет:\*\*\s*(P[0-4])\s*$", re.MULTILINE)


class DevLoopError(RuntimeError):
    """Raised when a development-loop invariant is violated."""


@dataclass(frozen=True)
class Task:
    """One atomic section of the canonical plan."""

    task_id: str
    title: str
    priority: str
    plan_path: str
    section: str

    @property
    def fingerprint(self) -> str:
        """Return a stable fingerprint of the exact plan contract."""
        raw = (
            f"{self.plan_path}\n{self.task_id}\n{self.title}\n{self.section}"
        ).encode()
        return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True)
class DiffStats:
    """Bounded view of a working-tree change."""

    files: int
    changed_lines: int
    paths: tuple[str, ...]


def load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML mapping."""
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_json(path: Path) -> dict[str, Any]:
    """Load a UTF-8 JSON mapping."""
    return json.loads(path.read_text(encoding="utf-8"))


def run(
    command: str | Sequence[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a checked command while preserving the current environment."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "env": merged_env,
        "text": True,
    }
    if capture:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if isinstance(command, str):
        print(f"+ {command}", flush=True)
        return subprocess.run(command, shell=True, check=True, **kwargs)

    argv = list(command)
    print(f"+ {shlex.join(argv)}", flush=True)
    return subprocess.run(argv, check=True, **kwargs)


def git_output(*args: str) -> str:
    """Run git and return stripped stdout."""
    return run(["git", *args], capture=True).stdout.strip()


def current_branch() -> str:
    """Return the checked-out branch name."""
    return git_output("branch", "--show-current")


def ensure_clean_worktree() -> None:
    """Fail closed when the loop starts from an ambiguous tree."""
    if git_output("status", "--porcelain"):
        raise DevLoopError("worktree is not clean; commit or stash changes first")


def parse_plan(path: Path) -> list[Task]:
    """Parse ordered DS tasks from the canonical Markdown plan."""
    lines = path.read_text(encoding="utf-8").splitlines()
    starts: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        if match := _TASK_HEADING.match(line):
            starts.append((index, match))

    tasks: list[Task] = []
    for pos, (start, match) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        section = "\n".join(lines[start:end]).strip() + "\n"
        priority = _PRIORITY.search(section)
        try:
            plan_path = str(path.relative_to(ROOT))
        except ValueError:
            plan_path = str(path)
        tasks.append(
            Task(
                task_id=match.group(1),
                title=match.group(2).strip(),
                priority=priority.group(1) if priority else "P3",
                plan_path=plan_path,
                section=section,
            )
        )

    if not tasks:
        raise DevLoopError(f"no DS tasks found in {path}")
    return tasks


def read_state(path: Path) -> dict[str, Any]:
    """Read machine progress without treating it as plan truth."""
    if not path.exists():
        return {"version": 1, "completed": {}, "attempts": {}}
    state = load_json(path)
    state.setdefault("version", 1)
    state.setdefault("completed", {})
    state.setdefault("attempts", {})
    return state


def write_state(state: dict[str, Any], path: Path) -> None:
    """Persist state deterministically after a successful iteration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(rendered, encoding="utf-8")


def next_task(config: dict[str, Any], state: dict[str, Any]) -> Task | None:
    """Select the first incomplete or specification-changed task."""
    plan = Path(config["plan"]["canonical"])
    if not plan.is_absolute():
        plan = ROOT / plan

    completed = state.get("completed", {})
    for task in parse_plan(plan):
        record = completed.get(task.task_id)
        if not record or record.get("plan_fingerprint") != task.fingerprint:
            return task
    return None


def untracked_paths() -> tuple[str, ...]:
    """Return untracked, non-ignored paths so budgets cannot be bypassed."""
    output = git_output("ls-files", "--others", "--exclude-standard")
    return tuple(line for line in output.splitlines() if line.strip())


def diff_paths(base_ref: str = "HEAD") -> tuple[str, ...]:
    """Return tracked and untracked changed paths."""
    tracked = {
        line
        for line in git_output("diff", "--name-only", base_ref).splitlines()
        if line.strip()
    }
    return tuple(sorted(tracked | set(untracked_paths())))


def _untracked_line_cost(path: Path) -> int:
    """Estimate line-equivalent cost, including large binary additions."""
    data = path.read_bytes()
    physical_lines = data.count(b"\n") + (1 if data else 0)
    byte_equivalent = math.ceil(len(data) / 80) if data else 0
    return max(physical_lines, byte_equivalent)


def diff_stats(base_ref: str = "HEAD") -> DiffStats:
    """Calculate bounded diff statistics including untracked files."""
    changed_lines = 0
    tracked_paths: set[str] = set()
    for line in git_output("diff", "--numstat", base_ref).splitlines():
        if not line.strip():
            continue
        added, deleted, path = line.split("\t", 2)
        tracked_paths.add(path)
        changed_lines += int(added) if added.isdigit() else 0
        changed_lines += int(deleted) if deleted.isdigit() else 0

    untracked = set(untracked_paths())
    for relative in untracked:
        path = ROOT / relative
        if path.is_file():
            changed_lines += _untracked_line_cost(path)

    paths = tuple(sorted(tracked_paths | untracked))
    return DiffStats(files=len(paths), changed_lines=changed_lines, paths=paths)


def enforce_diff_budget(
    config: dict[str, Any], base_ref: str = "HEAD"
) -> DiffStats:
    """Reject oversized or self-modifying implementation diffs."""
    stats = diff_stats(base_ref)
    safety = config["safety"]
    if stats.files > int(safety["max_files_changed"]):
        raise DevLoopError(f"{stats.files} changed files exceeds budget")
    if stats.changed_lines > int(safety["max_changed_lines"]):
        raise DevLoopError(f"{stats.changed_lines} changed lines exceeds budget")

    protected = tuple(str(path).rstrip("/") for path in safety["protected_paths"])
    for path in stats.paths:
        if any(path == item or path.startswith(item + "/") for item in protected):
            raise DevLoopError(f"protected path changed: {path}")
    return stats


def run_commands(commands: Iterable[str], label: str) -> None:
    """Run an ordered gate group."""
    for command in commands:
        print(f"\n== {label}: {command} ==", flush=True)
        run(command)


def run_safe_fix(config: dict[str, Any]) -> None:
    """Apply deterministic fixes only to files already changed by the task."""
    del config  # policy is intentionally hard-coded; agents cannot widen the scope.
    paths = diff_paths("HEAD")
    python_paths = [path for path in paths if path.endswith(".py")]
    rust_paths = [
        path
        for path in paths
        if path.startswith("rust/acquisition-worker/") and path.endswith(".rs")
    ]
    go_paths = [
        path
        for path in paths
        if path.startswith("orchestrator/") and path.endswith(".go")
    ]

    if python_paths:
        run(["uv", "run", "ruff", "check", "--fix", *python_paths])
        run(["uv", "run", "ruff", "format", *python_paths])
    if rust_paths:
        run(
            [
                "cargo",
                "fmt",
                "--manifest-path",
                "rust/acquisition-worker/Cargo.toml",
            ]
        )
    if go_paths:
        run(["gofmt", "-w", *go_paths])


def run_fast_gates(config: dict[str, Any]) -> None:
    """Run cheap rejection gates."""
    run_commands(config["commands"]["fast_gates"], "fast-gate")


def run_full_gates(config: dict[str, Any]) -> None:
    """Run the complete pre-commit gate set."""
    run_commands(config["commands"]["full_gates"], "full-gate")
