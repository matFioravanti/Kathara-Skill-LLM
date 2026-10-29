"""Check the committed Base resources and experiment plans without starting services."""
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from benchmark_core.config import load_config
from benchmark_core.experiment import build_run_matrix, load_experiment, validate_experiment_prerequisites
from benchmark_core.prompts import missing_prompts, render_task_prompt, resolve_prompt
from benchmark_core.scenario_loader import discover_scenarios
from benchmark_core.task_catalog import TaskAssignment, task_correction_path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ('technical_structured', 'technical_discursive', 'nontechnical_discursive',
              'nontechnical_unstructured', 'graphical_tree', 'json_structured')


@pytest.mark.parametrize('lab,level,offset', [('lab_01', 'small', 1),
                                               ('lab_02', 'medium', 2),
                                               ('lab_03', 'large', 3)])
def test_base_resources(lab, level, offset):
    assignment = TaskAssignment(lab, 'base', level)
    assert lab in discover_scenarios(ROOT / 'scenarios')
    assert task_correction_path(ROOT, assignment).is_file()
    for index, category in enumerate(CATEGORIES):
        kind = f'T{index + 1}'
        expected = ROOT / 'prompt' / 'base' / level / f'{3 * index + offset:02d}_{category}_{level}.md'
        assert resolve_prompt(ROOT, 'base', kind, level) == expected
        source, content = render_task_prompt(ROOT, assignment, kind)
        assert source == expected and content.strip()
        assert missing_prompts(ROOT, [assignment], kind) == []


def test_descriptive_precedence_and_legacy_fallback(tmp_path):
    directory = tmp_path / 'prompt/base/small'
    directory.mkdir(parents=True)
    legacy = directory / 'T1.md'
    legacy.write_text('legacy')
    assert resolve_prompt(tmp_path, 'base', 'T1', 'small') == legacy
    descriptive = directory / '01_technical_structured_small.md'
    descriptive.write_text('descriptive')
    assert resolve_prompt(tmp_path, 'base', 'T1', 'small') == descriptive


def test_experiment_plans_and_prerequisites():
    config = load_config(ROOT / 'benchmark.yaml')
    labs = discover_scenarios(ROOT / 'scenarios')
    quick = load_experiment(ROOT / 'experiments/quick_test.yaml')
    final = load_experiment(ROOT / 'experiments/thesis_final.yaml')
    for spec in (quick, final):
        validate_experiment_prerequisites(spec, config, labs)
    cells = build_run_matrix(quick)
    assert len(cells) == 1
    assert (cells[0].lab_id, cells[0].dns_tree_id, cells[0].task_level,
            cells[0].prompt_type, cells[0].skill_mode, cells[0].replicate) == (
                'lab_01', 'base', 'small', 'T1', 'dns_only', 1)
    cells = build_run_matrix(replace(final, repetitions=2))
    assert Counter((cell.skill_mode, cell.replicate) for cell in cells) == {
        (mode, repetition): 18 for mode in final.skill_modes for repetition in (1, 2)}
    assert all(cell.dns_tree_id == 'base' for cell in cells)
