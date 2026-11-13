"""Offline smoke tests for phased orchestration (no Docker or LLM)."""
from concurrent.futures import Future
from pathlib import Path
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
        execute_phased(config, None, {}, "codex", [], {}, generation_workers=3,
                       checker_workers={"small": 2, "medium": 2, "large": 1},
                       update_reports=lambda: None)
