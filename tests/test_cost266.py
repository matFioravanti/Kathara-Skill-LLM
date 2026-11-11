"""Protocollo COST266: backend simulati, nessun container o modello a consumo."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import csv
import json
import subprocess

import pytest
import yaml

from benchmark_core.config import Config
from benchmark_core.cost266 import assets, protocol, runner
from benchmark_core.cost266.protocol import Cell, Spec, VERSION, cells, digest, fingerprint, load_spec, prompts
from benchmark_core.cost266.reports import aggregate_cost266
from benchmark_core.workspace import tree_hash, write_json


@pytest.fixture
def case(tmp_path, monkeypatch):
    dataset = tmp_path/'experiments/data'; lab = dataset/'lab'; lab.mkdir(parents=True)
    roles = [{'device':name,'address':f'192.0.2.{10+i}','role':name}
             for i,name in enumerate(('root','tld','country','city','subzone','resolver','client'))]
    conf = ''
    for role in roles:
        name = role['device']; conf += f'{name}[0]="A"\n{name}[image]="kathara/base"\n'
        (lab/f'{name}.startup').write_text(f"#!/bin/sh\nip -4 addr replace {role['address']}/24 dev eth0\n")
    (lab/'lab.conf').write_text(conf)
    zones=[]
    for i,(name,parent) in enumerate((('.',None),('test.','.'),('zz.test.','test.'),
                                     ('city.zz.test.','zz.test.'),('admin.city.zz.test.','city.zz.test.'))):
        zones.append({'name':name,'parent':parent,'stage':i+1,'device':roles[i]['device'],
                      'address':roles[i]['address'],'ns':'a.root-servers.' if i==0 else 'ns1.'+name,
                      'records':[{'name':'www.'+name,'type':'A','value':roles[i]['address']}] if i==3 else []})
    inventory={'schema':1,'synthetic':True,'zones':zones,'resolvers':[roles[5]],
               'clients':[{**roles[6],'resolver':roles[5]['address']}],'queries':zones[3]['records']}
    oracle={'lab_inline':conf,'convergence_time':1,'default_image':'kathara/base','test':{'requiring_startup':['client']}}
    (dataset/'correction.yaml').write_text(yaml.safe_dump(oracle))
    preparation={'baseline_sha256':tree_hash(lab),'correction_sha256':digest((dataset/'correction.yaml').read_bytes()),
                 'inventory_sha256':fingerprint(inventory)}
    spec=Spec('test_cost266',dataset,('one_shot','incremental'),('T1',),('no_skill',),1,100,1000,100,tmp_path/'experiment.yaml')
    config=Config(tmp_path,{'benchmark':{'timeout_seconds':10,'continue_on_error':True,'repetitions':1},
        'aut':{'agent':'codex','version':'test','model':'fixed','reasoning_effort':'low','skill_protocol':'explicit_read_v2'},
        'sandbox':{'image':'unchanged'},'checker':{'no_cache':True,'report_type':'csv'},'results':{'directory':'results'},
        'docker_sandbox':{'execution_backend':'docker_sandbox'}})
    monkeypatch.setattr(runner,'component_versions',lambda:{'checker':'test'})
    monkeypatch.setattr(runner,'_revision',lambda root:'revision-test')
    return SimpleNamespace(root=tmp_path,dataset=dataset,inventory=inventory,preparation=preparation,spec=spec,config=config,calls=[])


def fake_aut(case, fail_at=None):
    def aut(config,scenario,run,agent,prompt,skill_mode,run_id):
        index = int(run.parents[1].name)
        case.calls.append({'stage':index,'lab':tree_hash(run/'lab'),'files':{str(p.relative_to(run/'lab')):p.read_bytes()
                           for p in (run/'lab').rglob('*') if p.is_file()},'prompt':prompt,'run_id':run_id,
                           'timeout':config.data['benchmark']['timeout_seconds'],'run':run})
        logs=run/'logs/aut'
        (logs/'prompt_sent.md').write_text(prompt)
        events=[{'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':5,'reasoning_output_tokens':2,'cached_input_tokens':3}}]
        (logs/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
        (logs/(run_id+'.eval')).write_bytes(b'inspect-test-fixture')
        write_json(logs/'result.json',{'duration_seconds':2,'returncode':0,'timed_out':False})
        write_json(logs/'sandbox_metadata.json',{'sandbox_name':run_id,'cleanup_ok':True})
        if fail_at==index:
            (run/'lab/root/etc/bind').mkdir(parents=True,exist_ok=True)
            (run/'lab/root/etc/bind/partial').write_text('failure must not be forwarded')
            raise TimeoutError('simulated stage failure')
        metadata=json.loads((run/'manifest.json').read_text())
        for z in case.inventory['zones']:
            if metadata['strategy']=='one_shot' or z['stage']==index:
                directory=run/'lab'/z['device']/'etc/bind'; directory.mkdir(parents=True,exist_ok=True)
                (directory/'named.conf').write_text(f'zone "{z["name"]}" {{ type master; }};\n')
    return aut


def fake_checker(success=True):
    def checker(config,run,correction):
        assert not (run/'lab/correction.yaml').exists()
        results=run/'results'; (results/'lab').mkdir(parents=True,exist_ok=True)
        rows=[{'Test Description':'Checking correctness of DNS records','Passed':str(success),'Reason':'' if success else 'test failure'}]
        def write(path,columns,values):
            with path.open('w',newline='') as file:
                writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader();writer.writerows(values)
        write(results/'results.csv',['Student Name','Tests Passed','Tests Failed','Tests Total Number','Problems'],
              [{'Student Name':'lab','Tests Passed':int(success),'Tests Failed':int(not success),'Tests Total Number':1,'Problems':''}])
        write(results/'lab/lab_result_all.csv',['Test Description','Passed','Reason'],rows)
        write(results/'lab/lab_result_failed.csv',['Test Description','Passed','Reason'],[] if success else rows)
        write(results/'lab/lab_result_summary.csv',['Total Tests','Passed Tests','Failed'],
              [{'Total Tests':1,'Passed Tests':int(success),'Failed':int(not success)}])
        return {'checks_passed':int(success),'checks_failed':int(not success),'checks_total':1,'check_pass_rate':float(success),'task_success':success}
    return checker


def execute(case,monkeypatch,strategy='incremental',**kwargs):
    monkeypatch.setattr(runner,'run_aut',fake_aut(case,kwargs.pop('fail_at',None)))
    monkeypatch.setattr(runner,'run_checker',fake_checker(kwargs.pop('success',True)))
    cell=Cell(case.spec.experiment_id,'T1',strategy,'no_skill',1)
    return runner.execute(case.config,case.spec,cell,case.inventory,case.preparation,**kwargs)


def test_identity_separate_from_legacy_catalog():
    from benchmark_core.task_catalog import TaskAssignment, LAB_LEVELS, TASK_LEVELS, DNS_TREES
    assert 'cost266' not in TASK_LEVELS and 'cost266' not in LAB_LEVELS and 'multitld_v2' not in DNS_TREES
    with pytest.raises(ValueError):TaskAssignment('cost266','multitld_v2','cost266')
    with pytest.raises(ValueError):Cell('unsafe/exp','T1','incremental','no_skill',1)
    with pytest.raises(ValueError):Cell('safe','T1','incremental','no_skill',1,scenario='lab_01')
    a=Cell('safe','T1','one_shot','no_skill',1);b=replace(a,strategy='incremental')
    assert a.relative!=b.relative and a.run_id!=b.run_id


@pytest.mark.parametrize('key,value',[('strategies',['incremental','incremental']),('prompt_types',['T7']),
    ('skill_modes',['WITHOUT_SKILL']),('repetitions',True),('protocol','incremental_with_feedback')])
def test_spec_validation(case,key,value):
    data={'experiment':{'id':'test'},'dataset':'experiments/data','protocol':VERSION,'strategies':['one_shot','incremental'],
          'prompt_types':['T1'],'skill_modes':['no_skill'],'repetitions':1,
          'budgets':{'stage_seconds':10,'total_seconds':100,'checker_seconds':10}}
    path=case.root/'spec.yaml';path.write_text(yaml.safe_dump(data))
    assert len(list(cells(load_spec(path,case.root))))==2
    data[key]=value;path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):load_spec(path,case.root)


@pytest.mark.parametrize('prompt_type',protocol.PROMPT_TYPES)
def test_prompts_equivalent_and_no_correction(case,prompt_type):
    requirements=protocol.stage_requirements(case.inventory)
    one=prompts(case.inventory,Cell('test',prompt_type,'one_shot','no_skill',1))
    inc=prompts(case.inventory,Cell('test',prompt_type,'incremental','no_skill',1))
    assert len(one)==1 and len(inc)==6
    assert one[0]==protocol.render(sum(requirements,[]),prompt_type)
    assert all(p==protocol.render(r,prompt_type) for p,r in zip(inc,requirements))
    assert all('correction' not in p and 'feedback' not in p for p in one+inc)
    assert not any(r.get('request')=='client_resolver_and_resolution' for r in requirements[0])


def test_exact_calls_isolation_common_oracle_and_aggregate(case,monkeypatch):
    one=execute(case,monkeypatch,'one_shot');inc=execute(case,monkeypatch)
    assert len(case.calls)==7
    assert len({c['run_id'] for c in case.calls})==7
    assert case.calls[0]['lab']==case.calls[1]['lab']==case.preparation['baseline_sha256']
    assert (one/'evaluation/correction.yaml').read_bytes()==(inc/'evaluation/correction.yaml').read_bytes()
    for index,call in enumerate(case.calls[1:]):
        expected=inc/'input/lab' if index==0 else inc/'steps'/f'{index:02d}'/'checkpoint'
        assert call['lab']==tree_hash(expected)
        assert not any('correction' in f or 'logs/' in f or '.codex' in f or '.eval' in f for f in call['files'])
    metrics=json.loads((inc/'evaluation/metrics.json').read_text())
    assert metrics['aut_calls']==6 and metrics['sandbox_count']==6 and metrics['completed_stages']==6
    assert metrics['tokens']['input']==60 and metrics['tokens']['output']==30
    assert metrics['tokens']['reasoning']==12 and metrics['tokens']['total']==90
    assert metrics['timing']['agent_seconds']==12 and metrics['final_pass_rate']==1
    frames=aggregate_cost266(case.root,case.root/'results/test_cost266')
    assert len(frames[0])==2 and set(frames[0]['strategy'])=={'one_shot','incremental'}
    assert len(frames[2])==2
    import pandas as pd
    pairs=pd.read_csv(case.root/'results/test_cost266/pairs.csv')
    assert len(pairs)==1 and pairs['comparable_evaluated_pair'].iloc[0]
    from openpyxl import load_workbook
    book=load_workbook(case.root/'results/test_cost266/benchmark.xlsx',read_only=True)
    assert book.sheetnames==['Runs','Checks','Summary','Stages','Pairs'];book.close()
    # L'aggregatore storico non vede i checkpoint e non deduplica le strategie.
    from benchmark_core.aggregation import aggregate
    legacy,_,_=aggregate(case.root/'runs',case.root/'legacy_results')
    assert len(legacy)==0


def test_resume_failure_does_not_replay_valid_stages_or_propagate_partial(case,monkeypatch):
    run=execute(case,monkeypatch,fail_at=3)
    assert len(case.calls)==3
    metadata=json.loads((run/'manifest.json').read_text())
    assert metadata['pipeline_state']=='INCOMPLETE' and metadata['task_success'] is None
    assert tree_hash(run/'lab')==tree_hash(run/'steps/02/checkpoint')
    metrics=json.loads((run/'evaluation/metrics.json').read_text())
    assert metrics['completed_stages']==2 and metrics['aut_calls']==3 and metrics['final_pass_rate'] is None
    assert metrics['checker']['total'] is None
    preserved=(run/'steps/03/attempts/001/logs/aut/events.jsonl').read_bytes()
    execute(case,monkeypatch,resume=True)
    assert [c['stage'] for c in case.calls]==[1,2,3,3,4,5,6]
    assert not any('partial' in f for f in case.calls[3]['files'])
    assert (run/'steps/03/attempts/001/logs/aut/events.jsonl').read_bytes()==preserved
    metrics=json.loads((run/'evaluation/metrics.json').read_text())
    assert metrics['aut_calls']==7 and metrics['tokens']['input']==70
    execute(case,monkeypatch,resume=True)
    assert len(case.calls)==7


@pytest.mark.parametrize('artifact',['input/lab/lab.conf','evaluation/correction.yaml','steps/01/checkpoint/lab.conf',
                                    'steps/01/attempts/001/logs/aut/prompt_sent.md'])
def test_resume_rejects_tampering(case,monkeypatch,artifact):
    run=execute(case,monkeypatch)
    with (run/artifact).open('a') as file:file.write('tampered')
    with pytest.raises(ValueError):execute(case,monkeypatch,resume=True)
    assert len(case.calls)==6


def test_resume_rejects_model_or_budget_change(case,monkeypatch):
    execute(case,monkeypatch)
    case.config.data['aut']['model']='other'
    with pytest.raises(ValueError,match='Condizioni'):execute(case,monkeypatch,resume=True)


def test_failed_attempt_artifacts_are_immutable(case,monkeypatch):
    run=execute(case,monkeypatch,fail_at=2)
    (run/'steps/02/attempts/001/logs/aut/events.jsonl').write_text('altered')
    with pytest.raises(ValueError,match='Artefatti tentativo'):execute(case,monkeypatch,resume=True)


def test_missing_eval_cannot_complete_stage(case,monkeypatch):
    original=fake_aut(case)
    def without_eval(*args,**kwargs):
        original(*args,**kwargs)
        for path in (args[2]/'logs/aut').glob('*.eval'):path.unlink()
    monkeypatch.setattr(runner,'run_aut',without_eval)
    run=runner.execute(case.config,case.spec,Cell(case.spec.experiment_id,'T1','incremental','no_skill',1),case.inventory,case.preparation)
    metadata=json.loads((run/'manifest.json').read_text())
    assert metadata['pipeline_state']=='INCOMPLETE' and '.eval mancante' in metadata['pipeline_error']
    assert not (run/'steps/01/completed.json').exists()


def test_dns_property_coverage_uses_only_checker_rows(case,monkeypatch):
    coverage={'checks':[{'device':'client','command':'dig fixture','kind':'delegation_glue','name':'test.'}]}
    write_json(case.dataset/'oracle_coverage.json',coverage)
    run=execute(case,monkeypatch)
    assert (run/'evaluation/oracle_coverage.json').read_bytes()==(case.dataset/'oracle_coverage.json').read_bytes()
    metrics=json.loads((run/'evaluation/metrics.json').read_text())
    property_metrics=metrics['dns_property_checks']['delegation_glue']
    assert property_metrics['expected']==1 and property_metrics['observed']==0
    assert property_metrics['pass_rate'] is None and property_metrics['coverage_complete'] is False
    (run/'evaluation/oracle_coverage.json').write_text('altered')
    with pytest.raises(ValueError,match='copertura'):execute(case,monkeypatch,resume=True)


def test_duplicate_and_noncontiguous_checkpoints_rejected(case,monkeypatch):
    run=execute(case,monkeypatch)
    with pytest.raises(ValueError,match='già presente'):execute(case,monkeypatch)
    (run/'steps/02/completed.json').unlink()
    with pytest.raises(ValueError,match='Checkpoint'):execute(case,monkeypatch,resume=True)


def test_checker_failure_not_success_and_rerun_without_aut(case,monkeypatch):
    run=execute(case,monkeypatch,success=False)
    assert json.loads((run/'manifest.json').read_text())['task_success'] is False
    execute(case,monkeypatch,resume=True)
    assert len(case.calls)==6
    execute(case,monkeypatch,rerun=True)
    assert len(case.calls)==6
    metadata=json.loads((run/'manifest.json').read_text())
    assert metadata['evaluation_revision']==1 and metadata['task_success'] is True
    assert (run/'evaluation/history/revision_000/metrics.json').exists()
    assert json.loads((run/'evaluation/metrics.json').read_text())['tokens']['input']==60


def test_final_checker_infrastructure_failure_resume_without_aut(case,monkeypatch):
    monkeypatch.setattr(runner,'run_aut',fake_aut(case))
    monkeypatch.setattr(runner,'run_checker',lambda *a: (_ for _ in ()).throw(RuntimeError('checker down')))
    cell=Cell(case.spec.experiment_id,'T1','incremental','no_skill',1)
    run=runner.execute(case.config,case.spec,cell,case.inventory,case.preparation)
    assert json.loads((run/'manifest.json').read_text())['pipeline_state']=='CHECKER_FAILED'
    execute(case,monkeypatch,resume=True)
    assert len(case.calls)==6


def test_backend_gate_single_call_contract(case):
    case.config.data['aut'].update(skill_protocol='enforced_read_v1',skill_gate_recovery_policy='recovery_v1')
    for mode in ('no_skill','auto'):protocol.validate_backend(case.config,mode)
    for mode in ('dns_only','creation_only','both_forced'):
        with pytest.raises(ValueError,match='più chiamate'):protocol.validate_backend(case.config,mode)
    case.config.data['docker_sandbox']['execution_backend']='unknown'
    with pytest.raises(ValueError,match='nessun fallback'):protocol.validate_backend(case.config,'no_skill')
    case.config.data['docker_sandbox']['execution_backend']='antigravity_cli'
    with pytest.raises(ValueError,match='nessun fallback'):protocol.validate_backend(case.config,'no_skill')


def test_total_timeout_without_false_checker_zeros(case,monkeypatch):
    spec=replace(case.spec,total_timeout=1)
    monkeypatch.setattr(runner,'run_aut',fake_aut(case))
    clock=[0]
    monkeypatch.setattr(runner.time,'monotonic',lambda:clock[0])
    aut=runner.run_aut
    def slow(*args,**kwargs):aut(*args,**kwargs);clock[0]=2
    monkeypatch.setattr(runner,'run_aut',slow)
    cell=Cell(spec.experiment_id,'T1','incremental','no_skill',1)
    run=runner.execute(case.config,spec,cell,case.inventory,case.preparation)
    metrics=json.loads((run/'evaluation/metrics.json').read_text())
    assert metrics['status']=='INCOMPLETE' and metrics['final_pass_rate'] is None and metrics['checker']['total'] is None


@pytest.mark.parametrize('change',['correction','symlink','routing'])
def test_lab_leaks_and_routing_changes_block_checkpoint(case,monkeypatch,change):
    original=fake_aut(case)
    def bad(*args,**kwargs):
        original(*args,**kwargs);lab=args[2]/'lab'
        if change=='correction':(lab/'correction.yaml').write_text('forbidden')
        elif change=='symlink':(lab/'leak').symlink_to(case.dataset/'correction.yaml')
        else:
            with (lab/'root.startup').open('a') as f:f.write('ip route add default via 192.0.2.1\n')
    monkeypatch.setattr(runner,'run_aut',bad)
    run=runner.execute(case.config,case.spec,Cell(case.spec.experiment_id,'T1','incremental','no_skill',1),case.inventory,case.preparation)
    assert json.loads((run/'manifest.json').read_text())['pipeline_state']=='INCOMPLETE'
    assert not (run/'steps/01/completed.json').exists()


def test_real_dispatch_reuses_gate_and_sandbox_each_stage(case,monkeypatch):
    from benchmark_core import inspect_runner, skill_gate, docker_sandbox_runner
    gate=[];sandboxes=[]
    original_gate=skill_gate.enforce_or_block
    def record_gate(*args,**kwargs):gate.append(args[1]);return original_gate(*args,**kwargs)
    monkeypatch.setattr(skill_gate,'enforce_or_block',record_gate)
    def sandbox(**kwargs):
        workspace=kwargs['workspace'];logs=kwargs['logs'];sandboxes.append((kwargs['sandbox_name'],str(workspace)))
        assert not (workspace/'correction.yaml').exists()
        assert (workspace/'.codex/skills').is_dir()
        (logs/'prompt_sent.md').write_text(kwargs['prompt'])
        (logs/'events.jsonl').write_text(json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':2}})+'\n')
        write_json(logs/'result.json',{'duration_seconds':1,'returncode':0})
        write_json(logs/'sandbox_metadata.json',{'sandbox_name':kwargs['sandbox_name'],'cleanup_ok':True})
    monkeypatch.setattr(docker_sandbox_runner,'run_codex_in_sandbox',sandbox)
    monkeypatch.setattr(inspect_runner,'run_codex',lambda **k:pytest.fail('host fallback'))
    monkeypatch.setattr(runner,'run_aut',inspect_runner.run_aut)
    monkeypatch.setattr(runner,'run_checker',fake_checker())
    run=runner.execute(case.config,case.spec,Cell(case.spec.experiment_id,'T1','incremental','no_skill',1),case.inventory,case.preparation)
    assert len(gate)==len(sandboxes)==6 and len({s[0] for s in sandboxes})==6
    assert len(list(run.glob('steps/*/attempts/*/logs/aut/*.eval')))==6


def test_real_sandbox_lifecycle_cleanup_on_stage_timeout(case,monkeypatch):
    from benchmark_core import inspect_runner, docker_sandbox_runner as sbx
    cleaned=[]
    monkeypatch.setattr(sbx,'sbx_executable',lambda:'/fixture/sbx')
    monkeypatch.setattr(sbx,'sbx_version',lambda:'0.48.0')
    monkeypatch.setattr(sbx,'sbx_get_sandbox_id',lambda name:'fixture-id')
    monkeypatch.setattr(sbx,'sbx_check_network_policy',lambda name:None)
    monkeypatch.setattr(sbx,'_sbx_rm',lambda name:(cleaned.append(name) or True,None))
    real_subprocess_run=subprocess.run
    def fake_process(command,**kwargs):
        if command[0]=='git':return real_subprocess_run(command,**kwargs)
        if command[1]=='create':return subprocess.CompletedProcess(command,0,'','')
        if command[-1]=='--version':return subprocess.CompletedProcess(command,0,'codex 0.165.0','')
        raise subprocess.TimeoutExpired(command,1,output='',stderr='fixture timeout')
    monkeypatch.setattr(sbx.subprocess,'run',fake_process)
    monkeypatch.setattr(inspect_runner,'run_codex',lambda **kwargs:pytest.fail('host fallback'))
    monkeypatch.setattr(runner,'run_aut',inspect_runner.run_aut)
    run=runner.execute(case.config,case.spec,Cell(case.spec.experiment_id,'T1','incremental','no_skill',1),case.inventory,case.preparation)
    assert len(cleaned)==1
    assert json.loads((run/'manifest.json').read_text())['pipeline_state']=='INCOMPLETE'
    assert len(list(run.glob('steps/*/attempts/*/logs/aut/*.eval')))==1
    assert not (run/'steps/01/completed.json').exists()


def test_real_assets_prepare_deterministic_offline(tmp_path):
    first,second=tmp_path/'a',tmp_path/'b'
    a=assets.prepare(None,first);b=assets.prepare(None,second)
    assert a==b and tree_hash(first/'lab')==tree_hash(second/'lab')
    for name in ('inventory.json','correction.yaml','oracle_coverage.json','preparation.json'):
        assert (first/name).read_bytes()==(second/name).read_bytes()
    # Gli output conservati sono solo un riferimento aggiuntivo, mai input di prepare.
    reference=json.loads((assets.DEFAULT_INPUTS/'preparation.json').read_text())
    for key in ('validation','baseline_sha256','inventory_sha256','correction_sha256'):
        assert a[key]==reference[key]
    for name in ('inventory.json','correction.yaml','oracle_coverage.json'):
        assert (first/name).read_bytes()==(assets.DEFAULT_INPUTS/name).read_bytes()
    inventory,report=assets.load_dataset(first)
    assert len(inventory['zones'])==201 and len(inventory['roles'])==16
    assert report['validation']['simulated_paths']==5587
    assert inventory['routing']['simulated_paths']==53*16
    assert not list((first/'lab').rglob('correction.yaml'))
    assert not list((first/'lab').rglob('named.conf'))
    for p in (first/'source_backbone/europa_cost266_static').glob('*.startup'):
        assert (first/'lab'/p.name).read_bytes().startswith(p.read_bytes())


@pytest.fixture
def extracted_inputs(tmp_path):
    """Solo sorgenti canonici: nessuna baseline, inventario, oracle o preparation."""
    import shutil
    inputs=tmp_path/'inputs';inputs.mkdir()
    for directory in assets.SOURCE_DIRECTORIES:
        shutil.copytree(assets.DEFAULT_INPUTS/directory,inputs/directory)
    shutil.copy2(assets.DEFAULT_INPUTS/assets.SOURCE_MANIFEST,inputs/assets.SOURCE_MANIFEST)
    return inputs


def test_input_resolution_independent_of_cwd_and_explicit_override(tmp_path,monkeypatch):
    monkeypatch.delenv('COST266_INPUTS',raising=False)
    monkeypatch.chdir(tmp_path)
    assert assets.resolve_inputs()==assets.DEFAULT_INPUTS
    monkeypatch.setenv('COST266_INPUTS','experiments/cost266_data')
    assert assets.resolve_inputs()==assets.DEFAULT_INPUTS
    monkeypatch.setenv('COST266_INPUTS',str(tmp_path/'missing'))
    assert assets.resolve_inputs()==tmp_path/'missing'
    assert assets.resolve_inputs(Path('experiments/cost266_data'))==assets.DEFAULT_INPUTS
    with pytest.raises(ValueError,match='Asset mancanti'):
        assets.prepare(None,tmp_path/'dataset')
    assert not (tmp_path/'dataset').exists()


@pytest.mark.parametrize('change',['missing','modified','symlink','traversal'])
def test_extracted_sources_fail_closed(extracted_inputs,tmp_path,change):
    source=extracted_inputs/'source_dns/zone_inventory.csv'
    if change=='missing':
        source.unlink()
        message=r'Asset mancanti: source_dns/zone_inventory.csv'
    elif change=='modified':
        source.write_text(source.read_text()+'\n')
        message=r'Hash sorgenti non corrispondenti: source_dns/zone_inventory.csv'
    elif change=='symlink':
        source.unlink();source.symlink_to(assets.DEFAULT_INPUTS/'source_dns/zone_inventory.csv')
        message='Link simbolico'
    else:
        manifest=extracted_inputs/assets.SOURCE_MANIFEST
        data=json.loads(manifest.read_text());data['files']['../outside']='0'*64
        manifest.write_text(json.dumps(data))
        message='Percorso sorgente non sicuro'
    with pytest.raises(ValueError,match=message):
        assets.prepare(extracted_inputs,tmp_path/'dataset')
    assert not (tmp_path/'dataset').exists()
    assert not list(tmp_path.glob('.cost266-import-*'))


def test_extracted_sources_and_zip_import_equivalent(extracted_inputs,tmp_path,monkeypatch):
    import zipfile
    # ZIP temporanei creati dai sorgenti, senza attribuirgli gli hash degli ZIP originali.
    archives=tmp_path/'archives';archives.mkdir()
    (archives/'cost266.json').write_bytes((extracted_inputs/assets.SOURCE_GRAPH).read_bytes())
    for directory,name in zip(assets.SOURCE_DIRECTORIES,assets.ARCHIVE_INPUTS[1:]):
        with zipfile.ZipFile(archives/name,'w') as book:
            for path in sorted((extracted_inputs/directory).rglob('*')):
                if path.is_file():book.write(path,path.relative_to(extracted_inputs/directory).as_posix())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('COST266_INPUTS',str(extracted_inputs))
    first,second=tmp_path/'extracted',tmp_path/'zipped'
    a=assets.prepare(None,first);b=assets.prepare(archives,second)
    assert a['source_files']==b['source_files']==assets.source_hashes(extracted_inputs)
    assert tree_hash(first/'lab')==tree_hash(second/'lab')
    for key in ('validation','baseline_sha256','inventory_sha256','correction_sha256'):
        assert a[key]==b[key]
    for name in ('inventory.json','correction.yaml','oracle_coverage.json'):
        assert (first/name).read_bytes()==(second/name).read_bytes()
    assert a['assets']=={assets.SOURCE_MANIFEST:assets.digest((extracted_inputs/assets.SOURCE_MANIFEST).read_bytes())}
    assert set(b['assets'])==set(assets.ARCHIVE_INPUTS)


def test_zip_security_and_missing_assets(tmp_path):
    import zipfile
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside','bad')
    with pytest.raises(ValueError,match='sicuro'):assets.extract(archive,tmp_path/'out')
    with pytest.raises(ValueError,match='Asset mancanti'):assets.prepare(tmp_path,tmp_path/'dataset')


def test_oracle_custom_command_truth_table(tmp_path):
    """Esegue realmente sh/awk generati con un dig fixture, senza emulatori."""
    command=assets.dig_assert('192.0.2.1','__probe.child.test.','A',
        [((1,'child.test.'),(4,'NS'),(5,'ns1.child.test.')),((1,'ns1.child.test.'),(4,'A'),(5,'192.0.2.2'))],flags='+norecurse')
    bindir=tmp_path/'bin';bindir.mkdir();dig=bindir/'dig'
    import os
    env={**os.environ,'PATH':str(bindir)+os.pathsep+os.environ['PATH']}
    for answer,expected in [('child.test. 3600 IN NS ns1.child.test.\nns1.child.test. 3600 IN A 192.0.2.2',0),
        ('child.test. 3600 IN NS ns1.child.test.',1),
        ('child.test. 3600 IN NS ns1.child.test.\nns1.child.test. 3600 IN A 192.0.2.3',1),('',1)]:
        import shlex
        dig.write_text('#!/bin/sh\nprintf "%s\\n" '+shlex.quote(answer)+'\n');dig.chmod(0o755)
        assert subprocess.run(command,shell=True,env=env,capture_output=True).returncode==expected


def test_cli_dry_run_filters_failure_exit_and_resume(case,monkeypatch,capsys):
    from scripts import run_cost266 as cli
    monkeypatch.setattr(cli,'load_config',lambda p:case.config)
    monkeypatch.setattr(cli,'load_spec',lambda *a:case.spec)
    monkeypatch.setattr(cli,'load_dataset',lambda p:(case.inventory,case.preparation))
    monkeypatch.setattr(cli,'preflight',lambda *a,**k:None)
    monkeypatch.setattr(cli,'validate_mode_sources',lambda *a:None)
    monkeypatch.setattr(runner,'run_aut',fake_aut(case))
    monkeypatch.setattr(runner,'run_checker',fake_checker(False))
    assert cli.main(['--dry-run','--strategy','incremental'])==0
    assert not (case.root/'runs').exists() and not case.calls
    assert cli.main(['--strategy','incremental'])==1
    assert cli.main(['--resume','--strategy','incremental'])==1
    assert len(case.calls)==6
    assert cli.main(['--dry-run','--skill-mode','dns_only'])==1


def test_cli_prepare_default_and_explicit_directory(case,monkeypatch):
    from scripts import run_cost266 as cli
    monkeypatch.setattr(cli,'load_config',lambda p:case.config)
    monkeypatch.setattr(cli,'load_spec',lambda *a:case.spec)
    calls=[]
    monkeypatch.setattr(cli,'prepare',lambda inputs,destination:(calls.append((inputs,destination)) or {}))
    assert cli.main(['--prepare'])==0
    assert cli.main(['--prepare','experiments/cost266_data'])==0
    assert calls==[(None,case.dataset),(Path('experiments/cost266_data'),case.dataset)]
    assert cli.main(['--prepare','--dry-run'])==1
    assert len(calls)==2


def test_experiment_lock_excludes_second_launcher(case):
    with runner.experiment_lock(case.root,'test'):
        with pytest.raises(ValueError,match='già in esecuzione'):
            with runner.experiment_lock(case.root,'test'):pass
