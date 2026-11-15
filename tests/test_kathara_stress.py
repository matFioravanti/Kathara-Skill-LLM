"""Checker-only stress tests: all Docker/host probes and checker execution mocked."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib
import json
import threading
import time

import pytest
from benchmark_core import kathara_stress as stress
from benchmark_core.checker_runner import CheckerCancelled, wait_checker
from benchmark_core.workspace import tree_hash
from scripts import stress_test_kathara as cli


def fixture_run(root, number, *, aut=True):
    run=root/f'runs/thesis_final/lab_01/base/small/T1/no_skill/r{number:03d}'
    (run/'lab').mkdir(parents=True)
    (run/'lab/lab.conf').write_text('pc1[0]="A"\n')
    (run/'lab/pc1.startup').write_text('true\n')
    (run/'evaluation').mkdir()
    correction=run/'evaluation/correction.yaml'
    correction.write_text('lab_inline: |\n  pc1[0]="A"\ndefault_image: kathara/base\nconvergence_time: 1\n')
    data={'experiment_id':'thesis_final','task_level':'small','lab_id':'lab_01',
          'dns_tree_id':'base','prompt_type':'T1','skill_mode':'no_skill',
          'replicate':number,'run_number':number,'aut_execution_success':aut,
          'task_success':False,'pipeline_state':'CHECKER_FAILED',
          'started_at':f'2026-11-14T10:{number:02d}:00+00:00',
          'final_lab_sha256':tree_hash(run/'lab'),
          'correction_sha256':hashlib.sha256(correction.read_bytes()).hexdigest()}
    (run/'manifest.json').write_text(json.dumps(data))
    return run


@pytest.fixture
def originals(tmp_path,monkeypatch):
    def parse(path):
        text=(path/'lab.conf').read_text()
        return SimpleNamespace(machines={'pc1':SimpleNamespace(meta={})},links={},hash=hashlib.sha256(text.encode()).hexdigest())
    monkeypatch.setattr(stress,'parse_lab',parse)
    for n in range(1,17):fixture_run(tmp_path,n,aut=n!=16)
    return tmp_path


def test_selection_keeps_functional_failures_and_rejects_incomplete(originals):
    sources,rejected=stress.select_sources(originals,'thesis_final',15)
    assert len(sources)==15 and len(rejected)==1
    assert 'AUT non completato' in rejected[0]['reason']
    assert Path(sources[0].path).name=='r015'
    with pytest.raises(ValueError,match='disponibili 15'):
        stress.select_sources(originals,'thesis_final',16)


def test_changed_aut_excluded(originals):
    (originals/'runs/thesis_final/lab_01/base/small/T1/no_skill/r001/lab/pc1.startup').write_text('changed')
    with pytest.raises(ValueError,match='hash finale AUT'):
        stress.select_sources(originals,'thesis_final',15)


def test_copy_namespaces_unique_and_originals_unchanged(originals,tmp_path):
    sources,_=stress.select_sources(originals,'thesis_final',15)
    before=tree_hash(originals/'runs')
    copies=[stress.prepare(s,tmp_path/'copies',n) for n,s in enumerate(sources)]
    assert len({c['lab_hash'] for c in copies})==15
    assert len({c['namespace'] for c in copies})==15
    assert tree_hash(originals/'runs')==before
    stress.verify_sources(sources)


def test_scoped_cleanup_never_removes_foreign_or_baseline():
    probe=object.__new__(stress.DockerProbe);probe.api=Mock()
    probe.baseline={'baseline'};probe.baseline_networks={'baseline_net'}
    def entry(ident,h,app='kathara'):return {'Id':ident,'Labels':{'app':app,'lab_hash':h}}
    probe.api.containers.return_value=[entry('own','owned'),entry('other','foreign'),entry('baseline','owned'),entry('unrelated','owned','other')]
    probe.api.networks.return_value=[entry('own_net','owned'),entry('other_net','foreign'),entry('baseline_net','owned')]
    probe.cleanup({'owned'})
    probe.api.remove_container.assert_called_once_with('own',force=True,v=True)
    probe.api.remove_network.assert_called_once_with('own_net')


def test_different_docker_engines_rejected(monkeypatch):
    import docker
    client=Mock();client.api.info.return_value={'ID':'engine_one'}
    monkeypatch.setattr(docker,'from_env',lambda **kw:client)
    monkeypatch.setattr(stress,'read_cli',lambda *a:'engine_two')
    with pytest.raises(RuntimeError,match='same engine'):
        stress.DockerProbe()


def test_external_oom_is_ignored(originals,tmp_path,monkeypatch):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe()
    probe.api.events=lambda **kw:SimpleStream([{'Action':'oom','Actor':{'Attributes':{'lab_hash':'foreign'}}}])
    monkeypatch.setattr(stress,'run_checker',lambda *a,**kw:{'task_success':False})
    summary,_,_=stress.run_level(sources,tmp_path/'foreign_oom',3,options(),probe)
    assert not summary['stopped'] and summary['completed']==15


@pytest.mark.parametrize('sample,reason',[
    ({'host_pressure_critical':True},'critical'),
    ({'container_memory_bytes_sum':85,'docker_memory_limit_bytes':100},'proxy'),
    ({'container_memory_bytes_sum':84,'docker_memory_limit_bytes':100},None),
    ({'docker_global_memory_bytes':None},None),
])
def test_guards(sample,reason):
    result=stress.guard(sample,.85)
    assert reason in result if reason else result is None


def test_memory_usage_is_not_limit():
    assert stress.amount('1.5GiB')==1.5*1024**3
    assert stress.amount('128MiB')==128*1024**2
    with pytest.raises(ValueError):stress.amount('not available')


def test_stats_timeout_preserves_inventory(monkeypatch):
    import subprocess
    probe=object.__new__(stress.DockerProbe);probe.timeout=20;probe.info={'MemTotal':100}
    probe.inventory=lambda:([{'Id':'abc','State':'running','Labels':{'lab_hash':'h'}}],[])
    def cli(args,timeout=15):
        if args[0]=='docker':raise subprocess.TimeoutExpired(args,timeout)
        return ''
    monkeypatch.setattr(stress,'read_cli',cli);monkeypatch.setattr(stress,'host_sample',lambda:{})
    s=probe.sample([{'lab_hash':'h','devices':1,'directory':'/test'}])
    assert s['containers']==1 and s['active_labs']==1
    assert s['container_memory_bytes_sum'] is None and 'TimeoutExpired' in s['stats_error']


def test_tracker_survives_missing_docker_samples():
    t=stress.Tracker()
    for n in range(15):t.process('start',n);t.event('start',str(n),'lab'+str(n))
    assert t.peak==15 and t.peak_labs==15 and t.peak_containers==15
    t.event('die','0','lab0');assert t.snapshot()['tracked_active_labs']==14


def test_monitor_recovers_while_checkers_run(originals,tmp_path,monkeypatch):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe();calls=[]
    def sample(instances):
        calls.append(1)
        if len(calls)<=2:raise TimeoutError('Docker temporarily unavailable')
        return {'monotonic':time.monotonic(),'checker_processes':None,'active_labs':0,'containers':0}
    probe.sample=sample
    def checker(*args,process_callback=None,**kwargs):
        pid=threading.get_ident();process_callback('start',pid);time.sleep(.04);process_callback('end',pid)
        return {'task_success':True}
    monkeypatch.setattr(stress,'run_checker',checker)
    summary,rows,_=stress.run_level(sources,tmp_path/'recovery',3,options(),probe)
    assert summary['completed']==15 and not summary['stopped']
    assert summary['max_checker_processes']==3
    assert len(summary['monitoring_errors'])>=2


def test_checker_continues_during_temporary_stats_timeout(originals,tmp_path,monkeypatch):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe();calls=[]
    def sample(instances):
        calls.append(1)
        return {'monotonic':time.monotonic(),'checker_processes':None,'active_labs':0,'containers':0,
                'stats_error':'TimeoutExpired: docker stats' if len(calls)<4 else None}
    probe.sample=sample
    def checker(*args,process_callback=None,**kwargs):
        pid=threading.get_ident();process_callback('start',pid);time.sleep(.04);process_callback('end',pid)
        return {'task_success':True}
    monkeypatch.setattr(stress,'run_checker',checker)
    summary,_,samples=stress.run_level(sources,tmp_path/'stats-recovery',3,options(),probe)
    assert summary['completed']==15 and not summary['stopped']
    assert summary['max_checker_processes']==3 and summary['monitor_timeout_count']>=1
    assert any(s.get('stats_error') for s in samples) and any(not s.get('stats_error') for s in samples)


@pytest.mark.parametrize('code,expected', [('0',False),('137',True)])
def test_container_exit_classification(originals,tmp_path,monkeypatch,code,expected):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe()
    def conflicts(hashes):probe.planned=list(hashes);return []
    probe.conflicts=conflicts
    probe.api.events=lambda **kw:SimpleStream([{'Action':'die','id':'container1','timeNano':123,
        'Actor':{'Attributes':{'lab_hash':probe.planned[0],'exitCode':code}}}])
    monkeypatch.setattr(stress,'run_checker',lambda *a,**kw:{'task_success':True})
    summary,_,_=stress.run_level(sources,tmp_path/('exit'+code),3,options(),probe)
    assert not summary['stopped']
    errors=[x for x in summary['monitoring_errors'] if x['kind']=='nonzero_container_exit']
    assert bool(errors)==expected
    if expected: assert errors[0]['exit_code']=='137' and errors[0]['container_id']=='container1'


def test_cancellation_and_timeout():
    stop=threading.Event();stop.set();process=Mock(args=['checker'])
    with pytest.raises(CheckerCancelled):wait_checker(process,900,stop)
    process.wait.assert_not_called()
    import subprocess
    with pytest.raises(subprocess.TimeoutExpired):wait_checker(process,0,threading.Event())


class Stream:
    def __init__(self):self.closed=threading.Event()
    def __iter__(self):
        while not self.closed.wait(.01):pass
        return
        yield
    def close(self):self.closed.set()


class Probe:
    info={'MemTotal':16*1024**3}
    def __init__(self):self.api=SimpleNamespace(events=lambda **kw:Stream());self.cleaned=[]
    def conflicts(self,hashes):return []
    def cleanup(self,hashes):self.cleaned.append(hashes)
    def inventory(self):return [],[]
    def sample(self,instances):return {'monotonic':time.monotonic(),'checker_processes':0,'fully_started_labs':0}


def options(**kw):
    return SimpleNamespace(**({'timeout':2,'sample_interval':.01,'memory_fraction':.85,'max_infra_errors':2,'start_barrier':True}|kw))


def test_pool_limits_functional_failures_and_integrity(originals,tmp_path,monkeypatch):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe()
    lock=threading.Lock();active=0;peak=0
    def checker(config,run,correction,stop_event,process_callback=None):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active)
        time.sleep(.04)
        with lock:active-=1
        return {'task_success':False,'checks_passed':0,'checks_failed':1,'checks_total':1}
    monkeypatch.setattr(stress,'run_checker',checker)
    before=tree_hash(originals/'runs')
    summary,rows,_=stress.run_level(sources,tmp_path/'batch',3,options(),probe)
    assert summary['completed']==15 and summary['infrastructure_failures']==0
    assert summary['functional_passes']==0 and peak==3
    assert len(probe.cleaned)==1 and len(rows)==15
    assert tree_hash(originals/'runs')==before


def test_repeated_errors_stop_new_work_and_cleanup(originals,tmp_path,monkeypatch):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe()
    def checker(*a,**kw):raise RuntimeError('Docker failed')
    monkeypatch.setattr(stress,'run_checker',checker)
    summary,rows,_=stress.run_level(sources,tmp_path/'failed',2,options(),probe)
    assert summary['stopped'] and probe.cleaned
    assert len(rows)==15 and any(r['checker_status']=='NOT_STARTED' for r in rows)


def test_no_checker_launched_on_collision(originals,tmp_path,monkeypatch):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe()
    probe.conflicts=lambda hashes:['foreign_collision']
    checker=Mock();monkeypatch.setattr(stress,'run_checker',checker)
    with pytest.raises(RuntimeError,match='Namespace collision'):
        stress.run_level(sources,tmp_path/'collision',15,options(),probe)
    checker.assert_not_called()


def test_critical_pressure_prevents_all_launches(originals,tmp_path,monkeypatch):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe()
    probe.sample=lambda instances:{'monotonic':time.monotonic(),'host_pressure_critical':True}
    checker=Mock();monkeypatch.setattr(stress,'run_checker',checker)
    summary,rows,_=stress.run_level(sources,tmp_path/'pressure',15,options(),probe)
    checker.assert_not_called()
    assert summary['stopped'] and all(r['checker_status']=='NOT_STARTED' for r in rows)
    assert probe.cleaned


def test_oom_event_stops_launches(originals,tmp_path,monkeypatch):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe()
    # Match a planned stress hash only; external OOM events are ignored.
    def events(**kw):
        h=probe.planned[0]
        return SimpleStream([{'Action':'oom','Actor':{'Attributes':{'lab_hash':h}}}])
    def conflicts(hashes):probe.planned=list(hashes);return []
    probe.conflicts=conflicts;probe.api.events=events
    checker=Mock();monkeypatch.setattr(stress,'run_checker',checker)
    summary,_,_=stress.run_level(sources,tmp_path/'oom',15,options(),probe)
    assert summary['stopped'] and any('OOM confermato' in r for r in summary['stop_reasons'])
    assert probe.cleaned


class SimpleStream:
    def __init__(self,rows):self.rows=rows;self.closed=threading.Event()
    def __iter__(self):
        yield from self.rows
        self.closed.wait(3)
    def close(self):self.closed.set()


def test_keyboard_interrupt_cancels_workers_and_cleans(originals,tmp_path,monkeypatch):
    sources,_=stress.select_sources(originals,'thesis_final',15);probe=Probe()
    def checker(*a,stop_event,**kw):
        assert stop_event.wait(2)
        raise CheckerCancelled('cancelled')
    monkeypatch.setattr(stress,'run_checker',checker)
    monkeypatch.setattr(stress,'wait',Mock(side_effect=KeyboardInterrupt))
    summary,_,_=stress.run_level(sources,tmp_path/'interrupt',2,options(),probe)
    assert summary['stopped'] and probe.cleaned


def test_metrics_and_no_unsupported_optimum():
    rows=[{'checker_status':'COMPLETED','total_seconds':10,'task_success':False}]*15
    samples=[{'monotonic':0,'fully_started_labs':15,'checker_processes':15,'containers':360},
             {'monotonic':15,'fully_started_labs':15,'checker_processes':15,'containers':360}]
    s=stress.summarize(rows,samples,60,15)
    assert s['throughput_labs_per_minute']==15 and s['max_containers']==360
    assert s['sampled_seconds_at_target']==15 and s['functional_passes']==0


def test_default_dry_run_no_aut_checker_or_writes_to_original(originals,tmp_path,monkeypatch):
    checker=Mock(side_effect=AssertionError('No checker in dry run'))
    monkeypatch.setattr(stress,'run_checker',checker)
    before=tree_hash(originals/'runs')
    general=originals/'results/general/thesis_final'
    general.mkdir(parents=True);(general/'runs.csv').write_text('original report')
    output=tmp_path/'report'
    assert cli.main(['--output-dir',str(output)],root=originals,probe_factory=Probe)==0
    checker.assert_not_called()
    assert tree_hash(originals/'runs')==before
    assert (general/'runs.csv').read_text()=='original report'
    assert len(json.loads((output/'selection.json').read_text())['sources'])==15
    assert json.loads((output/'summary.json').read_text())['recommended_optimum_workers'] is None
    for name in ['summary.json','laboratories.csv','measurements.csv','docker_events.log','stress_test.log','report.md']:
        assert (output/name).exists()


def test_protected_output_paths_rejected(tmp_path):
    for name in ['runs/probe','results/general/thesis_final','scenarios/lab_01','results']:
        with pytest.raises(ValueError):cli.safe_output(tmp_path/name,tmp_path)
