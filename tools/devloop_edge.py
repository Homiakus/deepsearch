"""Multidimensional edge-space generation and task packets."""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from typing import Any

from tools.devloop_core import DevLoopError, Task


def generate_pairwise_cases(model: dict[str, Any]) -> list[dict[str, str]]:
    """Generate a deterministic pairwise covering array for all model axes."""
    axes_raw = model.get("axes")
    if not isinstance(axes_raw, dict) or len(axes_raw) < 2:
        raise DevLoopError("edge-space must define at least two axes")

    axes: list[tuple[str, tuple[str, ...]]] = []
    for name, values in axes_raw.items():
        if not isinstance(values, list) or not values:
            raise DevLoopError(f"axis {name!r} must contain values")
        axes.append((str(name), tuple(str(value) for value in values)))

    remaining = list(itertools.product(*(values for _, values in axes)))
    uncovered: set[tuple[int, str, int, str]] = set()
    for left_index, (_, left_values) in enumerate(axes):
        for right_index in range(left_index + 1, len(axes)):
            for left in left_values:
                for right in axes[right_index][1]:
                    uncovered.add((left_index, left, right_index, right))

    selected: list[tuple[str, ...]] = []
    while uncovered:
        best_index = -1
        best_cover: set[tuple[int, str, int, str]] = set()
        for index, candidate in enumerate(remaining):
            cover = {
                (left, candidate[left], right, candidate[right])
                for left in range(len(axes))
                for right in range(left + 1, len(axes))
                if (left, candidate[left], right, candidate[right]) in uncovered
            }
            if len(cover) > len(best_cover):
                best_index, best_cover = index, cover

        if best_index < 0 or not best_cover:
            raise DevLoopError("pairwise generator stalled")
        selected.append(remaining.pop(best_index))
        uncovered.difference_update(best_cover)

    return [
        {axes[index][0]: value for index, value in enumerate(case)}
        for case in selected
    ]


def missing_pairwise_coverage(
    model: dict[str, Any], cases: Iterable[dict[str, str]]
) -> set[tuple[str, str, str, str]]:
    """Return required value pairs that no generated case covers."""
    axes = [
        (str(name), [str(value) for value in values])
        for name, values in model["axes"].items()
    ]
    covered: set[tuple[str, str, str, str]] = set()
    for case in cases:
        for left_index, (left_name, _) in enumerate(axes):
            for right_name, _ in axes[left_index + 1 :]:
                covered.add(
                    (left_name, case[left_name], right_name, case[right_name])
                )

    required = {
        (left_name, left, right_name, right)
        for left_index, (left_name, left_values) in enumerate(axes)
        for right_name, right_values in axes[left_index + 1 :]
        for left in left_values
        for right in right_values
    }
    return required - covered


def edge_summary(model: dict[str, Any], cases: list[dict[str, str]]) -> str:
    """Render a compact edge-space contract for an implementation agent."""
    missing = missing_pairwise_coverage(model, cases)
    interactions = model.get("targeted_interactions", [])
    return "\n".join(
        [
            f"- axes: {len(model['axes'])}",
            f"- pairwise scenarios: {len(cases)}",
            f"- uncovered pairs: {len(missing)}",
            f"- targeted 3-way/high-risk interactions: {len(interactions)}",
            (
                "- regression rule: every confirmed bug keeps its minimal reproducer; "
                "generalizable bugs extend an axis or targeted interaction."
            ),
        ]
    )


def make_task_packet(task: Task, summary: str) -> str:
    """Build the immutable per-iteration implementation contract."""
    return f"""# DeepSearch atomic task packet

## Task
- ID: `{task.task_id}`
- Priority: `{task.priority}`
- Canonical plan: `{task.plan_path}`
- Plan fingerprint: `{task.fingerprint}`

## Mandatory execution contract
1. Work on this task only; split unrelated work into a later task.
2. Characterize current behavior before changing production behavior.
3. For a defect, create the smallest failing counterexample first.
4. Treat boundaries as a multidimensional space, not a flat list.
5. Use pairwise coverage routinely and explicit 3-way cases for coupled critical axes.
6. Keep unit tests hermetic; inject network/browser/storage faults behind boundaries.
7. Mechanical auto-fix may only format or apply deterministic linter fixes.
8. Semantic repair is test/invariant driven, capped, and must not weaken tests.
9. Respect file/line diff budgets and protected paths.
10. Success requires fast gates, full gates, and risk-required mutation testing.
11. Do not silently change public contracts, security policy, schemas, or dependencies.
12. After success, update devloop state and create one atomic commit.

## Multidimensional edge-space
{summary}

## Canonical plan section
{task.section}
"""
