from pathlib import Path

import pytest
import yaml

from benchmark_core.experiment import build_run_matrix, load_experiment, validate_experiment_prerequisites
from benchmark_core.config import Config
from benchmark_core.prompts import resolve_prompt
from benchmark_core.scenario_loader import discover_scenarios
from benchmark_core.task_catalog import (
    DNS_TREES, LAB_LEVELS, TaskAssignment, discover_dns_trees, parse_assignments,
    historical_correction_path, prompt_path, task_correction_path,
)


def test_assignments_are_explicit_and_duplicates_rejected():
    entries = [
        {'lab_id': 'lab_01', 'dns_tree_id': 'aurora', 'task_levels': ['small']},
        {'lab_id': 'lab_03', 'dns_tree_id': 'aurora', 'task_levels': ['large']},
        {'lab_id': 'lab_02', 'dns_tree_id': 'aster', 'task_levels': ['medium']},
    ]
    assert parse_assignments(entries) == (
        TaskAssignment('lab_01', 'aurora', 'small'),
        TaskAssignment('lab_03', 'aurora', 'large'),
        TaskAssignment('lab_02', 'aster', 'medium'),
    )
    with pytest.raises(ValueError, match='duplicata'):
        parse_assignments(entries + [entries[0]])


@pytest.mark.parametrize('lab,level', list(LAB_LEVELS.items()))
@pytest.mark.parametrize('tree', DNS_TREES)
def test_only_allowed_level_for_each_lab_and_tree(lab, level, tree):
    assert TaskAssignment(lab, tree, level).task_level == level
    for invalid in {'small', 'medium', 'large'} - {level}:
        with pytest.raises(ValueError, match='incompatibile'):
            TaskAssignment(lab, tree, invalid)
        with pytest.raises(ValueError, match='incompatibile'):
            parse_assignments([{'lab_id': lab, 'dns_tree_id': tree, 'task_levels': [invalid]}])


def test_paths_distinguish_levels_and_reject_unsafe_ids(tmp_path):
    small = TaskAssignment('lab_01', 'aurora', 'small')
    large = TaskAssignment('lab_03', 'aurora', 'large')
    assert task_correction_path(tmp_path, small) == tmp_path / 'scenarios/lab_01/tasks/aurora/small/correction.yaml'
    assert task_correction_path(tmp_path, small) != task_correction_path(tmp_path, large)
    assert prompt_path(tmp_path, 'aurora', 'small', 'T1') == tmp_path / 'prompt/aurora/small/T1.md'
    with pytest.raises(ValueError):
        TaskAssignment('../lab', 'aurora', 'small')
    with pytest.raises(ValueError):
        TaskAssignment('lab_01', 'other', 'small')
    with pytest.raises(ValueError):
        TaskAssignment('unknown', 'aurora', 'small')
    with pytest.raises(ValueError):
        prompt_path(tmp_path, 'aurora', 'medium', 'T7')


def test_matrix_contains_only_declared_nine_assignments(tmp_path):
    entries = [{'lab_id': lab, 'dns_tree_id': tree, 'task_levels': [level]}
               for lab, level in LAB_LEVELS.items() for tree in DNS_TREES]
    data = {'experiment': {'id': 'test'}, 'assignments': entries,
            'prompt_types': ['T1', 'T2', 'T3', 'T4', 'T5'],
            'skill_modes': ['no_skill', 'creation_only', 'dns_only', 'both_forced', 'auto'],
            'repetitions': 1}
    path = tmp_path / 'experiment.yaml'
    path.write_text(yaml.safe_dump(data))
    spec = load_experiment(path)
    cells = build_run_matrix(spec)
    assert len(cells) == 225
    assert {cell.assignment for cell in cells} == set(parse_assignments(entries))
    data['assignments'][0]['task_levels'] = ['medium']
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='incompatibile'):
        load_experiment(path)


def test_placeholders_are_not_resources(tmp_path):
    lab = tmp_path / 'scenarios/lab_01/lab'
    lab.mkdir(parents=True)
    (lab / '.gitkeep').touch()
    prompt = tmp_path / 'prompt/aurora/small'
    prompt.mkdir(parents=True)
    (prompt / '.gitkeep').touch()
    task = tmp_path / 'scenarios/lab_01/tasks/aurora/small'
    task.mkdir(parents=True)
    (task / '.gitkeep').touch()
    assert discover_scenarios(tmp_path / 'scenarios') == {}
    with pytest.raises(ValueError):
        resolve_prompt(tmp_path, 'aurora', 'T1', 'small')
    data = {'experiment': {'id': 'test'}, 'assignments': [{'lab_id': 'lab_01', 'dns_tree_id': 'aurora', 'task_levels': ['small']}],
            'prompt_types': ['T1'], 'skill_modes': ['no_skill'], 'repetitions': 1}
    path = tmp_path / 'experiment.yaml'
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        validate_experiment_prerequisites(load_experiment(path), Config(tmp_path, {}), {})


def test_discovery_reports_only_present_levels(tmp_path):
    (tmp_path / 'prompt/aurora/large').mkdir(parents=True)
    (tmp_path / 'prompt/aurora/small').mkdir()
    (tmp_path / 'prompt/aster').mkdir()
    assert discover_dns_trees(tmp_path) == {'aurora': ('small', 'large')}


def test_historical_identity_is_preserved_without_reclassification(tmp_path):
    assert historical_correction_path(tmp_path, 'older_lab', 'older_tree', 'medium') == (
        tmp_path / 'scenarios/older_lab/tasks/older_tree/medium/correction.yaml'
    )
    with pytest.raises(ValueError):
        historical_correction_path(tmp_path, '../outside', 'older_tree', 'medium')
