"""No agents/Docker: subprocess tests use only local dummy Python workers."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from benchmark_core.config import Config
from benchmark_core import standard_runtime as rt
from benchmark_core import standard_auth as auth


@pytest.mark.parametrize('message,kind',[
    ('AUTH_FAILED','AUTH_FAILED'),('401 Unauthorized','AUTH_FAILED'),('refresh token revoked','AUTH_FAILED'),
    ('session expired','AUTH_FAILED'),('timeout=True','TIMEOUT'),('crash','CRASH'),
    ('HTTP 503','TRANSIENT'),('hash alterato','INTEGRITY_FAILED'),('invalid configuration','PERMANENT')])
def test_classification(message,kind):
    assert rt.classify(message)==kind


@pytest.mark.parametrize('options',[{'max_attempts':0},{'max_attempts':2.5},{'heartbeat_seconds':0},
    {'auth_wait_seconds':-1},{'memory_limit_mb':float('nan')},{'auto_resume':1},{'unknown':2}])
def test_policy_validation(tmp_path,options):
    with pytest.raises(ValueError): rt.Policy.from_config(Config(tmp_path,{'resilience':options}))


def test_atomic_write_preserves_old_on_failure(tmp_path,monkeypatch):
    p=tmp_path/'checkpoint.json'; rt.atomic_json(p,{'valid':1})
    monkeypatch.setattr(rt.os,'replace',Mock(side_effect=OSError('disk')))
    with pytest.raises(OSError): rt.atomic_json(p,{'valid':2})
    assert json.loads(p.read_text())=={'valid':1}
    assert list(tmp_path.iterdir())==[p]


@pytest.fixture
def cell(tmp_path,monkeypatch):
    expected={'skill_mode':'dns_only'}
    monkeypatch.setattr('benchmark_core.fingerprint.conditions',lambda *a,**kw:expected)
    cfg=Config(tmp_path,{'resilience':{'backoff_seconds':0,'auth_wait_seconds':0}})
    scenario=SimpleNamespace(scenario_id='lab_01')
    monkeypatch.setattr(rt,'validate_artifacts',lambda *a,**kw:None)
    return cfg,scenario


def trial(cfg,number,status='AUT_FAILED',aut=False,error='AUTH_FAILED'):
    run=cfg.root/'runs'/'trial'/f'r{number:03d}'
    rt.atomic_json(run/'manifest.json',{'pipeline_state':status,'aut_execution_success':aut,'pipeline_error':error})
    return run


def test_auth_failed_restarts_generation_and_completed_resume(cell,monkeypatch):
    cfg,scenario=cell; calls=[]
    def attempt(*args):
        calls.append(args[5]); n=len(calls)
        return trial(cfg,n,'COMPLETED' if n==2 else 'AUT_FAILED'),None
    monkeypatch.setattr(rt,'_attempt',attempt)
    refresh=Mock(return_value=True); monkeypatch.setattr(auth,'refresh_account',refresh)
    result=rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='test',replicate=1)
    assert calls==[None,None] and refresh.call_count==1
    assert rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='test',replicate=1)==result
    assert len(calls)==2
    checkpoint=next((cfg.root/'runs/.supervision').glob('*/checkpoint.json'))
    data=rt.load(checkpoint)
    assert data['status']=='COMPLETED' and len(data['attempts'])==2
    assert (cfg.root/'runs/trial/r001/manifest.json').exists()


def test_checker_retry_only_resumes_evaluation(cell,monkeypatch):
    cfg,scenario=cell; calls=[]
    def attempt(*args):
        calls.append(args[5]); n=len(calls)
        return trial(cfg,1,'COMPLETED' if n==2 else 'CHECKER_FAILED',True,'timeout=True'),None
    monkeypatch.setattr(rt,'_attempt',attempt)
    result=rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='test')
    assert calls==[None,result]


def test_auth_interactive_budget_and_block_later_cells(cell,monkeypatch):
    cfg,scenario=cell
    monkeypatch.setattr(auth,'refresh_account',Mock(return_value=False))
    attempt=Mock(return_value=(trial(cfg,1),None)); monkeypatch.setattr(rt,'_attempt',attempt)
    with pytest.raises(rt.RecoveryRequired,match='WAITING_AUTH'):
        rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='test')
    with pytest.raises(rt.RecoveryRequired,match='WAITING_AUTH'):
        rt.run_supervised(cfg,scenario,'codex','T2',skill_mode='dns_only',experiment_id='test')
    assert attempt.call_count==1
    assert auth.refresh_account.call_count==4


def test_session_restored_while_waiting_resumes_automatically(tmp_path,monkeypatch):
    refresh=Mock(side_effect=[False,True]); monkeypatch.setattr(auth,'refresh_account',refresh)
    clock=iter([0,0,0,0.1]); monkeypatch.setattr(rt.time,'monotonic',lambda:next(clock))
    monkeypatch.setattr(rt.time,'sleep',lambda _:None)
    assert rt.recover_auth(rt.Policy(auth_wait_seconds=1),tmp_path/'checkpoint.json',{})
    assert refresh.call_count==2


@pytest.mark.parametrize('failure',['TIMEOUT','CRASH','TRANSIENT','MEMORY_LIMIT'])
def test_retry_budget_persists_across_invocations(cell,monkeypatch,failure):
    cfg,scenario=cell; attempt=Mock(return_value=(None,failure)); monkeypatch.setattr(rt,'_attempt',attempt)
    for _ in range(2):
        with pytest.raises(rt.RecoveryRequired,match='RETRY_EXHAUSTED'):
            rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='test')
    assert attempt.call_count==3


def test_worker_crash_checkpoint_reconciliation(cell,monkeypatch):
    cfg,scenario=cell; run=trial(cfg,1,'COMPLETED')
    def crash_after_manifest(*args):
        rt.atomic_json(args[6],{'run':str(run),'resources':[]})
        raise KeyboardInterrupt
    monkeypatch.setattr(rt,'_attempt',crash_after_manifest)
    with pytest.raises(KeyboardInterrupt): rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='test')
    monkeypatch.setattr(rt,'_attempt',Mock(side_effect=AssertionError('must not regenerate')))
    assert rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='test')==run


def test_global_lock_prevents_concurrent_recovery():
    with rt.serial_lock():
        with pytest.raises(rt.RecoveryRequired):
            with rt.serial_lock(): pass


def dummy_hang(*args):
    import time
    os.setsid()
    time.sleep(60)


def dummy_crash(*args):
    os.setsid(); os._exit(7)


@pytest.mark.parametrize('worker,kind',[(dummy_hang,'TIMEOUT'),(dummy_crash,'CRASH')])
def test_real_watchdog_with_dummy_processes_only(tmp_path,monkeypatch,worker,kind):
    monkeypatch.setattr(rt,'_worker',worker)
    result,failure=rt._attempt(None,None,None,None,{},None,tmp_path/'journal.json',
        rt.Policy(worker_timeout_seconds=.1,heartbeat_seconds=.05,cleanup_grace_seconds=.1),tmp_path/'heartbeat.json')
    assert result is None and failure==kind


def test_report_error_retry_and_continue(tmp_path,monkeypatch):
    monkeypatch.setattr(rt.time,'sleep',lambda _:None)
    operation=Mock(side_effect=OSError('disk unavailable'))
    assert not rt.retry_reports(operation,Config(tmp_path,{}))
    assert operation.call_count==3
    assert (tmp_path/'runs/.supervision/report_failure.json').exists()


def test_auth_refresh_rpc_redacts_account_and_never_starts_turn(tmp_path,monkeypatch):
    import sys
    fake=tmp_path/'fake_codex'
    fake.write_text('#!'+sys.executable+'''\nimport json,sys
for line in sys.stdin:
    m=json.loads(line)
    if m.get('method')=='initialize': print(json.dumps({'id':0,'result':{}}),flush=True)
    elif m.get('method')=='account/read':
        assert m['params']['refreshToken'] is True
        print(json.dumps({'id':1,'result':{'account':{'type':'chatgpt','email':'sensitive'}}}),flush=True)
    else: assert m['method']=='initialized'
''')
    fake.chmod(0o700)
    monkeypatch.setattr(auth,'codex_executable',lambda:str(fake))
    assert auth.refresh_account(timeout=2)
    assert list(tmp_path.iterdir())==[fake]


def test_native_aut_receipt_detects_token_tampering(tmp_path):
    p=tmp_path/'logs/aut/events.jsonl';p.parent.mkdir(parents=True);p.write_text('original usage')
    receipt=rt.aut_receipt(tmp_path)
    p.write_text('different usage')
    with pytest.raises(ValueError,match='AUT/token'): rt.check_receipt(tmp_path,receipt)


def test_hundreds_of_cells_no_repeated_completed_generation(cell,monkeypatch):
    cfg,scenario=cell; attempts=[]
    def attempt(*args):
        number=len(attempts)+1; attempts.append(number)
        return trial(cfg,number,'COMPLETED'),None
    monkeypatch.setattr(rt,'_attempt',attempt)
    for rep in range(1,251):
        rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='batch',replicate=rep)
    for rep in range(1,251):
        rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='batch',replicate=rep)
    assert len(attempts)==250


def test_memory_watchdog_without_large_allocation(tmp_path,monkeypatch):
    monkeypatch.setattr(rt,'_worker',dummy_hang)
    monkeypatch.setattr(rt,'process_tree',lambda pid:({pid},5000))
    result,failure=rt._attempt(None,None,None,None,{},None,tmp_path/'journal.json',
        rt.Policy(heartbeat_seconds=.01,cleanup_grace_seconds=.1),tmp_path/'heartbeat.json')
    assert failure=='MEMORY_LIMIT'
    assert rt.load(tmp_path/'heartbeat.json')['rss_mb']==5000


def test_cleanup_only_registered_resources(tmp_path,monkeypatch):
    journal=tmp_path/'worker.json'
    rt.atomic_json(journal,{'resources':[{'kind':'sandbox','name':'kathara-owned'}]})
    monkeypatch.setattr('benchmark_core.docker_sandbox_runner.sbx_executable',lambda:'fake-sbx')
    monkeypatch.setattr(rt.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout='[{"name":"unrelated"}]'))
    remove=Mock();monkeypatch.setattr('benchmark_core.docker_sandbox_runner._sbx_rm',remove)
    rt.cleanup_resources(journal)
    remove.assert_not_called()
    monkeypatch.setattr(rt.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout='[{"name":"kathara-owned"}]'))
    remove.return_value=(True,None)
    rt.cleanup_resources(journal)
    remove.assert_called_once_with('kathara-owned')


def test_unverified_cleanup_stops_next_generation(cell,monkeypatch):
    cfg,scenario=cell
    attempt=Mock(side_effect=rt.RecoveryRequired('CLEANUP_FAILED'));monkeypatch.setattr(rt,'_attempt',attempt)
    with pytest.raises(rt.RecoveryRequired): rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='test')
    assert (cfg.root/'runs/.supervision/cleanup_blocked.json').exists()
    monkeypatch.setattr(rt,'cleanup_resources',Mock(side_effect=rt.RecoveryRequired('CLEANUP_FAILED')))
    with pytest.raises(rt.RecoveryRequired): rt.run_supervised(cfg,scenario,'codex','T2',skill_mode='dns_only',experiment_id='test')
    assert attempt.call_count==1


def test_permanent_failure_not_implicitly_retried(cell,monkeypatch):
    cfg,scenario=cell
    run=trial(cfg,1,error='configuration invalid')
    attempt=Mock(return_value=(run,None));monkeypatch.setattr(rt,'_attempt',attempt)
    for _ in range(2):
        assert rt.run_supervised(cfg,scenario,'codex','T1',skill_mode='dns_only',experiment_id='test')==run
    assert attempt.call_count==1


def test_preflight_auth_recovers_before_first_generation(tmp_path,monkeypatch):
    config=Config(tmp_path,{'resilience':{'auth_wait_seconds':0,'backoff_seconds':0}})
    probe=Mock(side_effect=[RuntimeError('AUTH_FAILED'),None])
    monkeypatch.setattr(auth,'refresh_account',lambda:True)
    rt.guarded_preflight(probe,config,'codex')
    assert probe.call_count==2
