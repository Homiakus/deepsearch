"""One-task-at-a-time execution and controlled auto-repair."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from tools.devloop_core import (
    ROOT,
    DevLoopError,
    Task,
    current_branch,
    ensure_clean_worktree,
    enforce_diff_budget,
    git_output,
    load_json,
    next_task,
    read_state,
    run,
    run_fast_gates,
    run_full_gates,
    run_safe_fix,
    write_state,
)
from tools.devloop_edge import edge_summary, generate_pairwise_cases, make_task_packet
from tools.devloop_mutation import mutation_required, run_mutation


def mark_completed(state: dict[str, Any], task: Task) -> None:
    """Record success only after every required gate has passed."""
    state.setdefault("completed", {})[task.task_id] = {
        "plan_fingerprint": task.fingerprint,
        "priority": task.priority,
        "title": task.title,
    }
    state.setdefault("attempts", {}).pop(task.task_id, None)


def semantic_repair(
    config: dict[str, Any],
    task: Task,
    packet_path: Path,
    command: str | None,
) -> None:
    """Allow a bounded test-driven repair loop without weakening the gate."""
    if not command:
        raise DevLoopError(
            "fast gates failed and no semantic auto-fix command is configured"
        )

    rounds = int(config["safety"]["max_semantic_autofix_rounds"])
    env = {
        "DEEPSEARCH_TASK_ID": task.task_id,
        "DEEPSEARCH_TASK_PACKET": str(packet_path),
        "DEEPSEARCH_REPAIR_MODE": "1",
    }
    for index in range(1, rounds + 1):
        print(f"\n== semantic repair {index}/{rounds} ==", flush=True)
        run(command, env=env)
        enforce_diff_budget(config)
        run_safe_fix(config)
        enforce_diff_budget(config)
        try:
            run_fast_gates(config)
            return
        except subprocess.CalledProcessError:
            if index == rounds:
                raise


def commit_iteration(task: Task) -> str:
    """Create one atomic commit for one successful canonical plan task."""
    run(["git", "add", "-A"])
    if not git_output("diff", "--cached", "--name-only"):
        raise DevLoopError("successful iteration has no changes to commit")

    subject = f"feat(devloop): complete {task.task_id.lower()} {task.title}"
    if len(subject) > 72:
        subject = f"feat(devloop): complete {task.task_id.lower()}"
    run(["git", "commit", "-m", subject])
    return git_output("rev-parse", "HEAD")


def push_main(config: dict[str, Any]) -> None:
    """Push by normal fast-forward semantics; never force-update main."""
    expected = str(config["git"]["branch"])
    branch = current_branch()
    if branch != expected:
        raise DevLoopError(f"refusing push from {branch!r}; expected {expected!r}")
    run(["git", "push", "origin", f"{branch}:{expected}"])


def _preflight_clean_baseline(config: dict[str, Any]) -> None:
    """Prove the clean baseline is green before an agent may edit anything."""
    ensure_clean_worktree()
    print("\n== baseline preflight ==", flush=True)
    try:
        run_fast_gates(config)
    except subprocess.CalledProcessError as exc:
        raise DevLoopError(
            "clean baseline is red; refusing task-scoped auto-repair because it "
            "could misattribute inherited failures"
        ) from exc


def run_one_iteration(
    config: dict[str, Any],
    *,
    agent_cmd: str,
    semantic_autofix_cmd: str | None,
    push: bool,
) -> bool:
    """Execute exactly one canonical task through the complete gate chain."""
    expected = str(config["git"]["branch"])
    if current_branch() != expected:
        raise DevLoopError(f"loop must run on {expected!r}")

    _preflight_clean_baseline(config)
    state_path = ROOT / config["plan"]["state_file"]
    state = read_state(state_path)
    task = next_task(config, state)
    if task is None:
        print("All canonical DS tasks are recorded as complete.")
        return False

    model = load_json(ROOT / config["edge_space"]["model"])
    cases = generate_pairwise_cases(model)
    runtime = ROOT / ".deepsearch" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    packet_path = runtime / f"{task.task_id.lower()}-task.md"
    packet_path.write_text(
        make_task_packet(task, edge_summary(model, cases)),
        encoding="utf-8",
    )

    env = {
        "DEEPSEARCH_TASK_ID": task.task_id,
        "DEEPSEARCH_TASK_PRIORITY": task.priority,
        "DEEPSEARCH_TASK_PACKET": str(packet_path),
        "DEEPSEARCH_EDGE_CASES_JSON": json.dumps(cases, ensure_ascii=False),
    }
    run(agent_cmd, env=env)
    enforce_diff_budget(config)
    run_safe_fix(config)
    enforce_diff_budget(config)

    try:
        run_fast_gates(config)
    except subprocess.CalledProcessError:
        semantic_repair(config, task, packet_path, semantic_autofix_cmd)

    run_full_gates(config)
    if mutation_required(config, task):
        run_mutation(
            config=config,
            base_ref="HEAD",
            full=False,
            languages={"python", "rust", "go"},
        )

    mark_completed(state, task)
    write_state(state, state_path)
    enforce_diff_budget(config)
    commit_sha = commit_iteration(task)
    print(f"Committed {task.task_id}: {commit_sha}")
    if push:
        push_main(config)
    return True
