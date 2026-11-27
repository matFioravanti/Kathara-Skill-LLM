"""Offline smoke tests for phased orchestration (no Docker or LLM)."""
from concurrent.futures import Future
from pathlib import Path
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from benchmark_core.experiment import RunCell, ResumeDecision
from benchmark_core.phased_execution import execute_phased
from benchmark_core.checker_runner import isolate_checker_copy
from benchmark_core.task_catalog import TaskAssignment


class InlinePool:
    """Deterministic substitute for a spawned process pool."""

    starts = []

    def __init__(self, max_workers, mp_context):
        self.max_workers = max_workers
        self.starts.append(max_workers)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def submit(self, fn, *args):
        future = Future()
        try:
            future.set_result(fn(*args))
        except BaseException as exc:
            future.set_exception(exc)
        return future


def test_isolation_changes_only_temporary_copy(tmp_path):
    original = tmp_path / "original.conf"
    original.write_text('LAB_NAME="Shared"\nr1[0]="A"\n')
    copy = tmp_path / "temporary.conf"
    copy.write_bytes(original.read_bytes())
    ident = isolate_checker_copy(copy)
    assert ident.startswith("ParallelChecker")
    assert f'LAB_NAME="{ident}"' in copy.read_text()
    assert 'r1[0]="A"' in copy.read_text()
    assert original.read_text().startswith('LAB_NAME="Shared"')
    assert isolate_checker_copy(copy) != ident


def test_isolation_adds_one_identity(tmp_path):
    conf = tmp_path / "lab.conf"
    conf.write_text('r1[0]="A"\n')
    identity = isolate_checker_copy(conf)
    assert conf.read_text().splitlines()[0] == f'LAB_NAME="{identity}"'


def test_generation_only_skips_checker_and_reuses_generated_lab(tmp_path):
    assignment = TaskAssignment('lab_03', 'base', 'large')
    cells = [RunCell('pilot', 'lab_03', 'T1', 'no_skill', n, assignment) for n in (1, 2)]
    decisions = [ResumeDecision(cell, True, 'missing') for cell in cells]
    config = SimpleNamespace(root=tmp_path, data={'docker_sandbox': {'execution_backend': 'docker_sandbox'}})
    existing = tmp_path / 'existing'
    calls = []

    def generated(cfg, scenario, agent, cell):
        calls.append(('generate', cell.replicate))
        return str(tmp_path / 'new'), 'AUT_COMPLETED'

    with (patch('benchmark_core.phased_execution.ProcessPoolExecutor', InlinePool),
          patch('benchmark_core.phased_execution.get_context', return_value=None),
          patch('benchmark_core.phased_execution.conditions', return_value={}),
          patch('benchmark_core.phased_execution.validate_artifacts', return_value={'aut_execution_success': True}),
          patch('benchmark_core.phased_execution.describe_run', return_value='existing'),
          patch('benchmark_core.phased_execution._generate', generated),
          patch('benchmark_core.phased_execution._evaluate', side_effect=AssertionError('checker must not run'))):
        failed = execute_phased(config, None, {'lab_03': object()}, 'codex', decisions,
                                {cells[0]: existing}, generation_workers=2,
                                checker_workers={'small': 1, 'medium': 1, 'large': 1},
                                update_reports=lambda: calls.append(('report', None)),
                                generation_only=True)
    assert not failed
    assert calls == [('generate', 2), ('report', None)]


def test_phased_order_with_two_workers(tmp_path):
    InlinePool.starts = []
    assignment = {
        level: TaskAssignment(lab, "base", level)
        for level, lab in (("small", "lab_01"), ("medium", "lab_02"), ("large", "lab_03"))
    }
    cells = [
        RunCell("thesis_final", item.lab_id, "T1", "no_skill", 3, item)
        for item in assignment.values()
    ]
    decisions = [ResumeDecision(cell, True, "missing") for cell in cells]
    config = SimpleNamespace(
        root=tmp_path,
        data={"docker_sandbox": {"execution_backend": "docker_sandbox"}},
    )
    state = []
    calls = []
    runs = {}

    def generated(cfg, scenario, agent, cell):
        state.append(("generate", cell.task_level))
        path = tmp_path / f"{cell.task_level}"
        path.mkdir()
        (path / "manifest.json").write_text('{"pipeline_state":"AUT_COMPLETED"}')
        runs[cell.task_level] = path
        return str(path), "AUT_COMPLETED"

    def evaluated(cfg, run_name):
        level = Path(run_name).name
        state.append(("check", level))
        return str(run_name), "COMPLETED"

    with patch("benchmark_core.phased_execution.ProcessPoolExecutor", InlinePool), \
         patch("benchmark_core.phased_execution._generate", generated), \
         patch("benchmark_core.phased_execution._evaluate", evaluated), \
         patch("benchmark_core.phased_execution.get_context", return_value=None):
        failed = execute_phased(
            config, SimpleNamespace(), {c.lab_id: object() for c in cells},
            "codex", decisions, {}, generation_workers=2,
            checker_workers={"small": 2, "medium": 2, "large": 1},
            update_reports=lambda: calls.append("aggregate"),
        )
    assert failed is False
    assert [x[0] for x in state] == ["generate"] * 3 + ["check"] * 3
    assert [x[1] for x in state[-3:]] == ["small", "medium", "large"]
    assert len(calls) == 4
    assert InlinePool.starts == [2, 2, 2, 1]


def test_invalid_worker_count_fails_closed(tmp_path):
    config = SimpleNamespace(root=tmp_path,
                             data={"docker_sandbox": {"execution_backend": "docker_sandbox"}})
    with pytest.raises(ValueError, match="generation_workers"):
        execute_phased(config, None, {}, "codex", [], {}, generation_workers=11,
                       checker_workers={"small": 2, "medium": 2, "large": 1},
                       update_reports=lambda: None)


@pytest.mark.parametrize("level, count", [
    ("small", 0),
    ("small", 7),
    ("medium", 7),
    ("large", 3),
])
def test_invalid_checker_count_fails_closed(tmp_path, level, count):
    config = SimpleNamespace(
        root=tmp_path,
        data={"docker_sandbox": {"execution_backend": "docker_sandbox"}},
    )
    counts = {"small": 4, "medium": 4, "large": 2}
    counts[level] = count
    with pytest.raises(ValueError, match=fr"checker_workers\[{level}\]"):
        execute_phased(config, None, {}, "codex", [], {},
                       generation_workers=5, checker_workers=counts,
                       update_reports=lambda: None)


def test_five_generators_and_four_checkers_keep_phase_boundaries(tmp_path):
    """Exercise configured worker limits and checker waves without Docker."""
    InlinePool.starts = []
    small = TaskAssignment("lab_01", "base", "small")
    medium = TaskAssignment("lab_02", "base", "medium")
    cells = [
        RunCell("thesis_final", assignment.lab_id, f"T{number}",
                "no_skill", 4, assignment)
        for assignment in (small, medium)
        for number in range(1, 6)
    ]
    decisions = [ResumeDecision(cell, True, "missing") for cell in cells]
    config = SimpleNamespace(
        root=tmp_path,
        data={"docker_sandbox": {"execution_backend": "docker_sandbox"}},
    )
    stages = []
    updates = []
    worker_limits = []

    def generated(cfg, scenario, agent, cell):
        stages.append(("generate", cell.task_level))
        worker_limits.append(cfg.data["parallel_execution"]["generation"]["workers"])
        assert cfg.data["parallel_execution"]["checker"]["small_workers"] == 4
        run = tmp_path / f"{cell.task_level}_{cell.prompt_type}"
        run.mkdir()
        (run / "manifest.json").write_text('{"pipeline_state":"AUT_COMPLETED"}')
        return str(run), "AUT_COMPLETED"

    def evaluated(cfg, run_name):
        level = Path(run_name).name.split("_", 1)[0]
        stages.append(("check", level))
        return str(run_name), "COMPLETED"

    with (
        patch("benchmark_core.phased_execution.ProcessPoolExecutor", InlinePool),
        patch("benchmark_core.phased_execution._generate", generated),
        patch("benchmark_core.phased_execution._evaluate", evaluated),
        patch("benchmark_core.phased_execution.get_context", return_value=None),
    ):
        failed = execute_phased(
            config, SimpleNamespace(), {cell.lab_id: object() for cell in cells},
            "codex", decisions, {}, generation_workers=5,
            checker_workers={"small": 4, "medium": 4, "large": 2},
            update_reports=lambda: updates.append("aggregate"),
        )

    assert failed is False
    assert stages[:10] == [("generate", cell.task_level) for cell in cells]
    assert stages[10:] == [("check", "small")] * 5 + [("check", "medium")] * 5
    assert InlinePool.starts == [5, 4, 4, 4, 4]
    assert len(updates) == 5  # generation + four checker waves
    assert worker_limits == [5] * 10
    assert "parallel_execution" not in config.data


@pytest.mark.parametrize("generators,checkers", [(5, 4), (10, 6)])
def test_real_spawn_pool_reaches_requested_limits_without_containers(tmp_path, generators, checkers):
    """Unlike InlinePool, this proves overlap in separate OS processes."""
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "probe"
    result = subprocess.run(
        [sys.executable, "-B", str(root / "scripts/verify_parallel_workers.py"),
         "--sandbox-workers", str(generators), "--checker-workers", str(checkers), "--output", str(output)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / "report.json").read_text())
    assert report["generation_peak"] == generators and len(report["generation_pids"]) == generators
    assert report["checker_peak"] == checkers and report["phases_separated"]
    assert report["sandbox_peak"] == report["actual_checker_process_peak"] == 0
    assert not report["failed"]
