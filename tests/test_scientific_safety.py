"""Scientific integrity and publication checks; all files live in tmp_path."""
import json
import csv
import hashlib
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import pandas as pd
import openpyxl

from benchmark_core.aggregation import aggregate, _write_excel
from benchmark_core.experiment import analyse_existing_runs, load_experiment
from benchmark_core.fingerprint import compare, fingerprint
from benchmark_core.check_classification import classify_rows, _expected_records
from benchmark_core.workspace import write_json


def observation(root, directory, replicate=1, model='a', status='COMPLETED'):
    run = root / 'exp/lab_01/base/small/T1/no_skill' / directory
    (run / 'evaluation').mkdir(parents=True)
    manifest = {'run_id':directory, 'run_number':int(directory[1:]), 'experiment_id':'exp',
        'lab_id':'lab_01', 'scenario_id':'lab_01', 'dns_tree_id':'base', 'task_level':'small',
        'prompt_type':'T1', 'skill_mode':'no_skill', 'replicate':replicate, 'model':model,
        'pipeline_state':status, 'checker_execution_success':status == 'COMPLETED', 'task_success':True}
    metrics = {**manifest, 'status':status, 'scenario':'lab_01',
               'checker':{'passed':1,'failed':0,'total':1,'pass_rate':1.0}}
    correction=b'fixture correction\n'
    manifest['correction_sha256']=hashlib.sha256(correction).hexdigest()
    (run/'evaluation/correction.yaml').write_bytes(correction)
    (run/'lab').mkdir(); (run/'input/lab').mkdir(parents=True)
    write_json(run/'manifest.json',manifest); write_json(run/'evaluation/metrics.json',metrics)
    reports = run/'results'; (reports/'lab').mkdir(parents=True)
    def write(path, header, rows):
        with path.open('w', newline='') as f:
            writer=csv.writer(f); writer.writerow(header); writer.writerows(rows)
    header=['Test Description','Passed','Reason']
    write(reports/'results.csv',['Student Name','Tests Passed','Tests Failed','Tests Total Number','Problems'],[['lab',1,0,1,'']])
    write(reports/'lab/lab_result_all.csv',header,[['synthetic','True','OK']])
    write(reports/'lab/lab_result_failed.csv',header,[])
    write(reports/'lab/lab_result_summary.csv',['Total Tests','Passed Tests','Failed'],[[1,1,0]])
    return run


def test_duplicate_physical_attempts_excluded_and_reported(tmp_path):
    root=tmp_path/'runs'
    observation(root,'r001',1,model='a'); observation(root,'r003',1,model='b')
    observation(root,'r004',2,model='a')
    rows, _, summary = aggregate(root,tmp_path/'out')
    assert len(rows)==3
    assert summary['evaluated_runs'].sum()==1
    report=json.loads((tmp_path/'out/duplicates.json').read_text())
    assert report['physical_attempts']==3 and report['excluded_completed_attempts']==2
    assert report['duplicates'][0]['conditions']=='conflitto'
    assert {Path(a['path']).name for a in report['duplicates'][0]['attempts']}=={'r001','r003'}


def test_failed_attempt_is_inventoried_but_not_counted_twice(tmp_path):
    root=tmp_path/'runs'
    observation(root,'r001',1,status='AUT_FAILED')
    observation(root,'r002',1,status='COMPLETED')
    rows, _, summary = aggregate(root,tmp_path/'out')
    assert len(rows)==2 and summary.iloc[0]['logical_observations']==1
    assert summary.iloc[0]['physical_attempts']==2
    report=json.loads((tmp_path/'out/duplicates.json').read_text())
    assert report['exclusions'][0]['reason']=='superseded_failed_attempt'


def test_atomic_generation_preserves_previous_on_failure(tmp_path):
    root=tmp_path/'runs'; observation(root,'r001')
    out=tmp_path/'out'; aggregate(root,out)
    old_target=(out/'current').readlink(); old=(out/'runs.csv').read_bytes()
    observation(root,'r002',2)
    with patch('benchmark_core.aggregation._write_excel',side_effect=RuntimeError('simulated failure')):
        with pytest.raises(RuntimeError,match='simulated failure'): aggregate(root,out)
    assert (out/'current').readlink()==old_target and (out/'runs.csv').read_bytes()==old
    assert json.loads((out/'report_manifest.json').read_text())['generation_id']==old_target.name


def test_experiment_reports_are_isolated_and_updated(tmp_path):
    root = tmp_path / 'runs'
    first = observation(root, 'r001')
    other = root / 'other' / first.relative_to(root / 'exp')
    shutil.copytree(first, other)
    manifest = json.loads((other / 'manifest.json').read_text())
    manifest['experiment_id'] = 'other'
    write_json(other / 'manifest.json', manifest)
    metrics = json.loads((other / 'evaluation/metrics.json').read_text())
    metrics['experiment_id'] = 'other'
    write_json(other / 'evaluation/metrics.json', metrics)
    out = tmp_path / 'results' / 'exp'
    rows, _, _ = aggregate(root, out, experiment_id='exp')
    assert list(rows['experiment_id']) == ['exp']
    observation(root, 'r002', replicate=2)
    rows, _, _ = aggregate(root, out, experiment_id='exp')
    assert len(rows) == 2 and set(rows['experiment_id']) == {'exp'}
    other_rows, _, _ = aggregate(root, tmp_path / 'results/other', experiment_id='other')
    assert list(other_rows['experiment_id']) == ['other']


def test_large_workbook_streaming_preserves_classified_checks(tmp_path):
    checks = pd.DataFrame({'primary_category': ['dns'] * 25001,
                           'subcategory': ['dns_record'] * 25001,
                           'record_type': ['MX'] * 25001,
                           'classification_source': ['custom_command'] * 25001,
                           'passed': [False] * 25001,
                           **{f'extra_{n}': [n] * 25001 for n in range(6)}})
    output = tmp_path / 'large.xlsx'
    _write_excel(output, (pd.DataFrame({'ID': ['r1']}), checks, pd.DataFrame({'total': [1]})))
    book = openpyxl.load_workbook(output, read_only=True)
    rows = book['Checks'].iter_rows(values_only=True)
    assert next(rows)[:5] == ('primary_category', 'subcategory', 'record_type', 'classification_source', 'passed')
    assert next(rows)[:5] == ('dns', 'dns_record', 'MX', 'custom_command', False)
    book.close()


def test_existing_legacy_reports_are_not_overwritten(tmp_path):
    out=tmp_path/'out'; out.mkdir(); (out/'runs.csv').write_text('historical')
    (tmp_path/'runs').mkdir()
    with pytest.raises(ValueError,match='preesistente'):
        aggregate(tmp_path/'runs',out)
    assert (out/'runs.csv').read_text()=='historical'


def test_corrupt_json_or_missing_metrics_blocks_publication(tmp_path):
    root=tmp_path/'runs'; run=observation(root,'r001')
    (run/'evaluation/metrics.json').write_text('{')
    with pytest.raises(ValueError,match='metrics.json'): aggregate(root,tmp_path/'out')
    assert not (tmp_path/'out/current').exists()
    diagnostics = list((tmp_path/'out/.diagnostics').glob('*.json'))
    assert len(diagnostics)==1 and 'metrics.json' in json.loads(diagnostics[0].read_text())['message']
    (run/'evaluation/metrics.json').unlink()
    with pytest.raises(ValueError,match='senza metriche'): aggregate(root,tmp_path/'out')
    (run/'manifest.json').write_text('[]')
    with pytest.raises(ValueError,match='manifest.json'): aggregate(root,tmp_path/'out')
    (run/'manifest.json').unlink()
    with pytest.raises(ValueError,match='senza manifest'): aggregate(root,tmp_path/'out')


def test_fingerprint_changes_and_legacy_is_unverified():
    expected={'version':1,'agent':'codex','model':'a','reasoning_effort':'low',
              'prompt_sha256':'p','correction_sha256':'c','source_lab_sha256':'l',
              'skill_mode':'no_skill','aut':{'version':'1'},'skills':{},'timeout_seconds':900,
              'python_version':'3','component_versions':{'checker':'1'}}
    manifest={'experimental_conditions':expected,'experimental_fingerprint':fingerprint(expected)}
    assert compare(manifest,expected)==('compatible',[])
    changed={**expected,'model':'b'}
    assert compare(manifest,changed)[0]=='conflict'
    assert compare({'model':'a'},expected)[0]=='unverified'
    assert compare({'model':'b'},expected)[0]=='conflict'
    assert compare({**manifest,'experimental_fingerprint':'bad'},expected)[0]=='conflict'
    incomplete={**expected,'model':None}
    assert compare({'experimental_conditions':incomplete,'experimental_fingerprint':fingerprint(incomplete)},incomplete)[0]=='unverified'


def test_correction_cache_tracks_content_changes(tmp_path):
    correction=tmp_path/'correction.yaml'
    def text(kind):
        return f'test:\n  applications:\n    dns:\n      local_ns: {{"1.1.1.1": [pc1]}}\n      records:\n        {kind}: {{example.org: [1.2.3.4]}}\n'
    rows=[{'test_description':'Checking correctness of DNS records','passed':True,'reason':'OK'}]
    _expected_records.cache_clear()
    correction.write_text(text('A'))
    assert classify_rows(rows,correction,'0.1.14',True)[0][2]=='A'
    assert classify_rows(rows,correction,'0.1.14',True)[0][2]=='A'
    assert _expected_records.cache_info().hits==1
    correction.write_text(text('MX'))
    assert classify_rows(rows,correction,'0.1.14',True)[0][2]=='MX'
