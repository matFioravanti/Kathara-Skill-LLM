from pathlib import Path

import pytest

from benchmark_core.task_catalog import (
    TaskAssignment, discover_dns_trees, parse_assignments, prompt_path,
    task_correction_path,
)


def test_assignments_are_explicit_and_duplicates_rejected():
    entries = [
        {"lab_id": "lab1", "dns_tree_id": "aurora", "task_levels": ["small", "large"]},
        {"lab_id": "lab1", "dns_tree_id": "aster", "task_levels": ["medium"]},
    ]
    assert parse_assignments(entries) == (
        TaskAssignment("lab1", "aurora", "small"),
        TaskAssignment("lab1", "aurora", "large"),
        TaskAssignment("lab1", "aster", "medium"),
    )
    with pytest.raises(ValueError, match="duplicata"):
        parse_assignments(entries + [entries[0]])


def test_paths_distinguish_levels_and_reject_unsafe_ids(tmp_path):
    small = TaskAssignment("lab1", "aurora", "small")
    large = TaskAssignment("lab1", "aurora", "large")
    assert task_correction_path(tmp_path, small) != task_correction_path(tmp_path, large)
    assert prompt_path(tmp_path, "aurora", "small", "T1") == tmp_path / "prompt/aurora/small/T1.md"
    with pytest.raises(ValueError):
        TaskAssignment("../lab", "aurora", "small")
    with pytest.raises(ValueError):
        prompt_path(tmp_path, "aurora", "medium", "T7")


def test_discovery_reports_only_present_levels(tmp_path):
    (tmp_path / "prompt/aurora/large").mkdir(parents=True)
    (tmp_path / "prompt/aurora/small").mkdir()
    (tmp_path / "prompt/aster").mkdir()
    assert discover_dns_trees(tmp_path) == {"aurora": ("small", "large")}
