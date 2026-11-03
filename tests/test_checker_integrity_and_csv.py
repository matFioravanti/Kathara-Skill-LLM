import csv
import json
from pathlib import Path

import pytest

from benchmark_core.checker_runner import parse_reports
from benchmark_core.workspace import check_lab_integrity, copy_lab, manifest, tree_hash


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)


def test_large_failure_report_and_validation(tmp_path):
    count = 4000
    rows = [[f'failure {i}', 'False', 'reason'] for i in range(count)]
    problems = ' '.join(f'{i}: ' + 'failure detail ' * 5 for i in range(count))
    assert len(problems) > 131072
    write_csv(tmp_path / 'results.csv', ['Student Name', 'Tests Passed', 'Tests Failed', 'Tests Total Number', 'Problems'],
              [['lab', 0, count, count, problems]])
    columns = ['Test Description', 'Passed', 'Reason']
    write_csv(tmp_path / 'lab/lab_result_all.csv', columns, rows)
    write_csv(tmp_path / 'lab/lab_result_failed.csv', columns, rows)
    write_csv(tmp_path / 'lab/lab_result_summary.csv', ['Total Tests', 'Passed Tests', 'Failed'], [[count, 0, count]])
    result, parsed = parse_reports(tmp_path)
    assert result['checks_failed'] == count and result['checker_problems'] == problems
    assert len(parsed) == count
    write_csv(tmp_path / 'lab/lab_result_failed.csv', columns, rows[:-1])
    with pytest.raises(ValueError, match='failed incoerente'):
        parse_reports(tmp_path)


def test_integrity_diagnostic_and_copy_isolation(tmp_path):
    run = tmp_path / 'run'
    lab = run / 'lab'
    lab.mkdir(parents=True)
    for name in ('modified', 'deleted', 'permissions'):
        (lab / name).write_text('original')
    before = manifest(lab)
    baseline = tree_hash(lab)
    copied = tmp_path / 'temporary/lab'
    copied.parent.mkdir()
    copy_lab(lab, copied)
    (copied / 'modified').write_text('checker')
    assert tree_hash(lab) == baseline
    check_lab_integrity(run, {'lab': before})
    (lab / 'modified').write_text('changed')
    (lab / 'deleted').unlink()
    (lab / 'added').write_text('new')
    (lab / 'permissions').chmod(0o600)
    with pytest.raises(RuntimeError, match='alterato'):
        check_lab_integrity(run, {'lab': before})
    changes = json.loads((run / 'logs/checker_integrity_diff.json').read_text())['lab']
    assert changes['added'] == ['added']
    assert changes['deleted'] == ['deleted']
    assert changes['modified'] == ['modified']
    assert changes['permissions']['permissions']['after'] == '0o600'
    assert changes['before_sha256'] == baseline
    assert changes['after_sha256'] == tree_hash(lab)
