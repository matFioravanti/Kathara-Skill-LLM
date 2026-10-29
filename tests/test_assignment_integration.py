"""Synthetic integration coverage: no agents, containers or DNS services are started."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from benchmark_core.aggregation import aggregate
from benchmark_core.config import load_config
from benchmark_core.experiment import (analyse_existing_runs, build_run_matrix,
    compute_resume_plan, load_experiment, validate_experiment_prerequisites)
from benchmark_core.pipeline import reevaluate_run, run_one
from benchmark_core.prompts import render_task_prompt
from benchmark_core.scenario_loader import discover_scenarios
from benchmark_core.task_catalog import TaskAssignment
from scripts.run_experiment import main
from scripts import run_benchmark


@pytest.fixture
def synthetic(tmp_path):
    lab = tmp_path / 'scenarios/lab_x/lab'
    lab.mkdir(parents=True)
    (lab / 'lab.conf').write_text('pc1[0]="net1"\n')
    (lab / 'pc1.startup').write_text('ip addr add 192.0.2.1/24 dev eth0\n')
    for tree, level in [('tree_x', 'small'), ('tree_x', 'large'), ('tree_y', 'small')]:
        prompt = tmp_path / 'prompt' / tree / level
        prompt.mkdir(parents=True)
        for t in ('T1', 'T2'):
            (prompt / f'{t}.md').write_text(f'{tree} {level} {t} {{{{server.device}}}} {{{{server.address}}}}\n')
        task = tmp_path / 'scenarios/lab_x/tasks' / tree / level
        task.mkdir(parents=True)
        (task / 'correction.yaml').write_text('lab_inline: |\n  pc1[0]="net1"\n')
        (task / 'bindings.yaml').write_text('server:\n  device: pc1\n  address: 192.0.2.1\n')
    spec = {'experiment': {'id': 'synthetic'}, 'assignments': [
        {'lab_id':'lab_x','dns_tree_id':'tree_x','task_levels':['small','large']},
        {'lab_id':'lab_x','dns_tree_id':'tree_y','task_levels':['small']}],
        'prompt_types':['T1','T2'], 'skill_modes':['no_skill'], 'repetitions':2}
    experiment = tmp_path / 'experiment.yaml'
    experiment.write_text(yaml.safe_dump(spec, sort_keys=False))
    base = yaml.safe_load((Path(__file__).parents[1] / 'benchmark.yaml').read_text())
    base['aut']['agent'] = 'codex'
    base['aut']['skill_protocol'] = 'explicit_read_v2'
    base['results']['directory'] = 'results'
    config_path = tmp_path / 'benchmark.yaml'
    config_path.write_text(yaml.safe_dump(base))
    return tmp_path, config_path, experiment


def test_full_synthetic_flow(synthetic, capsys):
    root, config_path, experiment = synthetic
    config = load_config(config_path)
    spec = load_experiment(experiment)
    labs = discover_scenarios(root / 'scenarios')
    validate_experiment_prerequisites(spec, config, labs)
    assert len(build_run_matrix(spec)) == 12
    assert main([str(experiment), '--config', str(config_path), '--lab', 'lab_x', '--dns-tree', 'tree_x', '--task-level', 'large', '--prompt-type', 'T1', '--dry-run']) == 0
    out = capsys.readouterr().out
    assert '2 osservazioni' in out and 'prompt/tree_x/large/T1.md' in out
    assert 'scenarios/lab_x/tasks/tree_x/large/correction.yaml' in out
    assert not (root / 'runs').exists()
    with patch('sys.argv', ['run_benchmark.py', '--experiment', str(experiment), '--config', str(config_path), '--dns-tree', 'tree_y', '--prompt-type', 'T2', '--dry-run']):
        assert run_benchmark.main() == 0
    assert 'prompt/tree_y/small/T2.md' in capsys.readouterr().out
    assignment = TaskAssignment('lab_x', 'tree_x', 'large')
    outcome = {'checks_passed': 0, 'checks_failed': 1, 'checks_total': 1, 'check_pass_rate': 0.0, 'task_success': False}
    def fake_aut(config, scenario, run, agent, prompt, **kwargs):
        assert not (run / 'evaluation/correction.yaml').exists()
        assert 'pc1 192.0.2.1' in prompt
        (run / 'lab/agent.txt').write_text('modified')
    with patch('benchmark_core.pipeline.component_versions', return_value={}), patch('benchmark_core.pipeline.run_aut', side_effect=fake_aut), patch('benchmark_core.pipeline.run_checker', return_value=outcome):
        run = run_one(config, labs['lab_x'], 'codex', 'T1', skill_mode='no_skill', experiment_id='synthetic', replicate=1, assignment=assignment)
        manifest = json.loads((run / 'manifest.json').read_text())
        assert manifest['pipeline_state'] == 'COMPLETED' and manifest['task_success'] is False
        assert (manifest['lab_id'], manifest['dns_tree_id'], manifest['task_level']) == ('lab_x','tree_x','large')
        assert not (labs['lab_x'].lab / 'agent.txt').exists()
        assert not (run / 'input/lab/agent.txt').exists()
        plan = compute_resume_plan(spec, analyse_existing_runs(root / 'runs', spec))
        skipped = [d.cell for d in plan if not d.should_run]
        assert len(skipped) == 1 and skipped[0].assignment == assignment and skipped[0].replicate == 1
        with patch('benchmark_core.pipeline.run_aut') as aut:
            reevaluate_run(config, run)
            aut.assert_not_called()
        assert (run / 'evaluation/history/revision_000/correction.yaml').exists()
        assert json.loads((run / 'manifest.json').read_text())['evaluation_revision'] == 1
    runs, _, summary = aggregate(root / 'runs', root / 'results')
    assert len(runs) == 1 and len(summary) == 1
    assert runs.iloc[0]['dns_tree_id'] == 'tree_x' and summary.iloc[0]['task_level'] == 'large'
    assert (root / 'results/benchmark.xlsx').is_file()
    assert main([str(experiment), '--config', str(config_path), '--dns-tree', 'tree_x', '--task-level', 'large', '--prompt-type', 'T1', '--resume', '--dry-run']) == 0
    assert 'SKIP lab_x/tree_x/large/T1/no_skill rep=1' in capsys.readouterr().out
    assert main([str(experiment), '--config', str(config_path), '--dns-tree', 'tree_x', '--task-level', 'large', '--rerun-correction', '--dry-run']) == 0
    assert 'RERUN runs/synthetic/lab_x/tree_x/large/T1/no_skill/r001' in capsys.readouterr().out


def test_bindings_reject_absent_ip_and_missing_resources(synthetic):
    root, config_path, experiment = synthetic
    assignment = TaskAssignment('lab_x','tree_x','small')
    binding = root / 'scenarios/lab_x/tasks/tree_x/small/bindings.yaml'
    binding.write_text('server: {device: pc1, address: 192.0.2.88}\n')
    with pytest.raises(ValueError, match='non presente'):
        render_task_prompt(root, assignment, 'T1')
    (root / 'prompt/tree_y/small/T2.md').unlink()
    with pytest.raises(ValueError):
        validate_experiment_prerequisites(load_experiment(experiment), load_config(config_path), discover_scenarios(root / 'scenarios'))


def test_distinct_trees_and_levels_have_distinct_run_ids_and_summaries(synthetic):
    root, config_path, experiment = synthetic
    config = load_config(config_path)
    labs = discover_scenarios(root / 'scenarios')
    outcome = {'checks_passed': 1, 'checks_failed': 0, 'checks_total': 1, 'check_pass_rate': 1.0, 'task_success': True}
    assignments = [TaskAssignment('lab_x', tree, level) for tree, level in
                   [('tree_x', 'small'), ('tree_x', 'large'), ('tree_y', 'small')]]
    runs = []
    with patch('benchmark_core.pipeline.component_versions', return_value={}), \
         patch('benchmark_core.pipeline.run_aut'), \
         patch('benchmark_core.pipeline.run_checker', return_value=outcome):
        for assignment in assignments:
            runs.append(run_one(config, labs['lab_x'], 'codex', 'T1', skill_mode='no_skill',
                                experiment_id='synthetic', replicate=1, assignment=assignment))
    assert len({json.loads((r / 'manifest.json').read_text())['run_id'] for r in runs}) == 3
    rows, _, summary = aggregate(root / 'runs', root / 'results')
    assert len(rows) == len(summary) == 3
    assert len([d for d in compute_resume_plan(load_experiment(experiment),
               analyse_existing_runs(root / 'runs', load_experiment(experiment))) if not d.should_run]) == 3


def test_antigravity_pipeline_keeps_existing_skill_treatment(synthetic):
    root, config_path, _ = synthetic
    config = load_config(config_path)
    skill = root / 'dns-skill.md'
    skill.write_text('synthetic skill\n')
    config.data['aut']['dns_skill'] = 'dns-skill.md'
    labs = discover_scenarios(root / 'scenarios')
    outcome = {'checks_passed': 1, 'checks_failed': 0, 'checks_total': 1, 'check_pass_rate': 1.0, 'task_success': True}
    with patch('benchmark_core.pipeline.component_versions', return_value={}), \
         patch('benchmark_core.pipeline.run_aut') as aut, \
         patch('benchmark_core.pipeline.run_checker', return_value=outcome):
        run = run_one(config, labs['lab_x'], 'antigravity', 'T1', experiment_id='synthetic',
                      replicate=1, assignment=TaskAssignment('lab_x', 'tree_y', 'small'))
    manifest = json.loads((run / 'manifest.json').read_text())
    assert manifest['pipeline_state'] == 'COMPLETED'
    assert manifest['agent'] == 'antigravity' and manifest['skill_mode'] == 'no_skill'
    assert aut.call_count == 1
