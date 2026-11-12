"""Protocollo v2: test deterministici, nessun Docker o modello reale."""
from dataclasses import replace
from pathlib import Path
import json
import subprocess

import pytest

from test_cost266 import case, fake_checker, fake_aut
from benchmark_core.cost266 import runner, continuous
from benchmark_core.cost266.protocol import Cell, CONTINUOUS_VERSION, VERSION, prompts, digest
from benchmark_core.workspace import tree_hash, write_json


class ScriptedSession:
    instances = []
    fault = None
    read_schedule = None

    def __init__(self, *, workspace,state,logs,config):
        self.workspace,self.state,self.logs,self.config = workspace,state,logs,config
        self.name=None;self.readonly=True;self.thread_id=None
        self.cleanup=[];self.commands=[];self.turns=[];self.overhead=0.0;self.version='fixture'
        self.creates=[];self.received=[];self.read_count=0;self.completed_stages=[]
        self.instances.append(self)

    def create(self, *, readonly):
        self.readonly=readonly
        self.name='sandbox-'+str(len(self.creates)+1)
        self.creates.append(readonly);self.overhead+=0.25
        if not readonly and self.fault=='transition':self.thread_id='unexpected-transition'
        self.state.mkdir(parents=True,exist_ok=True)
        if self.fault=='create':raise RuntimeError('create failure')

    def close(self):
        if self.name:
            self.cleanup.append({'name':self.name,'ok':self.fault!='cleanup','error':None})
            self.overhead+=0.1
            if self.fault=='cleanup':raise RuntimeError('cleanup failure')
            self.name=None

    def turn(self, *, prompt,directory,timeout):
        directory.mkdir(parents=True,exist_ok=False)
        prior=self.thread_id
        self.received.append((self.readonly,prompt,self.name,prior))
        assert timeout>0
        saved=prompt[:-1] if self.fault=='stdin' and not self.readonly else prompt
        (directory/'prompt_sent.md').write_bytes(saved)
        (directory/'stderr.log').write_text('')
        value=self.thread_id or 'thread-initial'
        index=int(directory.parts[directory.parts.index('steps')+1]) if 'steps' in directory.parts else 0
        if index==3 and self.fault=='lost_thread':value='thread-other'
        self.thread_id=value
        events=[{'type':'thread.started','thread_id':value}]
        if index==3 and self.fault=='missing_thread':events=[]
        if self.readonly:
            from benchmark_core.skill_modes import mode_details
            available=list(mode_details(self.config.data.get('fixture_mode','no_skill')).forced_skills)
            names=(self.read_schedule[self.read_count] if self.read_schedule and self.read_count<len(self.read_schedule) else available)
            if directory.name!='fallback':
                self.read_count+=1
                for name in names:
                    events.append({'type':'item.completed','item':{'id':name,'type':'command_execution',
                        'command':f'cat .codex/skills/{name}/SKILL.md','exit_code':0,'status':'completed',
                        'aggregated_output':(self.workspace/'.codex/skills'/name/'SKILL.md').read_text()}})
            usage={'input_tokens':11,'output_tokens':3,'reasoning_output_tokens':1,'cached_input_tokens':5}
            if self.fault=='gate_mutation':(self.workspace/'lab.conf').write_text('altered')
        else:
            assert (self.workspace/'.codex/skills').is_dir()
            # Il workspace conserva direttamente la modifica della prima fase.
            if index>1:assert (self.workspace/'root/etc/bind/phase1').read_text()=='persistent'
            target=self.workspace/'root/etc/bind';target.mkdir(parents=True,exist_ok=True)
            if index==1:(target/'phase1').write_text('persistent')
            self.completed_stages.append(index)
            usage={'input_tokens':10*index,'output_tokens':index,'reasoning_output_tokens':1,'cached_input_tokens':index}
            if self.fault=='unknown_usage' and index==2:usage=None
            if self.fault=='routing' and index==3:
                with (self.workspace/'root.startup').open('a') as f:f.write('ip route add default via 192.0.2.1\n')
            if self.fault=='symlink' and index==3:(self.workspace/'link').symlink_to('/etc/passwd')
            if self.fault=='skill_mutation' and index==3:(self.workspace/'.codex/extra').write_text('forbidden')
        failed=index==3 and self.fault in ('failure','timeout','interrupt')
        events.append({'type':'turn.failed'} if failed else {'type':'turn.completed','usage':usage})
        if index==3 and self.fault=='missing_completion':events=events[:-1]
        if index==3 and self.fault=='blocking_event':events.append({'type':'error','message':'blocked'})
        (directory/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        result={'returncode':1 if failed else 0,'timed_out':self.fault=='timeout' and failed,
                'duration_seconds':2,'usage':usage,'session_id':value,'stdin_delivery_verified':True}
        write_json(directory/'result.json',result)
        write_json(directory/'invocation.json',{'command':['codex','exec']+(['resume',prior] if prior else []),
            'stdin_bytes':len(saved),'stdin_sha256':digest(saved),'session_expected':prior})
        self.commands.append(['fixture']);self.turns.append((directory,result))
        if failed:
            if self.fault=='interrupt':raise KeyboardInterrupt()
            raise RuntimeError('timeout' if self.fault=='timeout' else 'stage failure')
        return events,result


@pytest.fixture
def v2(case,monkeypatch):
    case.spec=replace(case.spec,protocol=CONTINUOUS_VERSION)
    ScriptedSession.instances=[];ScriptedSession.fault=None;ScriptedSession.read_schedule=None
    monkeypatch.setattr(continuous,'ProtectedCodexSession',ScriptedSession)
    monkeypatch.setattr(continuous,'sbx_get_sandbox_id',lambda name:'id-'+name if name else None)
    monkeypatch.setattr(runner,'run_checker',fake_checker())
    monkeypatch.setattr(runner,'run_aut',lambda *a,**k:pytest.fail('incremental v2 must not call run_aut'))
    return case


def run(v2,mode='no_skill',**kwargs):
    return runner.execute(v2.config,v2.spec,Cell(v2.spec.experiment_id,'T1','incremental',mode,1),v2.inventory,v2.preparation,**kwargs)


def forced(v2,mode='dns_only'):
    v2.config.data['aut'].update(skill_protocol='enforced_read_v1',skill_gate_recovery_policy='recovery_v1')
    v2.config.data['fixture_mode']=mode
    for name,key in [('kathara-dns','dns_skill'),('kathara-creation','creation_skill')]:
        path=v2.root/'skills'/name/'SKILL.md';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(f'---\nname: {name}\ndescription: Fixture for continuous session tests.\n---\nRead the whole fixture skill.\n')
        v2.config.data['aut'][key]=str(path.relative_to(v2.root))


def test_six_turns_one_workspace_sandbox_thread_and_checkpoints(v2,monkeypatch):
    calls=[]
    copies=[];preparations=[]
    original_copy=continuous.copy_lab;original_prepare=continuous.prepare_skill_workspace
    def copy(*args,**kwargs):copies.append(args);return original_copy(*args,**kwargs)
    def prepare(*args,**kwargs):preparations.append(args);return original_prepare(*args,**kwargs)
    monkeypatch.setattr(continuous,'copy_lab',copy)
    monkeypatch.setattr(continuous,'prepare_skill_workspace',prepare)
    checker=fake_checker()
    def check(config,run,correction):
        session=ScriptedSession.instances[0]
        assert session.name is None and len(session.cleanup)==1
        assert len(list(run.glob('steps/*/checkpoint')))==6
        calls.append(correction.read_bytes());return checker(config,run,correction)
    monkeypatch.setattr(runner,'run_checker',check)
    path=run(v2)
    session=ScriptedSession.instances[0]
    assert session.creates==[False] and len(session.received)==6 and len(calls)==1
    assert len(copies)==1 and len(preparations)==1
    assert len({entry[2] for entry in session.received})==1
    assert [entry[3] for entry in session.received]==[None]+['thread-initial']*5
    assert not session.workspace.exists() and not session.state.exists()
    metadata=json.loads((path/'manifest.json').read_text())
    assert metadata['pipeline_state']=='COMPLETED' and metadata['session_cleanup_ok']
    assert metadata['thread_id']=='thread-initial' and metadata['context_continuity_verified']
    for i in range(1,7):
        step=path/'steps'/f'{i:02d}'
        marker=json.loads((step/'completed.json').read_text())
        assert tree_hash(step/'checkpoint')==marker['checkpoint_sha256']
        assert not list((step/'checkpoint').rglob('.codex'))
        assert not list((step/'checkpoint').rglob('correction.yaml'))
        stage=json.loads((step/'attempts/001/manifest.json').read_text())
        assert stage['stage_completed'] and stage['thread_id']=='thread-initial'
        assert stage['sandbox_id']=='id-sandbox-1'
    assert len(list(path.glob('steps/*/attempts/*/logs/aut/*.eval')))==6


def test_only_current_prompt_is_sent_and_future_prompts_stay_on_host(v2,monkeypatch):
    messages=[f'ONLY_STAGE_{i}_PRIVATE_REQUIREMENT' for i in range(1,7)]
    monkeypatch.setattr(runner,'prompts',lambda *args:messages)
    original=ScriptedSession.turn
    def inspect(self,**kwargs):
        index=len(self.received)
        assert kwargs['prompt'].decode()==messages[index]
        for source in (self.workspace,self.state):
            if source.exists():
                for p in source.rglob('*'):
                    if p.is_file():
                        data=p.read_bytes()
                        assert all(message.encode() not in data for message in messages[index+1:])
        return original(self,**kwargs)
    monkeypatch.setattr(ScriptedSession,'turn',inspect)
    path=run(v2)
    assert json.loads((path/'manifest.json').read_text())['task_success'] is True
    assert [p.decode() for _,p,_,_ in ScriptedSession.instances[0].received]==messages


@pytest.mark.parametrize('mode',['dns_only','creation_only','both_forced'])
def test_functional_prompts_unchanged_and_skill_directory_persists(v2,mode):
    from benchmark_core.skill_modes import mode_details
    forced(v2,mode)
    path=run(v2,mode)
    session=ScriptedSession.instances[0]
    expected=prompts(v2.inventory,Cell(v2.spec.experiment_id,'T1','incremental',mode,1))
    assert [p.decode() for readonly,p,_,_ in session.received if not readonly]==expected
    assert session.creates==[True,False] and len(session.cleanup)==2
    gate=json.loads((path/'logs/aut/skill_gate.json').read_text())
    assert gate['skill_gate_read_attempts']==1 and gate['skill_gate_status']=='completed'
    assert gate['skill_gate_verified_skills']==list(mode_details(mode).forced_skills)
    assert gate['skill_gate_write_seconds']==12
    metrics=json.loads((path/'evaluation/metrics.json').read_text())
    assert metrics['sandbox_count']==2 and metrics['writable_sandbox_count']==1 and metrics['protected_sandbox_count']==1
    assert metrics['session_count']==1 and metrics['functional_turns']==6 and metrics['gate_turns']==1
    assert metrics['tokens']['input']==221 and metrics['tokens']['output']==24
    assert metrics['tokens']['total']==245 and metrics['tokens']['reasoning']==7 and metrics['tokens']['cached_input']==26
    assert metrics['gate_input_tokens']==11 and metrics['functional_input_tokens']==210
    assert metrics['timing']['agent_seconds']==14
    assert metrics['timing']['sandbox_overhead_seconds']==pytest.approx(.7)
    assert metrics['skill_delivery_before_write'] is True


@pytest.mark.parametrize('schedule,attempts,fallback', [([[],['kathara-dns']],2,False),([[],[],[]],3,True)])
def test_gate_retry_and_fallback_are_preserved(v2,schedule,attempts,fallback):
    forced(v2);ScriptedSession.read_schedule=schedule
    path=run(v2,'dns_only')
    gate=json.loads((path/'logs/aut/skill_gate.json').read_text())
    assert gate['skill_gate_read_attempts']==attempts and gate['skill_gate_fallback_used'] is fallback
    assert len(ScriptedSession.instances)==1 and ScriptedSession.instances[0].creates==[True,False]
    assert len(list(path.glob('steps/*/checkpoint')))==6
    metrics=json.loads((path/'evaluation/metrics.json').read_text())
    assert metrics['gate_turns']==attempts+int(fallback)
    assert metrics['tokens']['input']==210+11*metrics['gate_turns']


@pytest.mark.parametrize('fault', ['failure','timeout','lost_thread','missing_thread','missing_completion','blocking_event','routing','symlink','skill_mutation'])
def test_error_stage_three_stops_without_checkpoint_or_checker(v2,monkeypatch,fault):
    ScriptedSession.fault=fault
    monkeypatch.setattr(runner,'run_checker',lambda *a:pytest.fail('checker after failed stage'))
    path=run(v2)
    assert len(ScriptedSession.instances[0].received)==3
    assert len(ScriptedSession.instances[0].cleanup)==1
    assert len(list(path.glob('steps/*/completed.json')))==2
    assert not (path/'steps/03/checkpoint').exists()
    assert (path/'steps/03/attempts/001/logs/aut/events.jsonl').is_file()
    metadata=json.loads((path/'manifest.json').read_text())
    assert metadata['pipeline_state']=='INCOMPLETE' and metadata['task_success'] is None
    assert tree_hash(path/'lab')==tree_hash(path/'steps/02/checkpoint')
    assert metadata['pipeline_error']
    with pytest.raises(ValueError,match='stessa sandbox/thread'):run(v2,resume=True)
    assert len(ScriptedSession.instances)==1


@pytest.mark.parametrize('fault',['stdin','create','cleanup','gate_mutation'])
def test_cleanup_and_security_fail_closed(v2,monkeypatch,fault):
    ScriptedSession.fault=fault
    if fault=='gate_mutation':forced(v2)
    monkeypatch.setattr(runner,'run_checker',lambda *a:pytest.fail('checker after lifecycle failure'))
    path=run(v2,'dns_only' if fault=='gate_mutation' else 'no_skill')
    metadata=json.loads((path/'manifest.json').read_text())
    assert metadata['pipeline_state']=='INCOMPLETE'
    assert ScriptedSession.instances[0].cleanup
    if fault=='cleanup':
        assert metadata['session_cleanup_ok'] is False
        with pytest.raises(ValueError,match='Cleanup'):run(v2,resume=True)
        with pytest.raises(ValueError,match='Cleanup'):run(v2,rerun=True)


def test_interrupt_closes_sandbox_and_preserves_previous_checkpoints(v2,monkeypatch):
    ScriptedSession.fault='interrupt'
    monkeypatch.setattr(runner,'run_checker',lambda *a:pytest.fail('checker after interruption'))
    with pytest.raises(KeyboardInterrupt):run(v2)
    path=v2.root/'runs'/Cell(v2.spec.experiment_id,'T1','incremental','no_skill',1).relative
    assert len(ScriptedSession.instances[0].cleanup)==1
    assert len(list(path.glob('steps/*/completed.json')))==2
    assert json.loads((path/'manifest.json').read_text())['pipeline_state']=='INCOMPLETE'


def test_checker_failure_can_resume_and_recheck_without_new_aut(v2,monkeypatch):
    monkeypatch.setattr(runner,'run_checker',lambda *a:(_ for _ in ()).throw(RuntimeError('checker unavailable')))
    path=run(v2)
    assert json.loads((path/'manifest.json').read_text())['pipeline_state']=='CHECKER_FAILED'
    monkeypatch.setattr(runner,'run_checker',fake_checker())
    run(v2,resume=True)
    run(v2,rerun=True)
    assert len(ScriptedSession.instances)==1 and len(ScriptedSession.instances[0].received)==6
    metadata=json.loads((path/'manifest.json').read_text())
    assert metadata['task_success'] and metadata['evaluation_revision']==1
    assert (path/'evaluation/history/revision_000/metrics.json').exists()


def test_metrics_sum_per_turn_and_unknown_stays_unknown(v2):
    path=run(v2)
    metrics=json.loads((path/'evaluation/metrics.json').read_text())
    assert metrics['tokens']['input']==210 and metrics['tokens']['output']==21
    assert metrics['tokens']['total']==231 and metrics['tokens']['reasoning']==6
    assert metrics['tokens']['cached_input']==21 and metrics['aut_calls']==6
    assert metrics['gate_turns']==0 and metrics['sandbox_count']==1 and metrics['session_count']==1
    assert metrics['timing']['sandbox_overhead_seconds']==pytest.approx(.35)


def test_sandbox_id_change_stops_before_sending_next_prompt(v2,monkeypatch):
    def identity(name):
        session=ScriptedSession.instances[0]
        return 'replaced-id' if len(session.received)>=2 else 'id-'+name
    monkeypatch.setattr(continuous,'sbx_get_sandbox_id',identity)
    path=run(v2)
    assert len(ScriptedSession.instances[0].received)==2
    assert len(list(path.glob('steps/*/checkpoint')))==1
    assert json.loads((path/'manifest.json').read_text())['pipeline_state']=='INCOMPLETE'


def test_gate_transition_cannot_replace_thread(v2):
    forced(v2);ScriptedSession.fault='transition'
    path=run(v2,'dns_only')
    assert len(ScriptedSession.instances[0].received)==1
    assert ScriptedSession.instances[0].creates==[True,False]
    assert not list(path.glob('steps/*/checkpoint'))
    assert 'transizione' in json.loads((path/'manifest.json').read_text())['pipeline_error']


def test_one_shot_recovery_uses_existing_gate_and_counts_without_duplication(v2,monkeypatch):
    from benchmark_core import inspect_runner
    forced(v2)
    monkeypatch.setattr('benchmark_core.docker_sandbox_runner.ProtectedCodexSession',ScriptedSession)
    monkeypatch.setattr(runner,'run_aut',inspect_runner.run_aut)
    cell=Cell(v2.spec.experiment_id,'T1','one_shot','dns_only',1)
    path=runner.execute(v2.config,v2.spec,cell,v2.inventory,v2.preparation)
    metadata=json.loads((path/'manifest.json').read_text())
    assert metadata['task_success'] is True
    metrics=json.loads((path/'evaluation/metrics.json').read_text())
    assert metrics['functional_turns']==1 and metrics['gate_turns']==1 and metrics['aut_calls']==2
    assert metrics['tokens']['input']==21 and metrics['tokens']['output']==4 and metrics['tokens']['total']==25
    assert metrics['functional_input_tokens']==10 and metrics['gate_input_tokens']==11
    assert metrics['functional_agent_seconds']==2 and metrics['gate_agent_seconds']==2


def test_missing_usage_not_invented(v2):
    ScriptedSession.fault='unknown_usage'
    path=run(v2)
    metrics=json.loads((path/'evaluation/metrics.json').read_text())
    assert metrics['tokens']['input'] is None and metrics['tokens']['total'] is None
    assert metrics['task_success'] is True


def test_v2_rejects_other_backends_and_legacy_resume(v2):
    from benchmark_core.cost266.protocol import validate_backend
    v2.config.data['docker_sandbox']['execution_backend']='codex_cli'
    with pytest.raises(ValueError,match='nessun fallback'):
        validate_backend(v2.config,'no_skill',strategy='incremental',protocol=CONTINUOUS_VERSION)
    v2.config.data['docker_sandbox']['execution_backend']='docker_sandbox'
    path=run(v2)
    v2.spec=replace(v2.spec,protocol=VERSION)
    with pytest.raises(ValueError,match='Condizioni'):run(v2,resume=True)


def test_one_shot_dispatch_unchanged_and_report_pairing(v2,monkeypatch):
    from benchmark_core.cost266.reports import aggregate_cost266
    run(v2)
    monkeypatch.setattr(runner,'run_aut',fake_aut(v2))
    cell=Cell(v2.spec.experiment_id,'T1','one_shot','no_skill',1)
    runner.execute(v2.config,v2.spec,cell,v2.inventory,v2.preparation)
    assert len(v2.calls)==1 and len(ScriptedSession.instances)==1
    frames=aggregate_cost266(v2.root,v2.root/'results/test_cost266')
    assert len(frames[0])==2 and 'context_continuity_verified' in frames[0]
    from openpyxl import load_workbook
    book=load_workbook(v2.root/'results/test_cost266/benchmark.xlsx',read_only=True)
    assert book.sheetnames==['Runs','Checks','Summary','Stages','Pairs'];book.close()


def test_real_launcher_uses_resume_for_same_thread(tmp_path,monkeypatch):
    from benchmark_core.docker_sandbox_runner import ProtectedCodexSession
    from benchmark_core.config import Config
    session=ProtectedCodexSession(workspace=tmp_path,state=tmp_path/'state',logs=tmp_path/'logs',
        config=Config(tmp_path,{'aut':{'model':'fixture','reasoning_effort':'low'}}))
    session.name='fixture-sandbox';commands=[]
    monkeypatch.setattr(session,'prefix',lambda:['fixture','exec'])
    def execute(command,**kwargs):
        commands.append(command)
        events=[{'type':'skill_gate.process_attestation','uid':session.uid,'status':
                  'NoNewPrivs:\t1\n'+''.join(f'{key}:\t0000000000000000\n' for key in ('CapEff','CapPrm','CapBnd','CapAmb'))},
                {'type':'thread.started','thread_id':'fixed-thread'},
                {'type':'turn.completed','usage':{'input_tokens':2,'output_tokens':1}}]
        return subprocess.CompletedProcess(command,0,''.join(json.dumps(e)+'\n' for e in events).encode(),b'')
    monkeypatch.setattr('benchmark_core.docker_sandbox_runner.subprocess.run',execute)
    session.turn(prompt=b'first',directory=tmp_path/'first',timeout=1)
    session.turn(prompt=b'second',directory=tmp_path/'second',timeout=1)
    assert 'resume' not in commands[0]
    assert commands[1][commands[1].index('resume')+1]=='fixed-thread'
