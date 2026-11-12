"""Result destinations and benchmark isolation, using synthetic runs only."""
import hashlib
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from benchmark_core.config import Config,load_config
from benchmark_core.report_paths import (general_root,general_legacy,general_experiment,
    cost266_experiment,cost266_comparison,publish_cost266_report,validate_cost266_report_destination)
from benchmark_core.aggregation import aggregate
from test_scientific_safety import observation
from test_assignment_integration import synthetic,write_checker_reports
from test_cost266_selection import selection,arguments
from test_cost266_continuous import v2
from test_cost266 import case
from scripts import run_cost266,run_experiment,run_benchmark,aggregate_results,compare_cost266,aggregate_cost266_results,analyze_results


def snapshot(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


def test_shared_paths_and_configured_root(tmp_path):
    config=Config(tmp_path,{'results':{'directory':'custom-results'}})
    assert general_root(config)==tmp_path/'custom-results/general'
    assert general_legacy(config)==tmp_path/'custom-results/general/_legacy'
    assert general_experiment(config,'thesis_final')==tmp_path/'custom-results/general/thesis_final'
    assert cost266_experiment(config,'custom_v1')==tmp_path/'custom-results/cost266/experiments/custom_v1'
    assert cost266_comparison(config,'cmp_01')==tmp_path/'custom-results/cost266/comparisons/cmp_01'
    for name in ('../unsafe','nested/path','',None):
        with pytest.raises(ValueError):cost266_experiment(config,name)
    with pytest.raises(ValueError,match='riservato'):general_experiment(config,'_legacy')


def test_general_cli_and_explicit_report_output(synthetic,monkeypatch):
    root,config_path,experiment=synthetic
    monkeypatch.setattr(run_experiment,'preflight',lambda *a,**k:None)
    monkeypatch.setattr(run_experiment,'_notify_benchmark_finished',lambda:None)
    monkeypatch.setattr('benchmark_core.pipeline.component_versions',lambda:{})
    def fake_aut(config,scenario,run,agent,prompt,**kwargs):
        (run/'lab/agent.txt').write_text('synthetic')
    outcome={'checks_passed':1,'checks_failed':0,'checks_total':1,'check_pass_rate':1.0,'task_success':True}
    monkeypatch.setattr('benchmark_core.pipeline.run_aut',fake_aut)
    monkeypatch.setattr('benchmark_core.pipeline.run_checker',lambda config,run,correction:write_checker_reports(run,outcome))
    args=[str(experiment),'--config',str(config_path),'--lab','lab_03','--dns-tree','aurora',
          '--task-level','large','--prompt-type','T1','--skill-mode','no_skill']
    assert run_experiment.main([*args,'--only-replicate','1'])==0
    report=root/'results/general/synthetic'
    assert (report/'runs.csv').is_file() and (report/'benchmark.xlsx').is_file()
    custom=root/'explicit-report'
    assert run_experiment.main([*args,'--only-replicate','2','--report-output',str(custom)])==0
    assert (custom/'runs.csv').is_file() and len(pd.read_csv(custom/'runs.csv'))==2
    assert len(pd.read_csv(report/'runs.csv'))==1


def test_legacy_and_analyze_explicit_destination(synthetic,monkeypatch):
    root,config_path,_=synthetic;captured=[]
    monkeypatch.setattr(run_benchmark,'validate_report_destination',lambda p:captured.append(p))
    monkeypatch.setattr(run_benchmark,'verify_skills',lambda config:{})
    monkeypatch.setattr(sys,'argv',['run_benchmark.py','--config',str(config_path),'--check-skills'])
    assert run_benchmark.main()==0 and captured==[root/'results/general/_legacy']
    monkeypatch.setattr(analyze_results,'analyze',lambda p:(captured.append(p) or pd.DataFrame()))
    explicit=root/'custom-analysis'
    monkeypatch.setattr(sys,'argv',['analyze_results.py','--config',str(config_path),'--results',str(explicit)])
    assert analyze_results.main() is None and captured[-1]==explicit


def test_default_cost_reports_comparison_and_regeneration(selection,monkeypatch):
    root=selection.root
    old=root/'results/test_continuous';old.mkdir(parents=True);(old/'runs.csv').write_text('historical')
    assert run_cost266.main(arguments('one_shot'))==0
    assert run_cost266.main(arguments('incremental_continuous'))==0
    assert run_cost266.main(arguments('incremental_isolated'))==0
    report=root/'results/cost266/experiments/test_continuous'
    assert (report/'runs.csv').is_file() and len(pd.read_csv(report/'runs.csv'))==2
    assert (root/'results/cost266/experiments/test_isolated/benchmark.xlsx').is_file()
    before=snapshot(root/'runs');assert (old/'runs.csv').read_text()=='historical'
    monkeypatch.setattr(aggregate_cost266_results,'load_config',lambda p:selection.config)
    assert aggregate_cost266_results.main(['--experiment','test_continuous'])==0
    explicit_cost=root/'cost-explicit/test_continuous'
    assert aggregate_cost266_results.main(['--experiment','test_continuous','--output',str(explicit_cost)])==0
    assert (explicit_cost/'runs.csv').is_file()
    monkeypatch.chdir(root)
    assert aggregate_cost266_results.main(['--experiment','test_continuous','--output','runs/test_continuous'])==1
    assert aggregate_cost266_results.main(['--experiment','test_continuous','--output','results/../runs/test_continuous'])==1
    assert snapshot(root/'runs')==before
    assert snapshot(root/'runs')==before and (old/'runs.csv').read_text()=='historical'
    monkeypatch.setattr(compare_cost266,'load_config',lambda p:selection.config)
    assert compare_cost266.main(['--root',str(root),'--comparison-id','test'])==0
    output=root/'results/cost266/comparisons/test'
    assert (output/'benchmark_comparison.xlsx').is_file() and (output/'comparison_manifest.json').is_file()
    assert compare_cost266.main(['--root',str(root),'--comparison-id','test'])==1
    explicit=root/'other-comparison'
    assert compare_cost266.main(['--root',str(root),'--output',str(explicit)])==0
    assert (explicit/'observations.csv').is_file() and snapshot(root/'runs')==before
    assert compare_cost266.main(['--root',str(root),'--output','results/../runs/forbidden'])==1
    assert snapshot(root/'runs')==before


def test_cost_report_rejects_unmanaged_and_altered_files_before_aut(selection):
    root=selection.root;output=cost266_experiment(selection.config,'test_continuous')
    output.mkdir(parents=True);(output/'runs.csv').write_text('unmanaged')
    assert run_cost266.main(arguments('one_shot'))==1
    assert not selection.calls and (output/'runs.csv').read_text()=='unmanaged'
    (output/'runs.csv').unlink()
    assert run_cost266.main(arguments('one_shot'))==0
    (output/'summary.csv').write_text('manually edited')
    before=snapshot(root/'runs');calls=len(selection.calls)
    assert run_cost266.main(arguments('incremental_continuous'))==1
    assert snapshot(root/'runs')==before and len(selection.calls)==calls
    assert (output/'summary.csv').read_text()=='manually edited'


def test_occupied_parent_is_rejected_before_cost_aut(selection):
    path=selection.root/'results/cost266'
    path.parent.mkdir(parents=True);path.write_text('unmanaged')
    assert run_cost266.main(arguments('one_shot'))==1
    assert not selection.calls and path.read_text()=='unmanaged'


def test_managed_report_from_another_experiment_is_not_adopted(selection):
    assert run_cost266.main(arguments('one_shot'))==0
    base=selection.root/'results/cost266/experiments'
    source=base/'test_continuous';target=base/'test_isolated'
    shutil.copytree(source,target)
    before=snapshot(target);calls=len(selection.calls)
    assert run_cost266.main(arguments('incremental_isolated'))==1
    assert len(selection.calls)==calls and snapshot(target)==before


def test_cost_report_rechecked_before_every_cell(selection,monkeypatch):
    original=run_cost266.publish_cost266_report
    def publish_then_edit(root,output):
        result=original(root,output)
        (output/'runs.csv').write_text('edited between cells')
        return result
    monkeypatch.setattr(run_cost266,'publish_cost266_report',publish_then_edit)
    args=['--execution-mode','one_shot','--skill-mode','no_skill','--only-replicate','1']
    assert run_cost266.main(args)==1
    assert len(selection.calls)==1
    assert (selection.root/'results/cost266/experiments/test_continuous/runs.csv').read_text()=='edited between cells'


def test_general_multiple_experiments_and_schema_separation(synthetic,monkeypatch):
    root,config_path,_=synthetic;runs=root/'runs'
    first=observation(runs,'r001')
    disguised=observation(runs,'r002',replicate=2)
    data=json.loads((disguised/'manifest.json').read_text());data['schema']='cost266_v1'
    (disguised/'manifest.json').write_text(json.dumps(data))
    other=runs/'other'/first.relative_to(runs/'exp');shutil.copytree(first,other)
    for file in ('manifest.json','evaluation/metrics.json'):
        path=other/file;data=json.loads(path.read_text());data['experiment_id']='other';path.write_text(json.dumps(data))
    before=snapshot(runs)
    monkeypatch.setattr(sys,'argv',['aggregate_results.py','--config',str(config_path)])
    assert aggregate_results.main()==0
    for experiment in ('exp','other'):
        output=root/'results/general'/experiment
        frame=pd.read_csv(output/'runs.csv');summary=pd.read_csv(output/'summary.csv')
        assert len(frame)==1 and summary.evaluated_runs.sum()==1
        assert (output/'benchmark.xlsx').is_file()
    assert snapshot(runs)==before
    explicit=root/'explicit-output'
    monkeypatch.setattr(sys,'argv',['aggregate_results.py','--config',str(config_path),'--experiment','exp','--output',str(explicit)])
    assert aggregate_results.main()==0 and len(pd.read_csv(explicit/'runs.csv'))==1


def test_default_regeneration_separates_legacy_and_general(synthetic,monkeypatch):
    root,config_path,_=synthetic;runs=root/'runs'
    source=observation(runs,'r001')
    legacy=runs/'lab_01/T1/no_skill/r001';legacy.parent.mkdir(parents=True)
    shutil.copytree(source,legacy)
    before=snapshot(runs)
    monkeypatch.setattr(sys,'argv',['aggregate_results.py','--config',str(config_path)])
    assert aggregate_results.main()==0
    assert len(pd.read_csv(root/'results/general/exp/runs.csv'))==1
    assert len(pd.read_csv(root/'results/general/_legacy/runs.csv'))==1
    assert snapshot(runs)==before


def test_default_discovery_ignores_cost_schema_even_with_general_layout(synthetic,monkeypatch):
    root,config_path,_=synthetic;runs=root/'runs'
    run=observation(runs,'r001')
    path=run/'manifest.json';data=json.loads(path.read_text());data['schema']='cost266_v1';path.write_text(json.dumps(data))
    monkeypatch.setattr(sys,'argv',['aggregate_results.py','--config',str(config_path)])
    with pytest.raises(SystemExit):aggregate_results.main()
    assert not (root/'results/general/exp').exists()


@pytest.mark.parametrize('change',[{'schema':'cost266_v1'},{'schema':'cost266_v2'},
                                   {'task_level':'cost266'},
                                   {'conditions':{'protocol':'cost266_incremental_no_feedback_v1'}}])
def test_general_aggregator_skips_cost_metrics_before_parsing(tmp_path,change):
    runs=tmp_path/'runs';observation(runs,'r001')
    disguised=observation(runs,'r002',replicate=2)
    manifest=disguised/'manifest.json';data=json.loads(manifest.read_text());data.update(change)
    manifest.write_text(json.dumps(data));(disguised/'evaluation/metrics.json').write_text('{')
    rows,_,summary=aggregate(runs,tmp_path/'output',experiment_id='exp')
    assert len(rows)==1 and summary.evaluated_runs.sum()==1


def test_mixed_realistic_general_and_cost_runs_stay_separate(selection):
    root=selection.root
    observation(root/'runs','r001')
    assert run_cost266.main(arguments('one_shot'))==0
    before=snapshot(root/'runs')
    general,_,summary=aggregate(root/'runs',root/'results/general/exp',experiment_id='exp')
    cost=pd.read_csv(root/'results/cost266/experiments/test_continuous/runs.csv')
    assert len(general)==len(cost)==1 and summary.evaluated_runs.sum()==1
    assert set(general['experiment_id'])=={'exp'} and set(cost['experiment_id'])=={'test_continuous'}
    assert snapshot(root/'runs')==before
