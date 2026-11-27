import csv
import importlib.util
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/evaluate_existing_labs.py'
spec = importlib.util.spec_from_file_location('evaluate_existing_labs', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_run(root, prompt='T1', replicate=1, success=True):
    run = root / 'runs' / 'experiment' / 'lab_01' / 'base' / 'small' / prompt / 'dns_only' / f'r{replicate:03d}'
    (run / 'lab').mkdir(parents=True)
    (run / 'input/lab').mkdir(parents=True)
    (run / 'lab/lab.conf').write_text('original lab')
    (run / 'input/lab/lab.conf').write_text('baseline')
    (run / 'manifest.json').write_text(json.dumps({'execution_id': f'{prompt}-{replicate}',
        'observation_id': f'{prompt}-{replicate}', 'aut_execution_success': success,
        'task_level': 'small', 'prompt_type': prompt, 'skill_mode': 'dns_only', 'replicate': replicate}))
    return run


def test_selection_respects_filters_and_rejects_incomplete(tmp_path):
    first = fixture_run(tmp_path, replicate=1)
    fixture_run(tmp_path, replicate=2)
    fixture_run(tmp_path, prompt='T2', success=False)
    assert [r for r, _ in module.select_runs(tmp_path / 'runs', prompt_type='T1', replicate=1)] == [first]
    with pytest.raises(ValueError, match='generazione completa'):
        module.select_runs(tmp_path / 'runs')


def test_separate_results_and_technical_failures(tmp_path, monkeypatch):
    first = fixture_run(tmp_path, replicate=1)
    second = fixture_run(tmp_path, replicate=2)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'read_correction', lambda p: (b'valid correction', 'hash'))
    monkeypatch.setattr(module, 'validate_correction_lab', lambda correction, lab: None)
    monkeypatch.setattr(module, 'load_config', lambda p: SimpleNamespace(data={'checker': {}, 'benchmark': {'timeout_seconds': 10}}))
    config = tmp_path / 'config.yaml'
    config.write_text('config')
    correction = tmp_path / 'custom.yaml'
    correction.write_text('correction')
    calls = []

    def checker(config, run, correction, isolated):
        assert isolated and (run / 'lab/lab.conf').read_text() == 'original lab'
        (run / 'lab/lab.conf').write_text('temporary modification')
        calls.append(run)
        if len(calls) == 2:
            raise RuntimeError('checker unavailable')
        return {'task_success': False, 'checks_passed': 1, 'checks_failed': 1, 'checks_total': 2}

    monkeypatch.setattr(module, 'run_checker', checker)
    monkeypatch.setattr(module, 'parse_reports', lambda p: ({}, [{'Test Description': 'DNS', 'Passed': 'False', 'Reason': 'REFUSED'}]))
    output = tmp_path / 'results/general/new'
    argv = ['--correction', str(correction), '--runs', str(tmp_path / 'runs'), '--output', str(output), '--config', str(config)]
    assert module.main(argv + ['--dry-run']) == 0
    assert not output.exists()
    assert module.main(argv) == 1
    assert (first / 'lab/lab.conf').read_text() == (second / 'lab/lab.conf').read_text() == 'original lab'
    assert json.loads((output / 'manifest.json').read_text())['expected_runs'] == 2
    rows = list(csv.DictReader((output / 'runs.csv').open()))
    assert [r['status'] for r in rows] == ['COMPLETED', 'CHECKER_FAILED']
    summary = list(csv.DictReader((output / 'summary.csv').open()))[0]
    assert (summary['failed'], summary['technical_errors']) == ('1', '1')
    assert list(csv.DictReader((output / 'checks.csv').open()))[0]['reason'] == 'REFUSED'
    assert (output / 'benchmark.xlsx').is_file()
    assert module.main(argv) == 1


def test_two_checkers_execute_concurrently_with_isolated_results(tmp_path, monkeypatch):
    fixture_run(tmp_path, replicate=1)
    fixture_run(tmp_path, replicate=2)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'read_correction', lambda p: (b'valid correction', 'hash'))
    monkeypatch.setattr(module, 'validate_correction_lab', lambda correction, lab: None)
    monkeypatch.setattr(module, 'load_config', lambda p: SimpleNamespace(data={'checker': {}, 'benchmark': {'timeout_seconds': 10}}))
    config = tmp_path / 'config.yaml'
    config.write_text('config')
    correction = tmp_path / 'custom.yaml'
    correction.write_text('correction')
    barrier = threading.Barrier(2, timeout=5)
    seen = []

    def checker(config, run, correction, isolated):
        assert isolated
        seen.append((run, (run / 'results').resolve()))
        barrier.wait()
        return {'task_success': True, 'checks_passed': 1, 'checks_failed': 0, 'checks_total': 1}

    monkeypatch.setattr(module, 'run_checker', checker)
    monkeypatch.setattr(module, 'parse_reports', lambda p: ({}, []))
    output = tmp_path / 'results/general/new'
    result = module.main(['--correction', str(correction), '--runs', str(tmp_path / 'runs'),
                          '--output', str(output), '--config', str(config), '--checker-workers', '2'])
    assert result == 0
    assert len(seen) == 2 and seen[0][0] != seen[1][0] and seen[0][1] != seen[1][1]
    assert json.loads((output / 'manifest.json').read_text())['checker_workers'] == 2
    assert len(list(csv.DictReader((output / 'runs.csv').open()))) == 2
