"""End-to-end supervision using synthetic data and fake agents/checkers only."""
from pathlib import Path
import json

from test_assignment_integration import synthetic, write_checker_reports
from benchmark_core.config import load_config
from benchmark_core.scenario_loader import discover_scenarios
from benchmark_core.task_catalog import TaskAssignment
from benchmark_core import pipeline, standard_runtime as rt, standard_auth


def test_fork_auth_failure_fresh_codex_restart_and_scientific_resume(synthetic,monkeypatch):
    root,config_path,_=synthetic
    config=load_config(config_path)
    config.data['resilience']={'heartbeat_seconds':.05,'backoff_seconds':0,'auth_wait_seconds':0}
    scenario=discover_scenarios(root/'scenarios')['lab_03']
    calls=root/'calls.json'
    def aut(config,scenario,run,agent,prompt,**kw):
        n=json.loads(calls.read_text()) if calls.exists() else 0
        calls.write_text(json.dumps(n+1))
        (run/'logs/aut/events.jsonl').write_text('{"type":"turn.completed","usage":{"input_tokens":7}}\n')
        if n==0: raise RuntimeError('AUTH_FAILED: expired session')
        (run/'lab/generated.txt').write_text('generated')
    outcome={'checks_passed':1,'checks_failed':0,'checks_total':1,'check_pass_rate':1.0,'task_success':True}
    monkeypatch.setattr(pipeline,'run_aut',aut)
    monkeypatch.setattr(pipeline,'run_checker',lambda c,r,o:write_checker_reports(r,outcome))
    monkeypatch.setattr(pipeline,'component_versions',lambda:{})
    monkeypatch.setattr(standard_auth,'refresh_account',lambda:True)
    kw=dict(skill_mode='no_skill',experiment_id='synthetic',replicate=1,assignment=TaskAssignment('lab_03','aurora','large'))
    result=rt.run_supervised(config,scenario,'codex','T1',**kw)
    assert json.loads(calls.read_text())==2
    assert rt.load(result/'manifest.json')['pipeline_state']=='COMPLETED'
    assert rt.run_supervised(config,scenario,'codex','T1',**kw)==result
    assert json.loads(calls.read_text())==2
    assert len(list(result.parent.glob('r*/manifest.json')))==2
    assert (result/'logs/aut/events.jsonl').read_text().find('"input_tokens":7')>=0


def test_finalizing_resume_runs_checker_only(synthetic,monkeypatch):
    root,config_path,_=synthetic; config=load_config(config_path)
    config.data['resilience']={'heartbeat_seconds':.05,'backoff_seconds':0}
    scenario=discover_scenarios(root/'scenarios')['lab_03']
    outcome={'checks_passed':1,'checks_failed':0,'checks_total':1,'check_pass_rate':1.0,'task_success':True}
    assignment=TaskAssignment('lab_03','aurora','large')
    monkeypatch.setattr(pipeline,'run_aut',lambda *a,**k:None)
    monkeypatch.setattr(pipeline,'run_checker',lambda c,r,o:write_checker_reports(r,outcome))
    run=pipeline.run_one(config,scenario,'codex','T1',skill_mode='no_skill',experiment_id='synthetic',replicate=1,assignment=assignment)
    m=rt.load(run/'manifest.json');m['pipeline_state']='FINALIZING';rt.atomic_json(run/'manifest.json',m)
    (run/'evaluation/metrics.json').unlink()
    def forbidden(*a,**k): raise AssertionError('must not call Codex')
    monkeypatch.setattr(pipeline,'run_aut',forbidden)
    result=rt.run_supervised(config,scenario,'codex','T1',skill_mode='no_skill',experiment_id='synthetic',replicate=1,assignment=assignment,resume_run=run)
    assert result==run and rt.load(run/'manifest.json')['pipeline_state']=='COMPLETED'
    assert len(list(run.parent.glob('r*')))==1
