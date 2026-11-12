"""Cross-experiment reporting exercises real run verification with fake AUTs."""
from pathlib import Path
import hashlib
import json
import time

import pandas as pd
import pytest
from openpyxl import load_workbook

from test_cost266_selection import selection as base_selection, arguments
from test_cost266_continuous import v2
from test_cost266 import case
from scripts import run_cost266 as cli
from benchmark_core.cost266_comparative_report import compare
from benchmark_core.cost266.comparison import comparison_mismatches


@pytest.fixture
def selection(base_selection,monkeypatch):
    from benchmark_core.cost266 import runner
    from benchmark_core.workspace import write_json
    original=runner.run_aut
    def with_version(*args,**kwargs):
        original(*args,**kwargs)
        path=args[2]/'logs/aut/sandbox_metadata.json'
        metadata=json.loads(path.read_text());metadata['codex_sandbox_version']='fixture'
        write_json(path,metadata)
    monkeypatch.setattr(runner,'run_aut',with_version)
    return base_selection


def snapshot(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def runs(fixture,modes):
    for mode in modes:assert cli.main(arguments(mode))==0


def test_all_modes_cross_experiment_reports_and_determinism(selection):
    runs(selection,['one_shot','incremental_isolated','incremental_continuous'])
    root=selection.root;before=snapshot(root/'runs');before_reports=snapshot(root/'results')
    first=root/'comparison1';second=root/'comparison2'
    manifest=compare(root,first,['test_isolated','test_continuous'])
    assert manifest['observations_read']==3 and manifest['valid_pairs']==3 and manifest['valid_triples']==1
    pairs=pd.read_csv(first/'pairwise_comparisons.csv')
    assert len(pairs)==3 and pairs.comparable.all()
    assert pairs.delta_input_tokens.isna().all()
    assert pairs.token_reason.str.contains('non verificati').all()
    assert pd.read_csv(first/'observations.csv').input_tokens.isna().all()
    triple=pd.read_csv(first/'three_modes_comparison.csv')
    assert len(triple)==1 and triple.comparable.iloc[0]
    assert triple.one_shot_status.iloc[0]=='complete'
    summary=pd.read_csv(first/'summary.csv')
    success=summary[(summary.group_by=='execution_mode') & (summary.execution_mode=='one_shot') & (summary.metric=='task_success')].iloc[0]
    assert success.observations_valid==1 and success['mean']==1.0
    assert summary[summary.group_by=='execution_mode+prompt_type'].execution_mode.notna().all()
    book=load_workbook(first/'benchmark_comparison.xlsx',read_only=True)
    assert book.sheetnames==['Observations','Pairwise','Three Modes','Summary','Diagnostics'];book.close()
    time.sleep(1.1)
    compare(root,second,['test_isolated','test_continuous'])
    assert snapshot(first)==snapshot(second)
    assert snapshot(root/'runs')==before
    assert snapshot(root/'results')==before_reports


def test_missing_mode_and_failed_checker_are_visible(selection,monkeypatch):
    runs(selection,['one_shot'])
    from benchmark_core.cost266 import runner
    monkeypatch.setattr(runner,'run_checker',lambda *args:(_ for _ in ()).throw(RuntimeError('checker unavailable')))
    assert cli.main(arguments('incremental_isolated'))==1
    output=selection.root/'comparison'
    compare(selection.root,output)
    rows=pd.read_csv(output/'observations.csv')
    assert set(rows.status)=={'complete','checker_unavailable'}
    pairs=pd.read_csv(output/'pairwise_comparisons.csv')
    assert not pairs.comparable.any() and pairs.delta_final_pass_rate.isna().all()
    assert 'missing' in set(pd.read_csv(output/'three_modes_comparison.csv')['incremental_continuous_status'])
    summary=pd.read_csv(output/'summary.csv')
    row=summary[(summary.group_by=='execution_mode') & (summary.execution_mode=='one_shot') & (summary.metric=='final_pass_rate')].iloc[0]
    assert row.observations_valid==1


def test_different_model_and_integrity_failure_refuse_comparison(selection):
    runs(selection,['one_shot'])
    selection.config.data['aut']['model']='different'
    runs(selection,['incremental_isolated'])
    output=selection.root/'comparison'
    compare(selection.root,output)
    pairs=pd.read_csv(output/'pairwise_comparisons.csv')
    row=pairs.iloc[0]
    assert not row.comparable and 'model' in row.reason and pd.isna(row.delta_final_pass_rate)
    manifest=next((selection.root/'runs'/'test_isolated').rglob('manifest.json'))
    data=json.loads(manifest.read_text());data['conditions']['model']='tampered';manifest.write_text(json.dumps(data))
    output=selection.root/'comparison2';compare(selection.root,output)
    rows=pd.read_csv(output/'observations.csv')
    assert 'integrity_error' in set(rows.status)


@pytest.mark.parametrize('field',['baseline_sha256','correction_sha256','inventory_sha256','model','reasoning_effort','skill_mode','skill_protocol','skill_bundles','budgets'])
def test_condition_differences_do_not_match(selection,field):
    runs(selection,['one_shot','incremental_isolated'])
    paths=list((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    a,b=[json.loads(p.read_text()) for p in paths]
    b['conditions'][field]='different'
    assert field in ' '.join(comparison_mismatches(a,b))


def test_unverifiable_requirements_and_output_safety(selection):
    runs(selection,['one_shot','incremental_isolated'])
    paths=list((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    a,b=[json.loads(p.read_text()) for p in paths]
    a.pop('requirements_sha256');b.pop('requirements_sha256')
    b['conditions']['implementation_sha256']='different'
    assert 'requisiti DNS storici non verificabili' in comparison_mismatches(a,b)
    with pytest.raises(ValueError):compare(selection.root,selection.root/'runs/new')
    with pytest.raises(ValueError):compare(selection.root,selection.root/'comparison',['absent'])


def test_duplicate_and_legacy_one_shot_are_explicit(selection):
    import yaml
    runs(selection,['one_shot','incremental_isolated','incremental_continuous'])
    legacy=selection.root/'experiments/cost266_v1.yaml'
    assert cli.main([str(legacy),*arguments('one_shot')])==0
    data=yaml.safe_load(legacy.read_text());data['experiment']['id']='second_isolated'
    legacy.write_text(yaml.safe_dump(data))
    assert cli.main(arguments('incremental_isolated'))==0
    output=selection.root/'comparison';compare(selection.root,output)
    rows=pd.read_csv(output/'observations.csv')
    assert rows.legacy_one_shot.sum()==1
    triple=pd.read_csv(output/'three_modes_comparison.csv').iloc[0]
    assert triple.incremental_isolated_status=='duplicate' and not triple.comparable
    pairs=pd.read_csv(output/'pairwise_comparisons.csv')
    assert sum(pairs.reason.fillna('').str.contains('duplicate'))==2


def test_empty_source_exports_headers(selection):
    output=selection.root/'comparison';result=compare(selection.root,output)
    assert result['observations_read']==0
    assert 'mode_a' in pd.read_csv(output/'pairwise_comparisons.csv').columns
    assert 'comparable' in pd.read_csv(output/'three_modes_comparison.csv').columns


from test_token_accounting import cumulative_v2


def test_verified_token_deltas_use_normalized_metrics(cumulative_v2,monkeypatch):
    from test_cost266 import fake_aut
    from test_cost266_continuous import run
    from benchmark_core.cost266 import runner
    from benchmark_core.cost266.protocol import Cell
    from benchmark_core.token_usage import normalize_standalone, save
    fixture=cumulative_v2
    run(fixture)
    original=fake_aut(fixture)
    def single(*args,**kwargs):
        original(*args,**kwargs)
        logs=args[2]/'logs/aut';events=logs/'events.jsonl'
        events.write_text(json.dumps({'type':'thread.started','thread_id':'single-thread'})+'\n'+events.read_text())
        metadata=json.loads((logs/'sandbox_metadata.json').read_text());metadata['codex_sandbox_version']='0.165.0'
        save(logs/'sandbox_metadata.json',metadata)
        save(logs/'invocation.json',{'command':['codex','exec'],'codex_sandbox_version':'0.165.0'})
        normalize_standalone(logs,'0.165.0')
    monkeypatch.setattr(runner,'run_aut',single)
    runner.execute(fixture.config,fixture.spec,Cell(fixture.spec.experiment_id,'T1','one_shot','no_skill',1),fixture.inventory,fixture.preparation)
    output=fixture.root/'comparison';compare(fixture.root,output)
    pairs=pd.read_csv(output/'pairwise_comparisons.csv')
    row=pairs[(pairs.mode_a=='one_shot') & (pairs.mode_b=='incremental_continuous')].iloc[0]
    assert row.comparable and row.delta_input_tokens==200 and row.delta_output_tokens==16


def test_missing_controls_on_both_sides_do_not_become_comparable(selection):
    from benchmark_core.cost266_comparative_report import _pair, _condition_key, KEYS
    runs(selection,['one_shot','incremental_isolated'])
    paths=list((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    a,b=[json.loads(p.read_text()) for p in paths]
    a['conditions']['budgets']=None;b['conditions']['budgets']=None
    row={'integrity_verified':True,'status':'complete','usage_verified':False}
    pair=_pair({'meta':a,'row':row},{'meta':b,'row':row},('one_shot','incremental_isolated'),tuple(a.get(k) for k in KEYS))
    assert not pair['comparable'] and 'budgets non verificabile' in pair['reason']
    a['conditions']['budgets']=[None,None,None];b['conditions']['budgets']=[None,None,None]
    pair=_pair({'meta':a,'row':row},{'meta':b,'row':row},('one_shot','incremental_isolated'),tuple(a.get(k) for k in KEYS))
    assert not pair['comparable'] and 'budgets non verificabile' in pair['reason']
    a['conditions']['budgets']=[100,1000,100];b['conditions']['budgets']=[100,1000,100]
    b['conditions']['implementation_sha256']='f'*64
    pair=_pair({'meta':a,'row':row},{'meta':b,'row':row},('one_shot','incremental_isolated'),tuple(a.get(k) for k in KEYS))
    assert not pair['comparable'] and 'implementation_sha256' in pair['reason']
    changed={**a,'execution_backend':'host'}
    assert _condition_key(a,'fixture')!=_condition_key(changed,'fixture')


def test_incomplete_run_and_changed_checker_metrics_remain_visible(selection):
    from test_cost266_continuous import ScriptedSession
    runs(selection,['one_shot'])
    ScriptedSession.fault='failure'
    assert cli.main(arguments('incremental_continuous'))==1
    metric=next((selection.root/'runs').glob('*/*/*/cost266/*/one_shot/*/r*/evaluation/metrics.json'))
    data=json.loads(metric.read_text());data['checker']['pass_rate']=0.3;metric.write_text(json.dumps(data))
    output=selection.root/'comparison';compare(selection.root,output)
    observations=pd.read_csv(output/'observations.csv')
    assert set(observations.status)=={'incomplete','integrity_error'}
    assert not pd.read_csv(output/'pairwise_comparisons.csv').comparable.any()


def test_corrupt_manifest_is_reported_instead_of_disappearing(selection):
    runs(selection,['one_shot'])
    manifest=next((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    data=json.loads(manifest.read_text());data['schema']='corrupt';manifest.write_text(json.dumps(data))
    output=selection.root/'comparison';result=compare(selection.root,output,['test_continuous'])
    rows=pd.read_csv(output/'observations.csv')
    assert result['observations_read']==1 and rows.status.iloc[0]=='integrity_error'


def test_metadata_model_conflict_is_integrity_error(selection):
    runs(selection,['one_shot'])
    manifest=next((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    data=json.loads(manifest.read_text());data['model']='different';manifest.write_text(json.dumps(data))
    output=selection.root/'comparison';compare(selection.root,output)
    rows=pd.read_csv(output/'observations.csv')
    assert rows.status.iloc[0]=='integrity_error' and 'model' in rows.integrity_error.iloc[0]


def test_historical_missing_descriptive_protocol_is_inferred(selection):
    runs(selection,['one_shot'])
    manifest=next((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    data=json.loads(manifest.read_text());data['protocol_version']=None;manifest.write_text(json.dumps(data))
    output=selection.root/'comparison';compare(selection.root,output)
    row=pd.read_csv(output/'observations.csv').iloc[0]
    assert row.status=='complete' and row.execution_mode=='one_shot'


def test_historical_repetition_field_is_accepted(selection):
    runs(selection,['one_shot'])
    manifest=next((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    data=json.loads(manifest.read_text());data.pop('replicate');manifest.write_text(json.dumps(data))
    output=selection.root/'comparison';compare(selection.root,output)
    row=pd.read_csv(output/'observations.csv').iloc[0]
    assert row.status=='complete' and row.replicate==1


@pytest.mark.parametrize('observed,reason',[('other-version','agent_runtime_version'),(None,'versione runtime agente non verificabile')])
def test_agent_runtime_version_must_be_verified_and_equal(selection,monkeypatch,observed,reason):
    from benchmark_core.cost266 import runner
    from benchmark_core.workspace import write_json
    original=runner.run_aut
    def alter_version(*args,**kwargs):
        original(*args,**kwargs)
        path=args[2]/'logs/aut/sandbox_metadata.json'
        metadata=json.loads(path.read_text());metadata['codex_sandbox_version']=observed
        write_json(path,metadata)
    monkeypatch.setattr(runner,'run_aut',alter_version)
    runs(selection,['one_shot','incremental_continuous'])
    output=selection.root/'comparison';compare(selection.root,output)
    pairs=pd.read_csv(output/'pairwise_comparisons.csv')
    row=pairs[(pairs.mode_a=='one_shot') & (pairs.mode_b=='incremental_continuous')].iloc[0]
    assert not row.comparable and reason in row.reason
