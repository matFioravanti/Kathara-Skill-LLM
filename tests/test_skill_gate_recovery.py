"""Deterministic orchestration tests; these do not attest real isolation."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmark_core.skill_gate import run_recovery_gate, SkillGateError
from benchmark_core.workspace import write_json


class ScriptedSession:
    schedule = []
    truncate = False
    fail_at = None
    mutate_at = None
    instances = []

    def __init__(self, *, workspace, state, logs, config):
        self.workspace,self.state,self.logs=workspace,state,logs
        self.thread_id='same-thread'; self.cleanup=[]; self.commands=[]
        self.turns=[]; self.overhead=1; self.version='deterministic-test-double'
        self.creates=[]; self.prompts=[]; self.closed=0
        self.instances.append(self)

    def create(self, *, readonly):
        self.creates.append(readonly)

    def close(self):
        self.closed+=1
        self.cleanup.append({'ok':True})

    def turn(self, *, prompt, directory, timeout):
        directory.mkdir(parents=True)
        self.prompts.append(prompt)
        saved=prompt[:-20] if self.truncate and directory.name=='fallback' else prompt
        (directory/'prompt_sent.md').write_bytes(saved)
        (directory/'stderr.log').write_text('')
        events=[{'type':'thread.started','thread_id':self.thread_id}]
        index=len(self.turns)
        if directory.name=='phase_b':
            (self.workspace/'lab.conf').write_text('configured by test AUT')
        elif directory.name!='fallback':
            for name in self.schedule[index] if index<len(self.schedule) else []:
                raw=(self.workspace/'.codex/skills'/name/'SKILL.md').read_bytes().decode('utf-8')
                events.append({'type':'item.completed','item':{'id':f'item_{len(events)}','type':'command_execution',
                    'command':f'cat .codex/skills/{name}/SKILL.md','status':'completed','exit_code':0,'aggregated_output':raw}})
        events.append({'type':'turn.completed','usage':{'input_tokens':11,'output_tokens':3,'cached_input_tokens':5}})
        (directory/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        result={'returncode':0,'timed_out':False,'duration_seconds':2,'usage':{'input_tokens':11,'output_tokens':3,'cached_input_tokens':5},'stdin_delivery_verified':True}
        self.turns.append((directory,result)); write_json(directory/'result.json',result)
        if self.mutate_at: self.mutate_at(index)
        if self.fail_at==index: raise RuntimeError('Infrastructure failure')
        return events,result


@pytest.fixture
def setup(tmp_path):
    workspace=tmp_path/'workspace'; workspace.mkdir()
    (workspace/'lab.conf').write_text('baseline')
    root=tmp_path/'project'; root.mkdir()
    run=root/'runs/case/T1/both_forced/r001'; run.mkdir(parents=True)
    aut={'skill_protocol':'enforced_read_v1','skill_gate_recovery_policy':'recovery_v1'}
    metadata={'agent':'codex','skill_mode':'both_forced','skill_protocol':'enforced_read_v1'}
    for name,key in [('kathara-dns','dns_skill'),('kathara-creation','creation_skill')]:
        raw=f'---\nname: {name}\ndescription: Isolated test fixture.\n---\nComplete bytes for {name}.\r\n'.encode()
        path=root/'skills'/name/'SKILL.md'; path.parent.mkdir(parents=True); path.write_bytes(raw)
        staged=workspace/'.codex/skills'/name/'SKILL.md'; staged.parent.mkdir(parents=True); staged.write_bytes(raw)
        aut[key]=str(path.relative_to(root)); metadata[key+'_sha256']=hashlib.sha256(raw).hexdigest()
    write_json(run/'manifest.json',metadata)
    config=SimpleNamespace(root=root,data={'aut':aut,'benchmark':{'timeout_seconds':5},'docker_sandbox':{'execution_backend':'docker_sandbox'}},
                           path=lambda p:root/p,model=lambda:None,reasoning_effort=lambda:None)
    ScriptedSession.schedule=[]; ScriptedSession.truncate=False; ScriptedSession.fail_at=None
    ScriptedSession.mutate_at=None; ScriptedSession.instances=[]
    def execute(mode='both_forced'):
        return run_recovery_gate(config=config,run=run,workspace=workspace,original_prompt='ORIGINAL FUNCTIONAL PROMPT',mode=mode,session_factory=ScriptedSession)
    return config,run,workspace,execute


def record(run): return json.loads((run/'logs/aut/skill_gate.json').read_text())


@pytest.mark.parametrize('mode,skills',[('dns_only',['kathara-dns']),('creation_only',['kathara-creation']),('both_forced',['kathara-creation','kathara-dns'])])
def test_direct_read_opens_gate(setup,mode,skills):
    cfg,run,ws,execute=setup
    ScriptedSession.schedule=[skills]
    execute(mode)
    d=record(run); s=ScriptedSession.instances[0]
    assert d['skill_gate_status']=='completed'
    assert d['skill_gate_load_methods']==dict.fromkeys(skills,'read_verified')
    assert s.creates==[True,False] and s.prompts[-1]==b'ORIGINAL FUNCTIONAL PROMPT'
    assert (ws/'lab.conf').read_text()=='configured by test AUT'
    assert d['skill_gate_read_attempts']==1 and d['skill_gate_retry_count']==0
    assert d['skill_gate_initial_input_tokens']==11 and d['write_phase_input_tokens']==11


@pytest.mark.parametrize('schedule,attempts,method',[
    ([[],['kathara-dns']],2,'retry_verified'),
    ([[],[],['kathara-dns']],3,'retry_verified'),
    ([[],[],[]],3,'preloaded_fallback'),
])
def test_bounded_retry_and_fallback(setup,schedule,attempts,method):
    cfg,run,ws,execute=setup; ScriptedSession.schedule=schedule
    execute('dns_only'); d=record(run); s=ScriptedSession.instances[0]
    assert d['skill_gate_read_attempts']==attempts
    assert d['skill_gate_retry_count']==attempts-1
    assert d['skill_gate_load_methods']=={'kathara-dns':method}
    assert d['skill_gate_session_count']==1 and d['skill_gate_session_id']=='same-thread'
    assert len(list((run.parents[0]).glob('r*')))==1
    assert len(s.turns)<=5 and s.creates==[True,False] and s.closed>=2
    if method=='preloaded_fallback':
        prompt=(run/'logs/aut/fallback/prompt_sent.md').read_bytes()
        raw=cfg.path(cfg.data['aut']['dns_skill']).read_bytes()
        assert raw in prompt and b'\r\n' in prompt
        assert d['skill_gate_fallback_sha256_verified'] is True
        assert d['skill_gate_context_delivery_verified'] is True
        assert d['skill_gate_verified_skills']==['kathara-dns']
        assert d['skill_gate_retry_input_tokens']==22
        assert d['skill_gate_input_tokens']==44


def test_retry_only_missing_skill(setup):
    cfg,run,ws,execute=setup
    ScriptedSession.schedule=[['kathara-creation'],['kathara-dns']]
    execute(); s=ScriptedSession.instances[0]; d=record(run)
    assert b'kathara-creation' not in s.prompts[1]
    assert d['skill_gate_load_methods']=={'kathara-creation':'read_verified','kathara-dns':'retry_verified'}
    from benchmark_core.run_metrics import make_metrics
    meta=json.loads((run/'manifest.json').read_text())
    m=make_metrics(run,meta,total_seconds=10,checker_seconds=None,checker_outcome=None)
    assert set(m['skill_compliance']['observed_read_skills'])=={'kathara-creation','kathara-dns'}


def test_mixed_read_and_preload(setup):
    cfg,run,ws,execute=setup; ScriptedSession.schedule=[['kathara-creation'],[],[]]
    execute(); d=record(run)
    assert d['skill_gate_load_methods']=={'kathara-creation':'read_verified','kathara-dns':'preloaded_fallback'}
    assert d['skill_gate_fallback_skills']==['kathara-dns']
    assert b'BEGIN SKILL kathara-creation' not in (run/'logs/aut/fallback/prompt_sent.md').read_bytes()


def test_zero_retries_goes_to_fallback(setup):
    cfg,run,ws,execute=setup; cfg.data['aut']['skill_gate_max_retries']=0
    execute('dns_only'); d=record(run)
    assert d['skill_gate_read_attempts']==1 and d['skill_gate_retry_count']==0
    assert d['skill_gate_retry_input_tokens'] is None


@pytest.mark.parametrize('kind',['wrong_initial_hash','changed_source','truncated_fallback','changed_lab','infrastructure'])
def test_technical_failure_never_unlocks(setup,kind):
    cfg,run,ws,execute=setup
    if kind=='wrong_initial_hash':
        d=json.loads((run/'manifest.json').read_text()); d['dns_skill_sha256']='0'*64; write_json(run/'manifest.json',d)
    elif kind=='changed_source':
        ScriptedSession.mutate_at=staticmethod(lambda index:cfg.path(cfg.data['aut']['dns_skill']).write_bytes(b'changed') if index==2 else None)
    elif kind=='truncated_fallback': ScriptedSession.truncate=True
    elif kind=='changed_lab': ScriptedSession.mutate_at=staticmethod(lambda index:(ws/'lab.conf').write_text('illegal'))
    else: ScriptedSession.fail_at=0
    with pytest.raises((SkillGateError,RuntimeError)): execute('dns_only')
    d=record(run)
    assert d['skill_gate_status']=='technical_error' and d['skill_gate_blocked']
    assert not (run/'logs/aut/phase_b').exists()
    if ScriptedSession.instances: assert ScriptedSession.instances[0].creates==[True]


@pytest.mark.parametrize('value',[-1,11,True,'2'])
def test_invalid_retry_limits(setup,value):
    cfg,run,ws,execute=setup; cfg.data['aut']['skill_gate_max_retries']=value
    with pytest.raises(ValueError): execute()


def test_missing_usage_is_null_and_totals_not_cached_twice(setup):
    from benchmark_core.run_metrics import make_metrics
    cfg,run,ws,execute=setup; ScriptedSession.schedule=[['kathara-dns']]
    execute('dns_only')
    m=make_metrics(run,{'agent':'codex','skill_mode':'dns_only'},total_seconds=20,checker_seconds=None,checker_outcome=None)
    assert m['tokens']['input']==22 and m['tokens']['cached_input']==10
    assert m['tokens']['total']==28
    assert m['skill_gate_retry_input_tokens'] is None


def test_aggregation_separates_policy_and_exports_methods(setup,tmp_path):
    from benchmark_core.aggregation import aggregate
    import openpyxl
    cfg,run,ws,execute=setup; ScriptedSession.schedule=[['kathara-creation'],[],[]]
    execute()
    m={**record(run),'agent':'codex','skill_mode':'both_forced','skill_protocol':'enforced_read_v1','scenario':'case','prompt_type':'T1'}
    write_json(run/'evaluation/metrics.json',m)
    legacy=run.parent/'r002'; legacy.mkdir(); write_json(legacy/'manifest.json',json.loads((run/'manifest.json').read_text()))
    write_json(legacy/'evaluation/metrics.json',{**m,'skill_gate_recovery_policy_version':None,'skill_gate_load_methods':None})
    rows,_,summary=aggregate(run.parents[3],tmp_path/'reports')
    assert len(summary)==2
    recovery=summary[summary['skill_gate_recovery_policy_version']=='recovery_v1'].iloc[0]
    assert recovery['skill_gate_direct_runs']==1 and recovery['skill_gate_fallback_runs']==1
    assert recovery['skill_gate_retry_runs']==0 and recovery['skill_gate_delivery_denominator']==1
    assert recovery['skill_gate_fallback_rate']==1
    book=openpyxl.load_workbook(tmp_path/'reports/benchmark.xlsx',read_only=True)
    assert 'skill_gate_load_methods' in [c.value for c in next(book['Runs'].iter_rows())]


@pytest.mark.parametrize('mode,skills',[('dns_only',['kathara-dns']),('creation_only',['kathara-creation']),('both_forced',['kathara-creation','kathara-dns'])])
def test_ordinary_pipeline_reaches_checker(setup,monkeypatch,mode,skills):
    from benchmark_core import pipeline
    from benchmark_core.config import Config
    from benchmark_core.scenario_loader import Scenario
    cfg,_,_,_=setup
    source=cfg.root/'scenarios/tiny'; (source/'lab').mkdir(parents=True)
    (source/'lab/lab.conf').write_text('baseline')
    (source/'correction.yaml').write_text('fixture')
    (cfg.root/'prompt/tiny').mkdir(parents=True)
    (cfg.root/'prompt/tiny/T1.md').write_text('ORIGINAL FUNCTIONAL PROMPT')
    cfg.data['aut']['version']='test'
    cfg.data['sandbox']={'image':'fixture'}
    config=Config(cfg.root,cfg.data)
    ScriptedSession.schedule=[skills]
    monkeypatch.setattr('benchmark_core.docker_sandbox_runner.ProtectedCodexSession',ScriptedSession)
    monkeypatch.setattr(pipeline,'component_versions',lambda:{})
    monkeypatch.setattr(pipeline,'read_correction',lambda p:(b'fixture','sha'))
    monkeypatch.setattr(pipeline,'validate_correction',lambda p:'sha')
    checked=[]
    def checker(config,run,correction):
        assert (run/'lab/lab.conf').read_text()=='configured by test AUT'
        checked.append(run)
        return {'checks_passed':1,'checks_failed':0,'checks_total':1,'check_pass_rate':1,'task_success':True}
    monkeypatch.setattr(pipeline,'run_checker',checker)
    run=pipeline.run_one(config,Scenario('tiny',source),'codex','T1',mode)
    manifest=json.loads((run/'manifest.json').read_text())
    assert manifest['pipeline_state']=='COMPLETED' and len(checked)==1
    assert manifest['skill_gate_load_methods']==dict.fromkeys(skills,'read_verified')
    assert manifest['skill_gate_recovery_policy_version']=='recovery_v1'
    assert (source/'lab/lab.conf').read_text()=='baseline'


@pytest.mark.parametrize('kind',['ok','missing_thread','wrong_thread','failed_turn','privileged','timeout'])
def test_real_launcher_checks_thread_and_privilege_events(tmp_path,monkeypatch,kind):
    import subprocess
    from benchmark_core.docker_sandbox_runner import ProtectedCodexSession, SandboxError
    config=SimpleNamespace(model=lambda:None,reasoning_effort=lambda:None)
    session=ProtectedCodexSession(workspace=tmp_path,state=tmp_path/'state',logs=tmp_path/'logs',config=config)
    session.name='unit-only'; session.thread_id='expected-thread'
    status='NoNewPrivs:\t1\n'+''.join(f'{key}:\t0000000000000000\n' for key in ('CapEff','CapPrm','CapBnd','CapAmb'))
    events=[{'type':'skill_gate.process_attestation','uid':session.uid,'status':status}]
    if kind!='missing_thread': events.append({'type':'thread.started','thread_id':'other-thread' if kind=='wrong_thread' else 'expected-thread'})
    if kind=='privileged': events[0]['uid']=0
    events.append({'type':'turn.failed' if kind=='failed_turn' else 'turn.completed','usage':{'input_tokens':5,'output_tokens':1}})
    raw=''.join(json.dumps(e)+'\n' for e in events).encode()
    payload=b'Exact input bytes\r\nUnicode: \xc3\xa8\n'
    def fake_run(command,**kwargs):
        assert kwargs['input']==payload
        assert 'resume' in command and 'expected-thread' in command
        assert '--ephemeral' not in command and '--bounding-set=-all' in command
        if kind=='timeout': raise subprocess.TimeoutExpired(command,5,output=raw,stderr=b'timed out')
        return subprocess.CompletedProcess(command,0,raw,b'')
    monkeypatch.setattr(subprocess,'run',fake_run)
    directory=tmp_path/'logs/retries/attempt_01'
    if kind=='ok':
        _,result=session.turn(prompt=payload,directory=directory,timeout=5)
        assert result['stdin_delivery_verified'] and session.thread_id=='expected-thread'
    else:
        with pytest.raises(SandboxError): session.turn(prompt=payload,directory=directory,timeout=5)
        assert json.loads((directory/'result.json').read_text()).get('error')
    assert (directory/'prompt_sent.md').read_bytes()==payload
