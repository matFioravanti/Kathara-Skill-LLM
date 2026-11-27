import csv
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

from benchmark_core.classified_dns_catalog import CorrectionCatalog

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_classified_dns_benchmark', ROOT / 'scripts/build_classified_dns_benchmark.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CORRECTION = b'''# --- CS01 -- Device ---
# --- CS02 -- Topology ---
lab_inline: |
  pc1[0]="A"
test:
  applications:
    dns:
      local_ns:
        10.0.0.1: [pc1]
      records:
        # --- CS10 -- A records ---
        A:
          example.com: [10.0.0.1]
        # --- CS11 -- MX records ---
        MX:
          example.com: ['10 mail.example.com.']
'''


def test_no_position_based_dns_success_classification():
    catalog = CorrectionCatalog(CORRECTION)
    result, why = catalog.match('Checking correctness of DNS records', 'OK')
    assert result is None and 'IDENTIFIERS_ABSENT' in why
    match, why = catalog.match('Checking correctness of DNS records', "pc1 resolve A example.com with IP bad instead of ['10.0.0.1']")
    assert match['error_code'] == 'CS10' and match['device'] == 'pc1'
    assert catalog.match('Checking correctness of DNS records', "pc1 resolve A other.com with IP bad instead of ['10.0.0.1']")[0] is None


def test_synthetic_missing_checks_are_not_model_failures(tmp_path):
    correction = tmp_path / 'correction.yaml'
    correction.write_bytes(CORRECTION)
    b = module.Builder(tmp_path, sqlite3.connect(':memory:'))
    b.run_rows['run'] = dict(execution_id='run', lab_id='lab_01', task_level='small', prompt_id='T1',
                             skill_mode='no_skill', repetition=1, run_id='one')
    manifest = dict(status='CHECKER_FAILED', task_success=None, correction_sha256=hashlib.sha256(CORRECTION).hexdigest())
    e = b.make_eval('run', manifest, correction, tmp_path / 'results', 'V3', True, source=correction)
    b.process_evaluation(e)
    rows = [json.loads(x[0]) for x in b.db.execute('SELECT data FROM checks')]
    assert rows and all(r['check_status'] == 'NOT_EXECUTED' and r['error_present'] is None for r in rows)
    assert all(r['error_present'] is None for r in b.epr)
    assert b.stats['imported_controls'] == 0


def test_xlsx_split_retains_literal_text_and_rows(tmp_path):
    sink = module.ExcelSink(max_rows=3)
    sink.sheet('Checks_All', ['execution_id', 'passed', 'text'],
               [dict(execution_id=str(i), passed=i % 2 == 0, text='=NOT_A_FORMULA') for i in range(5)], split=True)
    path = tmp_path / 'test.xlsx'
    sink.finish(path)
    counts = module.verify_xlsx(path, sink.counts)
    assert counts == {'Checks_All_01': 2, 'Checks_All_02': 2, 'Checks_All_03': 1}


def test_native_codes_and_totals_agree_with_canonical_corrections():
    for lab, level, count in [('lab_01', 'small', 652), ('lab_02', 'medium', 2135), ('lab_03', 'large', 4883)]:
        cat = CorrectionCatalog((ROOT / 'scenarios' / lab / 'tasks/base' / level / 'correction.yaml').read_bytes())
        assert len(cat.definitions) == count
        assert {d['error_code'] for d in cat.definitions} == {f'CS{i:02d}' for i in range(1, 12)}


def test_missing_csv_does_not_become_success_even_if_manifest_says_completed(tmp_path):
    correction = tmp_path / 'correction.yaml'
    correction.write_bytes(CORRECTION)
    b = module.Builder(tmp_path, sqlite3.connect(':memory:'))
    b.run_rows['run'] = dict(execution_id='run', task_level='small', prompt_id='T1', skill_mode='auto')
    e = b.make_eval('run', dict(status='COMPLETED', task_success=True), correction, tmp_path / 'absent', 'V3', True, source=correction)
    b.process_evaluation(e)
    assert not e['report_consistent'] and e['csv_success'] is None


def test_run_frequency_is_not_control_failure_rate(tmp_path):
    b = module.Builder(tmp_path, sqlite3.connect(':memory:'))
    shared = dict(task_level='small', prompt_id='T1', skill_mode='auto', correction_version='V3',
                  error_code='DNS_AUTH_A_RECORD', analysis_included=True)
    b.epr = [shared | dict(error_present=1, executed_checks=10, passed_checks=9, failed_checks=1),
             shared | dict(error_present=0, executed_checks=10, passed_checks=10, failed_checks=0),
             shared | dict(error_present=None, executed_checks=0, passed_checks=0, failed_checks=0)]
    group = b.grouped_errors()[0]
    assert group['error_frequency_percentage'] == 50
    assert group['failure_percentage'] == 5
    assert group['unknown_runs'] == 1
