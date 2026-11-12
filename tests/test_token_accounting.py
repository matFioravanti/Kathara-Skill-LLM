"""Cumulative provider counters: no containers or paid model calls."""
from copy import deepcopy
from pathlib import Path
import hashlib,json

import pytest

from benchmark_core.token_usage import (UsageLedger,FIELDS,semantics_for,record_turn,
    aggregate_accounting,sum_counters,save,load_accounting,normalize_session)
from benchmark_core.run_metrics import codex_usage


def consume(ledger,raw,thread='thread',new=False,expected=None):
    return ledger.consume(raw,thread_id=thread,new_thread=new,
                          expected_thread=expected,semantics='cumulative_thread')


def test_real_two_turn_example():
    ledger=UsageLedger()
    a=consume(ledger,{'input_tokens':11363,'output_tokens':5,'cached_input_tokens':9088},new=True)
    b=consume(ledger,{'input_tokens':22751,'output_tokens':10,'cached_input_tokens':20224},expected='thread')
    assert a['usage_delta']['input_tokens']==11363 and b['usage_delta']['input_tokens']==11388
    assert b['usage_delta']['output_tokens']==5 and b['usage_delta']['cached_input_tokens']==11136
    assert aggregate_accounting([a,b])['usage_delta']['input_tokens']==22751
    assert aggregate_accounting([a,b])['usage_delta']['output_tokens']==10
    assert b['usage_raw']['input_tokens']==22751 and b['usage_verified']


def test_six_turns_all_fields_and_reported_total_are_independent():
    ledger=UsageLedger();items=[]
    for index in range(1,7):
        raw={'input_tokens':100*index,'output_tokens':10*index,'cached_input_tokens':40*index,
             'reasoning_output_tokens':2*index,'cache_write_input_tokens':3*index,'total_tokens':111*index}
        items.append(consume(ledger,raw,new=index==1,expected=None if index==1 else 'thread'))
    combined=aggregate_accounting(items)
    assert combined['usage_delta']==raw and combined['usage_verified']
    tokens=codex_usage([{'type':'turn.completed','usage':combined['usage_delta']}])
    assert tokens['total_reported']==666 and tokens['total_calculated']==660
    assert tokens['total']==666 and tokens['reasoning']==12 and tokens['cached_input']==240


def test_six_independent_threads_and_per_turn_backend():
    ledger=UsageLedger()
    items=[consume(ledger,{'input_tokens':7,'output_tokens':2},thread=f't{i}',new=True) for i in range(6)]
    assert aggregate_accounting(items)['usage_delta']['input_tokens']==42
    a=ledger.consume({'input_tokens':7,'output_tokens':2},semantics='per_turn')
    b=ledger.consume({'input_tokens':7,'output_tokens':2},semantics='per_turn')
    assert a['usage_delta']==b['usage_delta'] and b['usage_verified']


@pytest.mark.parametrize('bad',[None,-1,True,'3',1.5])
def test_invalid_values_never_become_zero_or_negative(bad):
    ledger=UsageLedger()
    item=consume(ledger,{'input_tokens':bad,'output_tokens':1},new=True)
    assert item['usage_delta']['input_tokens'] is None and not item['usage_verified']
    later=consume(ledger,{'input_tokens':20,'output_tokens':2},expected='thread')
    assert later['usage_delta']['input_tokens'] is None
    assert aggregate_accounting([item,later])['usage_delta']['input_tokens'] is None


def test_missing_turn_regression_and_incomplete_history():
    ledger=UsageLedger()
    a=consume(ledger,{'input_tokens':100,'output_tokens':3},new=True)
    gap=consume(ledger,None,expected='thread')
    b=consume(ledger,{'input_tokens':300,'output_tokens':8},expected='thread')
    c=consume(ledger,{'input_tokens':400,'output_tokens':10},expected='thread')
    assert gap['usage_delta']['input_tokens'] is None and b['usage_delta']['input_tokens'] is None
    assert c['usage_delta']['input_tokens']==100
    assert aggregate_accounting([a,gap,b,c])['usage_delta']['input_tokens'] is None
    reset=consume(ledger,{'input_tokens':5,'output_tokens':1},expected='thread')
    after=consume(ledger,{'input_tokens':600,'output_tokens':20},expected='thread')
    assert reset['usage_delta']['input_tokens'] is None and after['usage_delta']['input_tokens'] is None
    unknown=consume(UsageLedger(),{'input_tokens':100,'output_tokens':5},expected='thread')
    assert unknown['history_complete'] is False and not unknown['usage_verified']


def test_thread_replacement_is_not_reset_to_zero():
    ledger=UsageLedger();consume(ledger,{'input_tokens':100,'output_tokens':5},new=True)
    item=consume(ledger,{'input_tokens':20,'output_tokens':2},thread='replacement',expected='thread')
    assert not item['usage_verified'] and item['usage_delta']['input_tokens'] is None
    assert 'thread_continuity_lost' in item['usage_diagnostics'].values()


@pytest.mark.parametrize('backend,version',[('host','0.165.0'),('docker_sandbox','0.166.0'),
    ('docker_sandbox','0.165.0-beta'),('docker_sandbox',None)])
def test_only_verified_backend_version_uses_deltas(backend,version):
    assert semantics_for('codex',backend,version)=='unknown'


def write_turn(directory,raw,expected=None,thread='thread',failed=False):
    directory.mkdir(parents=True)
    events=[{'type':'thread.started','thread_id':thread},
            {'type':'turn.failed' if failed else 'turn.completed','usage':raw}]
    (directory/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    save(directory/'result.json',{'usage':raw,'returncode':1 if failed else 0,'timed_out':failed,
                                  'session_id':thread,'duration_seconds':2})
    save(directory/'invocation.json',{'session_expected':expected,'codex_sandbox_version':'0.165.0'})


def test_failed_observed_usage_preserved_and_source_tampering_detected(tmp_path):
    from types import SimpleNamespace
    paths=[tmp_path/'a',tmp_path/'b']
    write_turn(paths[0],{'input_tokens':10,'output_tokens':2})
    write_turn(paths[1],{'input_tokens':14,'output_tokens':3},expected='thread',failed=True)
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for folder in paths for p in folder.iterdir()}
    session=SimpleNamespace(version='codex-cli 0.165.0',turns=[(p,{}) for p in paths])
    normalize_session(session)
    first=(paths[0]/'usage_accounting.json').read_bytes()
    normalize_session(session)
    assert first==(paths[0]/'usage_accounting.json').read_bytes()
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in before.items())
    b=load_accounting(paths[1]);assert b['usage_delta']['input_tokens']==4
    assert b['outcome']=='failed_or_partial' and b['usage_verified']
    with (paths[0]/'events.jsonl').open('a') as f:f.write('{}\n')
    assert not load_accounting(paths[1])['usage_verified']
    assert load_accounting(paths[1])['usage_delta']['input_tokens'] is None


def test_unregistered_runtime_and_failed_event_only_usage_remain_explicit(tmp_path):
    from types import SimpleNamespace
    path=tmp_path/'unknown'
    write_turn(path,{'input_tokens':14,'output_tokens':3})
    invocation=json.loads((path/'invocation.json').read_text())
    invocation['codex_sandbox_version']='0.166.0';save(path/'invocation.json',invocation)
    normalize_session(SimpleNamespace(version='codex-cli 0.166.0',turns=[(path,{})]))
    item=load_accounting(path)
    assert item['usage_delta']['input_tokens'] is None and not item['usage_verified']
    path=tmp_path/'partial'
    write_turn(path,{'input_tokens':14,'output_tokens':3},failed=True)
    result=json.loads((path/'result.json').read_text());result['usage']=None;save(path/'result.json',result)
    normalize_session(SimpleNamespace(version='codex-cli 0.165.0',turns=[(path,{})]))
    item=load_accounting(path)
    assert item['usage_delta']['input_tokens']==14 and item['usage_verified']


@pytest.fixture
def cumulative_v2(v2,monkeypatch):
    original=ScriptedSession.turn
    def cumulative(self,**kwargs):
        self.version='codex-cli 0.165.0'
        events,result=original(self,**kwargs)
        increment=result['usage']
        counts=getattr(self,'cumulative_counts',{})
        for key,value in increment.items():counts[key]=counts.get(key,0)+value
        self.cumulative_counts=counts
        result['usage']=deepcopy(counts)
        for event in events:
            if event.get('type')=='turn.completed':event['usage']=deepcopy(counts)
        directory=kwargs['directory']
        (directory/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        save(directory/'result.json',result)
        invocation=json.loads((directory/'invocation.json').read_text())
        invocation['codex_sandbox_version']=self.version
        save(directory/'invocation.json',invocation)
        return events,result
    monkeypatch.setattr(ScriptedSession,'turn',cumulative)
    return v2


from test_cost266 import case
from test_cost266_continuous import v2, ScriptedSession, run, forced


def test_cumulative_continuous_runner_csv_excel_inspect_and_resume(cumulative_v2,monkeypatch):
    from benchmark_core.cost266.reports import aggregate_cost266
    from benchmark_core.cost266.runner import verify_run
    from inspect_ai.log import read_eval_log
    import pandas as pd
    fixture=cumulative_v2
    path=run(fixture)
    metadata=json.loads((path/'manifest.json').read_text())
    verify_run(path,metadata['conditions'])
    metrics=json.loads((path/'evaluation/metrics.json').read_text())
    assert metrics['usage_verified'] and metrics['tokens']['input']==210 and metrics['tokens']['output']==21
    assert metrics['tokens']['reasoning']==6 and metrics['tokens']['cached_input']==21
    assert metrics['sandbox_count']==1 and metrics['functional_turns']==6
    part=path/'steps/02/attempts/001/logs/aut'
    assert json.loads((part/'result.json').read_text())['usage']['input_tokens']==30
    assert load_accounting(part)['usage_delta']['input_tokens']==20
    log=read_eval_log(str(next(part.glob('*.eval'))))
    assert next(iter(log.stats.model_usage.values())).input_tokens==20
    aggregate_cost266(fixture.root,fixture.root/'results/test_cost266')
    rows=pd.read_csv(fixture.root/'results/test_cost266/stages.csv')
    assert list(rows['input_tokens'])==[10,20,30,40,50,60]
    assert rows['usage_verified'].all()
    from openpyxl import load_workbook
    book=load_workbook(fixture.root/'results/test_cost266/benchmark.xlsx',read_only=True)
    header=[cell.value for cell in next(book['Runs'].iter_rows())]
    assert 'usage_verified' in header;book.close()
    run(fixture,resume=True);run(fixture,rerun=True)
    assert len(ScriptedSession.instances)==1 and len(ScriptedSession.instances[0].received)==6
    assert json.loads((path/'evaluation/metrics.json').read_text())['tokens']['input']==210


@pytest.mark.parametrize('schedule,gate_count',[([['kathara-dns']],1),([[],['kathara-dns']],2),([[],[],[]],4)])
def test_cumulative_gate_sequence_is_normalized_before_categories(cumulative_v2,schedule,gate_count):
    fixture=cumulative_v2;forced(fixture)
    ScriptedSession.read_schedule=schedule
    path=run(fixture,'dns_only')
    metrics=json.loads((path/'evaluation/metrics.json').read_text())
    gate=json.loads((path/'logs/aut/skill_gate.json').read_text())
    assert metrics['usage_verified'] and metrics['gate_turns']==gate_count
    assert metrics['tokens']['input']==210+11*gate_count
    assert metrics['tokens']['output']==21+3*gate_count
    assert metrics['gate_input_tokens']==11*gate_count and metrics['functional_input_tokens']==210
    assert gate['skill_gate_input_tokens']==11*gate_count and gate['write_phase_input_tokens']==210
    assert metrics['tokens']['input']==ScriptedSession.instances[0].cumulative_counts['input_tokens']
    assert metrics['timing']['agent_seconds']==2*(6+gate_count)
    assert metrics['sandbox_count']==2 and metrics['writable_sandbox_count']==1


def test_cumulative_one_shot_gate_ordinary_path(cumulative_v2,monkeypatch):
    from benchmark_core import inspect_runner
    from benchmark_core.cost266 import runner
    from benchmark_core.cost266.protocol import Cell
    fixture=cumulative_v2;forced(fixture)
    monkeypatch.setattr('benchmark_core.docker_sandbox_runner.ProtectedCodexSession',ScriptedSession)
    monkeypatch.setattr(runner,'run_aut',inspect_runner.run_aut)
    cell=Cell(fixture.spec.experiment_id,'T1','one_shot','dns_only',1)
    path=runner.execute(fixture.config,fixture.spec,cell,fixture.inventory,fixture.preparation)
    metrics=json.loads((path/'evaluation/metrics.json').read_text())
    assert metrics['usage_verified'] and metrics['tokens']['input']==21
    assert metrics['tokens']['output']==4 and metrics['gate_input_tokens']==11
    assert metrics['functional_input_tokens']==10
