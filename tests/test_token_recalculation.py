"""Explicit, offline token recalculation with immutable source artifacts."""
from pathlib import Path
import hashlib,json

import pandas as pd
import pytest

from test_token_accounting import write_turn,case,v2,cumulative_v2
from test_cost266_continuous import run,forced,ScriptedSession
from benchmark_core.token_usage import save
from benchmark_core.token_recalculation import recalculate
from scripts.recalculate_cost266_tokens import main


def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_two_turn_export_preserves_every_source_byte_and_previous_results(tmp_path):
    source=tmp_path/'source'
    write_turn(source/'logs/turn1',{'input_tokens':11363,'output_tokens':5,'cached_input_tokens':9088})
    write_turn(source/'logs/turn2',{'input_tokens':22751,'output_tokens':10,'cached_input_tokens':20224},expected='thread')
    save(source/'evaluation/metrics.json',{'tokens':{'input':34114},'timing':{'agent_seconds':7},'checker':{'passed':12}})
    before=hashes(source);output=tmp_path/'recalculated'
    report=recalculate(source,output)
    assert report['usage_verified'] and report['tokens']['input']==22751 and report['tokens']['output']==10
    assert hashes(source)==before
    assert (output/'previous_results/evaluation/metrics.json').read_bytes()==(source/'evaluation/metrics.json').read_bytes()
    metrics=json.loads((output/'recalculated_metrics.json').read_text())
    assert metrics['timing']['agent_seconds']==7 and metrics['checker']['passed']==12
    assert list(pd.read_csv(output/'turns.csv')['input_tokens'])==[11363,11388]
    from inspect_ai.log import read_eval_log
    log=read_eval_log(str(output/'normalized/logs/turn2/normalized.eval'))
    assert next(iter(log.stats.model_usage.values())).input_tokens==11388
    assert (output/'benchmark.xlsx').is_file()
    with pytest.raises(ValueError,match='Output must be new'):recalculate(source,output)
    with pytest.raises(ValueError):recalculate(source,source/'rewritten')


def test_missing_history_export_is_explicitly_unverified(tmp_path):
    source=tmp_path/'source'
    write_turn(source/'logs/turn2',{'input_tokens':22751,'output_tokens':10},expected='thread')
    assert main([str(source),'--output',str(tmp_path/'output')])==2
    report=json.loads((tmp_path/'output/recalculation_manifest.json').read_text())
    assert not report['usage_verified'] and report['tokens']['input'] is None
    from inspect_ai.log import read_eval_log
    log=read_eval_log(str(tmp_path/'output/normalized/logs/turn2/normalized.eval'))
    assert not log.stats.model_usage


def test_missing_intermediate_stage_does_not_attribute_gap_to_next_turn(tmp_path):
    source=tmp_path/'source'
    write_turn(source/'steps/01/attempts/001/logs/aut/turn',{'input_tokens':10,'output_tokens':1})
    write_turn(source/'steps/03/attempts/001/logs/aut/turn',{'input_tokens':60,'output_tokens':6},expected='thread')
    report=recalculate(source,tmp_path/'output')
    assert report['tokens']['input'] is None and not report['usage_verified']
    rows=pd.read_csv(tmp_path/'output/turns.csv')
    assert pd.isna(rows['input_tokens'].iloc[1])


def test_recalculate_cost266_gate_excludes_phase_b_alias_and_keeps_receipts(cumulative_v2,tmp_path):
    fixture=cumulative_v2;forced(fixture)
    ScriptedSession.read_schedule=[[],[],[]]
    source=run(fixture,'dns_only')
    before=hashes(source)
    report=recalculate(source,tmp_path/'export')
    assert report['cost266_receipts_verified'] and report['usage_verified']
    assert report['turn_count']==10 and report['tokens']['input']==254
    assert any('phase_b' in item['path'] for item in report['excluded_aliases'])
    assert hashes(source)==before
    metrics=json.loads((tmp_path/'export/recalculated_metrics.json').read_text())
    assert metrics['gate_input_tokens']==44 and metrics['functional_input_tokens']==210
    assert metrics['tokens']['output']==33
    from benchmark_core.cost266.runner import verify_run
    verify_run(source,json.loads((source/'manifest.json').read_text())['conditions'])


def test_unknown_version_and_assertion_conflict_are_not_validated(tmp_path):
    source=tmp_path/'source'
    write_turn(source/'logs/turn1',{'input_tokens':7,'output_tokens':2})
    invocation=source/'logs/turn1/invocation.json'
    data=json.loads(invocation.read_text());data['codex_sandbox_version']='0.166.0';save(invocation,data)
    report=recalculate(source,tmp_path/'unknown')
    assert not report['usage_verified'] and report['tokens']['input'] is None
    report=recalculate(source,tmp_path/'conflict',codex_version='0.165.0')
    assert not report['usage_verified']


def test_session_metadata_is_bound_to_thread_and_expected_version_is_not_proof(tmp_path):
    source=tmp_path/'source'
    write_turn(source/'logs/turn1',{'input_tokens':7,'output_tokens':2})
    path=source/'logs/turn1/invocation.json'
    data=json.loads(path.read_text());data.pop('codex_sandbox_version');save(path,data)
    report=recalculate(source,tmp_path/'unproven',codex_version='0.165.0')
    assert not report['usage_verified'] and report['tokens']['input'] is None
    state=source/'state/sessions/session.jsonl';state.parent.mkdir(parents=True)
    state.write_text(json.dumps({'type':'session_meta','payload':{'id':'thread','cli_version':'0.165.0'}})+'\n')
    report=recalculate(source,tmp_path/'proven')
    assert report['usage_verified'] and report['tokens']['input']==7


def test_missing_declared_fallback_does_not_leak_into_functional_tokens(tmp_path):
    source=tmp_path/'source'
    logs=source/'logs/aut'
    write_turn(logs/'phase_a',{'input_tokens':10,'output_tokens':1})
    save(logs/'result.json',{'usage':{'input_tokens':40,'output_tokens':4}})
    save(logs/'skill_gate.json',{'skill_gate_retry_count':0,'skill_gate_fallback_used':True})
    write_turn(source/'steps/01/attempts/001/logs/aut/turn',{'input_tokens':30,'output_tokens':3},expected='thread')
    report=recalculate(source,tmp_path/'export')
    assert not report['usage_verified'] and report['tokens']['input'] is None
    assert report['turn_count']==3
