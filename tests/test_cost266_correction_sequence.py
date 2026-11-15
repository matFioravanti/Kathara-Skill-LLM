import csv
from pathlib import Path
from types import SimpleNamespace

from openpyxl import load_workbook

from benchmark_core.cost266 import runner
from benchmark_core.cost266.protocol import digest
from benchmark_core.workspace import tree_hash


def test_numbered_corrections_are_combined_in_order(tmp_path, monkeypatch):
    run = tmp_path / 'run'
    for directory in ('lab', 'input/lab', 'evaluation', 'results'):
        (run / directory).mkdir(parents=True)
    (run / 'lab' / 'lab.conf').write_text('test')
    (run / 'input/lab/lab.conf').write_text('test')
    names = ['correction_1.yaml', 'correction_2.yaml', 'correction_3.yaml']
    for name in names:
        (run / 'evaluation' / name).write_text(name)
    metadata = {'conditions': {'correction_files': {name: digest(name.encode()) for name in reversed(names)}},
                'input_lab_sha256': tree_hash(run / 'input/lab')}
    seen = []
    def fake_checker(config, checker_run, oracle, *, isolated=False):
        assert isolated is True
        seen.append(oracle.name)
        results = checker_run / 'results'
        (results / 'lab').mkdir()
        passed = oracle.name != names[1]
        def save(path, fields, rows):
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        detail = {'Test Description': oracle.name, 'Passed': str(passed), 'Reason': ''}
        fields = ['Test Description', 'Passed', 'Reason']
        save(results / 'lab/lab_result_all.csv', fields, [detail])
        save(results / 'lab/lab_result_failed.csv', fields, [] if passed else [detail])
        save(results / 'lab/lab_result_summary.csv', ['Total Tests','Passed Tests','Failed'],
             [{'Total Tests': 1, 'Passed Tests': int(passed), 'Failed': int(not passed)}])
        save(results / 'results.csv', ['Student Name','Tests Passed','Tests Failed','Tests Total Number','Problems'],
             [{'Student Name':'lab','Tests Passed':int(passed),'Tests Failed':int(not passed),'Tests Total Number':1,'Problems':''}])
        return {'checks_passed':int(passed),'checks_failed':int(not passed),'checks_total':1,'check_pass_rate':float(passed),'task_success':passed}
    monkeypatch.setattr(runner, 'run_checker', fake_checker)
    config = SimpleNamespace(root=tmp_path, data={'benchmark': {}})
    messages = []
    outcome = runner._evaluate_sequence(config, SimpleNamespace(checker_timeout=30), run, metadata, 30, isolated=True, emit=messages.append)
    assert seen == names
    assert len(messages) == 3
    assert all(f'Correction {index}/3 completata: {name}' in message for index, (name, message) in enumerate(zip(names, messages), 1))
    assert 'controlli superati=0/1, falliti=1' in messages[1]
    assert (outcome['checks_passed'], outcome['checks_total'], outcome['task_success']) == (2, 3, False)
    runner._write_run_workbook(run, metadata, {'timing': {'total_seconds': 2}})
    book = load_workbook(run / 'evaluation/benchmark.xlsx', read_only=True)
    assert book.sheetnames == ['General', 'Summary', 'Checks']
    assert list(book['Summary'].values)[-1][:4] == ('Totale', 2, 1, 3)
    assert [row[0] for row in list(book['Checks'].values)[1:]] == names
