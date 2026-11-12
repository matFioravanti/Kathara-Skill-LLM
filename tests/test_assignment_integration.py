"""Synthetic integration coverage: no agents, containers or DNS services are started."""
import json
import csv
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
from scripts import run_experiment
from scripts import run_benchmark


def write_checker_reports(run, outcome):
    reports = run / 'results'
    (reports / 'lab').mkdir(parents=True, exist_ok=True)
    def write(path, header, rows):
        with path.open('w', newline='') as file:
            writer = csv.writer(file); writer.writerow(header); writer.writerows(rows)
    passed = outcome['checks_passed']; failed = outcome['checks_failed']; total = outcome['checks_total']
    rows = [['synthetic check', 'True', 'OK'] for _ in range(passed)] + [['synthetic check', 'False', 'failed'] for _ in range(failed)]
    write(reports / 'results.csv', ['Student Name', 'Tests Passed', 'Tests Failed', 'Tests Total Number', 'Problems'], [['lab', passed, failed, total, '']])
    header = ['Test Description', 'Passed', 'Reason']
    write(reports / 'lab/lab_result_all.csv', header, rows)
    write(reports / 'lab/lab_result_failed.csv', header, rows[passed:])
    write(reports / 'lab/lab_result_summary.csv', ['Total Tests', 'Passed Tests', 'Failed'], [[total, passed, failed]])
    return outcome


@pytest.fixture
def synthetic(tmp_path):
    for lab_id in ('lab_01', 'lab_03'):
        lab = tmp_path / 'scenarios' / lab_id / 'lab'
        lab.mkdir(parents=True)
        (lab / 'lab.conf').write_text('pc1[0]="net1"\n')
        (lab / 'pc1.startup').write_text('ip addr add 192.0.2.1/24 dev eth0\n')
    for lab_id, tree, level in [('lab_01', 'aurora', 'small'), ('lab_03', 'aurora', 'large'), ('lab_01', 'aster', 'small')]:
        prompt = tmp_path / 'prompt' / tree / level
        prompt.mkdir(parents=True)
        for t in ('T1', 'T2'):
            (prompt / f'{t}.md').write_text(f'{tree} {level} {t} {{{{server.device}}}} {{{{server.address}}}}\n')
        task = tmp_path / 'scenarios' / lab_id / 'tasks' / tree / level
        task.mkdir(parents=True)
        (task / 'correction.yaml').write_text('lab_inline: |\n  pc1[0]="net1"\n')
        (task / 'bindings.yaml').write_text('server:\n  device: pc1\n  address: 192.0.2.1\n')
    spec = {'experiment': {'id': 'synthetic'}, 'assignments': [
        {'lab_id':'lab_01','dns_tree_id':'aurora','task_levels':['small']},
        {'lab_id':'lab_03','dns_tree_id':'aurora','task_levels':['large']},
        {'lab_id':'lab_01','dns_tree_id':'aster','task_levels':['small']}],
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
    assert main([str(experiment), '--config', str(config_path), '--lab', 'lab_03', '--dns-tree', 'aurora', '--task-level', 'large', '--prompt-type', 'T1', '--dry-run']) == 0
    out = capsys.readouterr().out
    assert '2 osservazioni' in out and 'prompt/aurora/large/T1.md' in out
    assert 'scenarios/lab_03/tasks/aurora/large/correction.yaml' in out
    assert not (root / 'runs').exists()
    with patch('sys.argv', ['run_benchmark.py', '--experiment', str(experiment), '--config', str(config_path), '--dns-tree', 'aster', '--prompt-type', 'T2', '--dry-run']):
        assert run_benchmark.main() == 0
    assert 'prompt/aster/small/T2.md' in capsys.readouterr().out
    assignment = TaskAssignment('lab_03', 'aurora', 'large')
    outcome = {'checks_passed': 0, 'checks_failed': 1, 'checks_total': 1, 'check_pass_rate': 0.0, 'task_success': False}
    def fake_aut(config, scenario, run, agent, prompt, **kwargs):
        assert not (run / 'evaluation/correction.yaml').exists()
        assert 'pc1 192.0.2.1' in prompt
        (run / 'lab/agent.txt').write_text('modified')
    with patch('benchmark_core.pipeline.component_versions', return_value={}), patch('benchmark_core.pipeline.run_aut', side_effect=fake_aut), patch('benchmark_core.pipeline.run_checker', side_effect=lambda config, run, correction: write_checker_reports(run, outcome)):
        run = run_one(config, labs['lab_03'], 'codex', 'T1', skill_mode='no_skill', experiment_id='synthetic', replicate=1, assignment=assignment)
        manifest = json.loads((run / 'manifest.json').read_text())
        assert manifest['pipeline_state'] == 'COMPLETED' and manifest['task_success'] is False
        assert (manifest['lab_id'], manifest['dns_tree_id'], manifest['task_level']) == ('lab_03','aurora','large')
        assert not (labs['lab_03'].lab / 'agent.txt').exists()
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
    assert runs.iloc[0]['dns_tree_id'] == 'aurora' and summary.iloc[0]['task_level'] == 'large'
    assert (root / 'results/benchmark.xlsx').is_file()
    assert main([str(experiment), '--config', str(config_path), '--dns-tree', 'aurora', '--task-level', 'large', '--prompt-type', 'T1', '--resume', '--dry-run']) == 0
    assert 'SKIP lab_03/aurora/large/T1/no_skill rep=1' in capsys.readouterr().out
    assert main([str(experiment), '--config', str(config_path), '--dns-tree', 'aurora', '--task-level', 'large', '--rerun-correction', '--dry-run']) == 0
    assert 'RERUN runs/synthetic/lab_03/aurora/large/T1/no_skill/r001' in capsys.readouterr().out


@pytest.mark.parametrize('third_state, expected_action', [
    (None, 'RUN'), ('AUT_FAILED', 'RUN'), ('COMPLETED', 'SKIP'),
])
def test_only_replicate_resume_uses_logical_number(synthetic, capsys, third_state, expected_action):
    root, config_path, experiment = synthetic
    mode = root / 'runs/synthetic/lab_03/aurora/large/T1/no_skill'

    def existing_run(directory, replicate, state):
        run = mode / directory
        run.mkdir(parents=True)
        manifest = {'experiment_id': 'synthetic', 'lab_id': 'lab_03',
                    'dns_tree_id': 'aurora', 'task_level': 'large', 'prompt_type': 'T1',
                    'skill_mode': 'no_skill', 'replicate': replicate, 'pipeline_state': state}
        if state == 'COMPLETED':
            from benchmark_core.fingerprint import conditions, fingerprint
            config = load_config(config_path)
            scenario = discover_scenarios(root / 'scenarios')['lab_03']
            assignment = TaskAssignment('lab_03', 'aurora', 'large')
            values = conditions(config, scenario, 'T1', 'no_skill', assignment)
            manifest.update(run_id='fixture', checker_execution_success=True, task_success=True,
                            correction_sha256=values['correction_sha256'], experimental_conditions=values,
                            experimental_fingerprint=fingerprint(values))
            (run / 'evaluation').mkdir(); (run / 'lab').mkdir(); (run / 'input/lab').mkdir(parents=True)
            (run / 'evaluation/correction.yaml').write_bytes((root / 'scenarios/lab_03/tasks/aurora/large/correction.yaml').read_bytes())
            (run / 'evaluation/metrics.json').write_text(json.dumps({'run_id':'fixture','replicate':replicate,'status':'COMPLETED','experiment_id':'synthetic','lab_id':'lab_03','dns_tree_id':'aurora','task_level':'large','prompt_type':'T1','skill_mode':'no_skill','checker':{'passed':1,'failed':0,'total':1}}))
            write_checker_reports(run, {'checks_passed':1,'checks_failed':0,'checks_total':1})
        (run / 'manifest.json').write_text(json.dumps(manifest))
        (run / 'log.txt').write_text(f'original {directory}')

    # The physical directory number does not identify the logical replicate.
    # Replicate 1 is missing, and replicate 2 has failed.
    existing_run('r003', 2, 'AUT_FAILED')
    if third_state is not None:
        existing_run('r001', 3, third_state)
    original = {p: p.read_bytes() for p in mode.rglob('*') if p.is_file()}
    args = [str(experiment), '--config', str(config_path), '--lab', 'lab_03',
            '--dns-tree', 'aurora', '--task-level', 'large', '--prompt-type', 'T1',
            '--skill-mode', 'no_skill', '--repetitions', '3', '--only-replicate', '3', '--resume']
    assert main(args + ['--dry-run']) == 0
    output = capsys.readouterr().out
    assert f'1 osservazioni, {int(expected_action == "RUN")} da eseguire' in output
    assert f'{expected_action} lab_03/aurora/large/T1/no_skill rep=3' in output
    assert 'rep=1' not in output and 'rep=2' not in output

    outcome = {'checks_passed': 1, 'checks_failed': 0, 'checks_total': 1,
               'check_pass_rate': 1.0, 'task_success': True}
    with patch.object(run_experiment, 'preflight'), \
         patch.object(run_experiment, 'run_one', run_one), \
         patch.object(run_experiment, 'aggregate'), \
         patch.object(run_experiment, '_notify_benchmark_finished'), \
         patch('benchmark_core.pipeline.component_versions', return_value={}), \
         patch('benchmark_core.pipeline.run_aut') as aut, \
         patch('benchmark_core.pipeline.run_checker', return_value=outcome):
        assert main(args) == 0
    assert aut.call_count == int(expected_action == 'RUN')
    assert all(path.read_bytes() == contents for path, contents in original.items())
    if expected_action == 'RUN':
        new_manifest = json.loads((mode / 'r004/manifest.json').read_text())
        assert new_manifest['replicate'] == 3


def test_only_replicate_filters_without_resume_and_validates_range(synthetic, capsys):
    _, config_path, experiment = synthetic
    args = [str(experiment), '--config', str(config_path), '--prompt-type', 'T1']
    assert main(args + ['--repetitions', '3', '--only-replicate', '3', '--dry-run']) == 0
    output = capsys.readouterr().out
    assert '3 osservazioni, 3 da eseguire' in output
    assert output.count(' rep=3 ') == 3
    assert 'rep=1' not in output and 'rep=2' not in output
    for value in ('0', '-1', '3'):
        assert main(args + ['--only-replicate', value, '--dry-run']) == 1
        assert '--only-replicate deve essere compreso tra 1 e 2' in capsys.readouterr().err
    assert main(args + ['--only-replicate', '1', '--rerun-correction', '--dry-run']) == 1
    assert '--only-replicate non si applica alla rivalutazione' in capsys.readouterr().err


def test_interrupted_finalization_is_not_completed(synthetic):
    from benchmark_core import pipeline
    root, config_path, _ = synthetic
    config = load_config(config_path)
    scenario = discover_scenarios(root / 'scenarios')['lab_03']
    assignment = TaskAssignment('lab_03', 'aurora', 'large')
    outcome = {'checks_passed':1, 'checks_failed':0, 'checks_total':1, 'check_pass_rate':1.0, 'task_success':True}
    original = pipeline.write_json
    def interrupted(path, data):
        if path.name == 'metrics.json':
            raise OSError('simulated interrupted metrics write')
        return original(path, data)
    with patch.object(pipeline, 'component_versions', return_value={}), \
         patch.object(pipeline, 'run_aut'), patch.object(pipeline, 'run_checker', side_effect=lambda config, run, correction: write_checker_reports(run, outcome)), \
         patch.object(pipeline, 'write_json', side_effect=interrupted):
        with pytest.raises(OSError, match='simulated interrupted'):
            run_one(config, scenario, 'codex', 'T1', skill_mode='no_skill', experiment_id='synthetic', replicate=3, assignment=assignment)
    run = root / 'runs/synthetic/lab_03/aurora/large/T1/no_skill/r001'
    assert json.loads((run / 'manifest.json').read_text())['pipeline_state'] == 'FINALIZING'
    assert not (run / 'evaluation/metrics.json').exists()
    from scripts.recover_metrics import recover
    before = (run / 'manifest.json').read_bytes()
    recovered = recover(run, root / 'recovered')
    assert json.loads((recovered / 'metrics.json').read_text())['checker']['total'] == 1
    assert (run / 'manifest.json').read_bytes() == before and not (run / 'evaluation/metrics.json').exists()
    with pytest.raises(ValueError, match='esterna'):
        recover(run, root / 'runs/recovered')
    args = [str(root/'experiment.yaml'), '--config', str(config_path), '--lab', 'lab_03', '--prompt-type', 'T1',
            '--repetitions', '3', '--only-replicate', '3', '--resume', '--dry-run']
    # A valid final AUT checkpoint is now recoverable, rather than a conflict.
    assert main(args) == 0


def test_resume_requires_complete_and_compatible_observation(synthetic, capsys):
    root, config_path, experiment = synthetic
    config = load_config(config_path)
    scenario = discover_scenarios(root / 'scenarios')['lab_03']
    assignment = TaskAssignment('lab_03', 'aurora', 'large')
    outcome = {'checks_passed':0, 'checks_failed':1, 'checks_total':1, 'check_pass_rate':0.0, 'task_success':False}
    with patch('benchmark_core.pipeline.component_versions', return_value={}), \
         patch('benchmark_core.pipeline.run_aut'), \
         patch('benchmark_core.pipeline.run_checker', side_effect=lambda config, run, correction: write_checker_reports(run, outcome)):
        run = run_one(config, scenario, 'codex', 'T1', skill_mode='no_skill', experiment_id='synthetic', replicate=3, assignment=assignment)
    args = [str(experiment), '--config', str(config_path), '--lab', 'lab_03', '--dns-tree', 'aurora',
            '--task-level', 'large', '--prompt-type', 'T1', '--skill-mode', 'no_skill', '--repetitions', '3',
            '--only-replicate', '3', '--resume', '--dry-run']
    assert main(args) == 0 and 'SKIP' in capsys.readouterr().out
    metric = run / 'evaluation/metrics.json'; original_metrics = metric.read_text()
    metric.unlink()
    assert main(args) == 1 and 'incompleti' in capsys.readouterr().err
    metric.write_text(original_metrics)
    config_data = yaml.safe_load(config_path.read_text()); config_data['aut']['reasoning_effort'] = 'high'
    config_path.write_text(yaml.safe_dump(config_data))
    assert main(args) == 1 and 'reasoning_effort' in capsys.readouterr().err
    config_data['aut']['reasoning_effort'] = config.reasoning_effort()
    config_path.write_text(yaml.safe_dump(config_data))
    path = run/'manifest.json'; manifest=json.loads(path.read_text())
    manifest.pop('experimental_conditions'); manifest.pop('experimental_fingerprint'); path.write_text(json.dumps(manifest))
    assert main(args) == 1 and 'unverified' in capsys.readouterr().err
    assert main(args + ['--resume-allow-unverified']) == 0
    assert 'AVVISO' in capsys.readouterr().out


def test_experiment_lock_blocks_a_second_launcher(synthetic, tmp_path, monkeypatch, capsys):
    import fcntl
    import hashlib
    root, config_path, experiment = synthetic
    monkeypatch.setattr(run_experiment.tempfile, 'gettempdir', lambda: str(tmp_path))
    lock_root = tmp_path / 'kathara-experiment-locks'; lock_root.mkdir()
    lock_id = hashlib.sha256(f'{root.resolve()}\0synthetic'.encode()).hexdigest()
    with (lock_root / f'{lock_id}.lock').open('a+') as existing:
        fcntl.flock(existing.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main([str(experiment), '--config', str(config_path), '--lab', 'lab_03']) == 1
        assert 'già in esecuzione' in capsys.readouterr().err


def test_notification_follows_all_runs_and_aggregation(synthetic):
    _, config_path, experiment = synthetic
    config = yaml.safe_load(config_path.read_text())
    config['benchmark']['continue_on_error'] = True
    config_path.write_text(yaml.safe_dump(config))
    events = []

    def failed_run(*args, **kwargs):
        events.append('run')
        raise RuntimeError('synthetic failure')

    args = [str(experiment), '--config', str(config_path), '--lab', 'lab_03',
            '--prompt-type', 'T1']
    with patch.object(run_experiment, 'preflight'), \
         patch.object(run_experiment, 'run_one', side_effect=failed_run), \
         patch.object(run_experiment, 'aggregate', side_effect=lambda *a, **kw: events.append('aggregate')), \
         patch.object(run_experiment, '_notify_benchmark_finished', side_effect=lambda: events.append('notify')):
        assert main(args + ['--dry-run']) == 0
        assert events == []
        assert main(args) == 1
    assert events == ['run', 'aggregate', 'run', 'aggregate', 'notify']


def test_notification_is_best_effort_and_macos_only():
    with patch.object(run_experiment.sys, 'platform', 'darwin'), \
         patch.object(run_experiment.subprocess, 'Popen', side_effect=OSError('no audio')) as play:
        run_experiment._notify_benchmark_finished()
        assert play.call_count == 1
    with patch.object(run_experiment.sys, 'platform', 'linux'), \
         patch.object(run_experiment.subprocess, 'Popen') as play:
        run_experiment._notify_benchmark_finished()
        play.assert_not_called()


def test_bindings_reject_absent_ip_and_missing_resources(synthetic):
    root, config_path, experiment = synthetic
    assignment = TaskAssignment('lab_01','aurora','small')
    binding = root / 'scenarios/lab_01/tasks/aurora/small/bindings.yaml'
    binding.write_text('server: {device: pc1, address: 192.0.2.88}\n')
    with pytest.raises(ValueError, match='non presente'):
        render_task_prompt(root, assignment, 'T1')
    (root / 'prompt/aster/small/T2.md').unlink()
    with pytest.raises(ValueError):
        validate_experiment_prerequisites(load_experiment(experiment), load_config(config_path), discover_scenarios(root / 'scenarios'))


def test_distinct_trees_and_levels_have_distinct_run_ids_and_summaries(synthetic):
    root, config_path, experiment = synthetic
    config = load_config(config_path)
    labs = discover_scenarios(root / 'scenarios')
    outcome = {'checks_passed': 1, 'checks_failed': 0, 'checks_total': 1, 'check_pass_rate': 1.0, 'task_success': True}
    assignments = [TaskAssignment(lab, tree, level) for lab, tree, level in
                   [('lab_01', 'aurora', 'small'), ('lab_03', 'aurora', 'large'), ('lab_01', 'aster', 'small')]]
    runs = []
    with patch('benchmark_core.pipeline.component_versions', return_value={}), \
         patch('benchmark_core.pipeline.run_aut'), \
         patch('benchmark_core.pipeline.run_checker', side_effect=lambda config, run, correction: write_checker_reports(run, outcome)):
        for assignment in assignments:
            runs.append(run_one(config, labs[assignment.lab_id], 'codex', 'T1', skill_mode='no_skill',
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
        run = run_one(config, labs['lab_01'], 'antigravity', 'T1', experiment_id='synthetic',
                      replicate=1, assignment=TaskAssignment('lab_01', 'aster', 'small'))
    manifest = json.loads((run / 'manifest.json').read_text())
    assert manifest['pipeline_state'] == 'COMPLETED'
    assert manifest['agent'] == 'antigravity' and manifest['skill_mode'] == 'no_skill'
    assert aut.call_count == 1
