#!/usr/bin/env python3
"""Conservative plan-driven development loop for DeepSearch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.devloop_core import (  # noqa: E402
    DEFAULT_CONFIG,
    ROOT,
    DevLoopError,
    Task,
    load_json,
    load_toml,
    next_task,
    parse_plan,
    read_state,
    run_fast_gates,
    run_full_gates,
    run_safe_fix,
)
from tools.devloop_edge import (  # noqa: E402
    edge_summary,
    generate_pairwise_cases,
    make_task_packet,
    missing_pairwise_coverage,
)
from tools.devloop_mutation import (  # noqa: E402
    bootstrap_mutation_tools,
    run_mutation,
)
from tools.devloop_runner import run_one_iteration  # noqa: E402

__all__ = [
    "Task",
    "generate_pairwise_cases",
    "make_task_packet",
    "missing_pairwise_coverage",
    "next_task",
    "parse_plan",
]


def build_parser() -> argparse.ArgumentParser:
    """Build the repository-local control-plane CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    subs = parser.add_subparsers(dest="command", required=True)

    next_parser = subs.add_parser("next-task")
    next_parser.add_argument("--json", action="store_true")

    edge_parser = subs.add_parser("edge-space")
    edge_parser.add_argument("--output")

    validate = subs.add_parser("validate")
    validate.add_argument("--fast", action="store_true")
    validate.add_argument("--fix", action="store_true")

    mutation = subs.add_parser("mutation")
    mutation.add_argument(
        "--scope",
        choices=("targeted", "full"),
        default="targeted",
    )
    mutation.add_argument("--base-ref", default="HEAD")
    mutation.add_argument(
        "--languages",
        nargs="+",
        choices=("python", "rust", "go"),
        default=("python", "rust", "go"),
    )

    subs.add_parser("bootstrap-mutation-tools")

    loop = subs.add_parser("loop")
    loop.add_argument("--agent-cmd", required=True)
    loop.add_argument("--semantic-autofix-cmd")
    loop.add_argument("--max-iterations", type=int)
    loop.add_argument("--push", action="store_true")
    return parser


def command_next(config: dict[str, Any], as_json: bool) -> int:
    """Render the next canonical task packet."""
    state_path = ROOT / config["plan"]["state_file"]
    task = next_task(config, read_state(state_path))
    if task is None:
        print("No pending canonical DS task.")
        return 0

    model = load_json(ROOT / config["edge_space"]["model"])
    cases = generate_pairwise_cases(model)
    if as_json:
        print(
            json.dumps(
                {
                    "id": task.task_id,
                    "priority": task.priority,
                    "title": task.title,
                    "plan": task.plan_path,
                    "fingerprint": task.fingerprint,
                    "pairwise_scenarios": len(cases),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(make_task_packet(task, edge_summary(model, cases)))
    return 0


def command_edge(config: dict[str, Any], output: str | None) -> int:
    """Generate and optionally persist the multidimensional edge matrix."""
    model_path = ROOT / config["edge_space"]["model"]
    model = load_json(model_path)
    cases = generate_pairwise_cases(model)
    missing = missing_pairwise_coverage(model, cases)
    payload = {
        "model": str(model_path.relative_to(ROOT)),
        "scenario_count": len(cases),
        "missing_pairs": len(missing),
        "targeted_interactions": model.get("targeted_interactions", []),
        "scenarios": cases,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if output:
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(output_path)
    else:
        print(rendered, end="")
    return 0 if not missing else 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected control-plane operation."""
    args = build_parser().parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config = load_toml(config_path)

    try:
        if args.command == "next-task":
            return command_next(config, args.json)
        if args.command == "edge-space":
            return command_edge(config, args.output)
        if args.command == "validate":
            if args.fix:
                run_safe_fix(config)
            (run_fast_gates if args.fast else run_full_gates)(config)
            return 0
        if args.command == "mutation":
            run_mutation(
                config=config,
                base_ref=args.base_ref,
                full=args.scope == "full",
                languages=set(args.languages),
            )
            return 0
        if args.command == "bootstrap-mutation-tools":
            bootstrap_mutation_tools()
            return 0
        if args.command == "loop":
            limit = args.max_iterations or int(config["loop"]["max_iterations"])
            semantic_cmd = args.semantic_autofix_cmd or os.environ.get(
                "DEEPSEARCH_SEMANTIC_AUTOFIX_CMD"
            )
            completed = 0
            for _ in range(limit):
                changed = run_one_iteration(
                    config,
                    agent_cmd=args.agent_cmd,
                    semantic_autofix_cmd=semantic_cmd,
                    push=args.push,
                )
                if not changed:
                    break
                completed += 1
            print(f"Development-loop iterations completed: {completed}")
            return 0
    except (DevLoopError, subprocess.CalledProcessError) as exc:
        print(f"devloop failed: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
