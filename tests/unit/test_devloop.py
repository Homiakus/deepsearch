from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from tools import devloop, devloop_mutation
from tools.devloop_core import DevLoopError


def _model() -> dict[str, object]:
    return {
        "axes": {
            "size": ["empty", "one", "many"],
            "state": ["fresh", "retrying", "cancelled"],
            "dependency": ["ok", "timeout", "malformed"],
            "ordering": ["stable", "reversed"],
        },
        "targeted_interactions": [],
    }


def test_pairwise_generator_is_complete_and_smaller_than_cartesian() -> None:
    model = _model()
    cases = devloop.generate_pairwise_cases(model)

    assert not devloop.missing_pairwise_coverage(model, cases)

    cartesian_size = 1
    for values in model["axes"].values():
        cartesian_size *= len(values)
    assert len(cases) < cartesian_size


def test_pairwise_generator_is_deterministic() -> None:
    model = _model()
    assert devloop.generate_pairwise_cases(model) == devloop.generate_pairwise_cases(
        model
    )


def test_pairwise_cases_cover_every_value_pair() -> None:
    model = _model()
    cases = devloop.generate_pairwise_cases(model)
    axes = list(model["axes"].items())

    for left_index, (left_name, left_values) in enumerate(axes):
        for right_name, right_values in axes[left_index + 1 :]:
            required = set(itertools.product(left_values, right_values))
            observed = {(case[left_name], case[right_name]) for case in cases}
            assert required <= observed


def test_plan_parser_extracts_atomic_ds_sections(tmp_path: Path) -> None:
    plan = tmp_path / "PLAN.md"
    plan.write_text(
        """# Plan

### DS-01 — First boundary

**Приоритет:** P0

**Что делаем:** one.

### DS-02 — Second boundary

**Приоритет:** P2

**Что делаем:** two.
""",
        encoding="utf-8",
    )

    tasks = devloop.parse_plan(plan)

    assert [task.task_id for task in tasks] == ["DS-01", "DS-02"]
    assert [task.priority for task in tasks] == ["P0", "P2"]
    assert "one." in tasks[0].section
    assert "two." not in tasks[0].section


def test_completed_task_reopens_when_plan_fingerprint_changes(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "PLAN.md"
    plan.write_text(
        """### DS-01 — Contract

**Приоритет:** P1

**Что делаем:** version one.
""",
        encoding="utf-8",
    )
    config = {"plan": {"canonical": str(plan)}}
    first = devloop.next_task(config, {"completed": {}})
    assert first is not None

    state = {
        "completed": {
            first.task_id: {
                "plan_fingerprint": first.fingerprint,
            }
        }
    }
    assert devloop.next_task(config, state) is None

    plan.write_text(
        """### DS-01 — Contract

**Приоритет:** P1

**Что делаем:** version two.
""",
        encoding="utf-8",
    )
    reopened = devloop.next_task(config, state)
    assert reopened is not None
    assert reopened.fingerprint != first.fingerprint


def test_task_packet_forbids_test_weakening() -> None:
    task = devloop.Task(
        task_id="DS-99",
        title="Guard",
        priority="P0",
        plan_path="PLAN.md",
        section="### DS-99 — Guard\n",
    )
    packet = devloop.make_task_packet(task, "- pairwise scenarios: 7")
    assert "must not weaken tests" in packet.lower()
    assert "multidimensional" in packet.lower()


def _write_mutmut_stats(root: Path, **stats: int) -> None:
    directory = root / "mutants"
    directory.mkdir(parents=True)
    (directory / "mutmut-cicd-stats.json").write_text(
        json.dumps(stats),
        encoding="utf-8",
    )


def test_python_mutation_gate_enforces_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(devloop_mutation, "ROOT", tmp_path)
    _write_mutmut_stats(
        tmp_path,
        total=10,
        skipped=0,
        killed=7,
        survived=3,
    )

    with pytest.raises(DevLoopError, match="below"):
        devloop_mutation._enforce_mutmut_stats(
            min_score=80.0,
            require_zero_survivors=False,
        )


def test_python_mutation_gate_rejects_survivors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(devloop_mutation, "ROOT", tmp_path)
    _write_mutmut_stats(
        tmp_path,
        total=10,
        skipped=0,
        killed=9,
        survived=1,
    )

    with pytest.raises(DevLoopError, match="surviving"):
        devloop_mutation._enforce_mutmut_stats(
            min_score=80.0,
            require_zero_survivors=True,
        )


def test_python_mutation_gate_accepts_strong_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(devloop_mutation, "ROOT", tmp_path)
    _write_mutmut_stats(
        tmp_path,
        total=10,
        skipped=0,
        killed=10,
        survived=0,
    )

    devloop_mutation._enforce_mutmut_stats(
        min_score=80.0,
        require_zero_survivors=True,
    )
