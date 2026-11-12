"""Selettore host: runner v1/v2 originali, con AUT simulati."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import hashlib
import json

import pandas as pd
import pytest
import yaml

from test_cost266 import case, fake_aut, fake_checker
from test_cost266_continuous import v2, ScriptedSession, forced
from benchmark_core.cost266 import runner, assets
from benchmark_core.cost266.protocol import VERSION, CONTINUOUS_VERSION, Cell, execution_mode
from benchmark_core.cost266.selection import resolve_selection
from benchmark_core.cost266.comparison import comparison_mismatches
from benchmark_core.cost266.reports import aggregate_cost266
from benchmark_core.workspace import write_json
from scripts import run_cost266 as cli


@pytest.fixture
def selection(v2,monkeypatch):
    root=v2.root
    for name,protocol,identity in [('cost266',CONTINUOUS_VERSION,'test_continuous'),
                                   ('cost266_v1',VERSION,'test_isolated')]:
        data={'experiment':{'id':identity},'dataset':'experiments/data','protocol':protocol,
              'strategies':['one_shot','incremental'],'prompt_types':['T1','T2'],
              'skill_modes':['no_skill','auto'],'repetitions':2,
              'budgets':{'stage_seconds':100,'total_seconds':1000,'checker_seconds':100}}
        (root/'experiments'/(name+'.yaml')).write_text(yaml.safe_dump(data))
    monkeypatch.setattr(cli,'ROOT',root)
    monkeypatch.setattr(cli,'load_config',lambda path:v2.config)
    monkeypatch.setattr(cli,'load_dataset',lambda path:(v2.inventory,v2.preparation))
    monkeypatch.setattr(cli,'preflight',lambda *a,**k:None)
    monkeypatch.setattr(cli,'validate_mode_sources',lambda *a:None)
    original=fake_aut(v2)
    def independent(*args,**kwargs):
        original(*args,**kwargs)
        logs=args[2]/'logs/aut'
        events=logs/'events.jsonl'
        events.write_text(json.dumps({'type':'thread.started','thread_id':'thread-'+kwargs['run_id']})+'\n'+events.read_text())
    monkeypatch.setattr(runner,'run_aut',independent)
    return v2


def arguments(mode,*extra):
    return ['--execution-mode',mode,'--prompt-type','T1','--skill-mode','no_skill','--only-replicate','1',*extra]


@pytest.mark.parametrize('mode,protocol,strategy,identity',[
    ('one_shot',CONTINUOUS_VERSION,'one_shot','test_continuous'),
    ('incremental_isolated',VERSION,'incremental','test_isolated'),
    ('incremental_continuous',CONTINUOUS_VERSION,'incremental','test_continuous')])
def test_default_configuration_mapping_is_loaded_before_cells(selection,mode,protocol,strategy,identity):
    s=resolve_selection(selection.root,selection.root,mode=mode)
    assert s.spec.protocol==protocol and s.spec.experiment_id==identity
    assert {c.strategy for c in s.selected_cells()}=={strategy}
    assert len(s.selected_cells(prompt_type='T1',skill_mode='no_skill',repetition=1))==1


@pytest.mark.parametrize('mode',['one_shot','incremental_isolated','incremental_continuous'])
def test_dry_run_displays_policies_and_does_not_call_backends(selection,monkeypatch,capsys,mode):
    for name in ('execute','preflight','experiment_lock'):
        monkeypatch.setattr(cli,name,lambda *a,**k:pytest.fail('mutation/backend during dry-run'))
    assert cli.main(arguments(mode,'--dry-run'))==0
    text=capsys.readouterr().out
    for field in ('Execution mode: '+mode,'Protocol:','Experiment:','Prompt type: T1','Skill mode: no_skill',
                  'Functional turns:','Session policy:','Writable sandbox policy:','Checker: final'):
        assert field in text
    if mode=='incremental_continuous':assert 'Session policy: persistent' in text and 'Writable sandbox policy: shared' in text
    assert not (selection.root/'runs').exists() and not (selection.root/'results').exists()


@pytest.mark.parametrize('mode',['one_shot','incremental_isolated','incremental_continuous'])
def test_selector_executes_existing_engines_and_records_mode(selection,mode):
    assert cli.main(arguments(mode))==0
    manifests=list((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    assert len(manifests)==1
    metadata=json.loads(manifests[0].read_text())
    assert metadata['execution_mode']==mode
    if mode=='incremental_continuous':
        assert not selection.calls and len(ScriptedSession.instances)==1
        assert ScriptedSession.instances[0].creates==[False]
        assert len(ScriptedSession.instances[0].received)==6
        assert metadata['thread_id']=='thread-initial' and metadata['session_count']==1
    else:
        assert len(selection.calls)==(1 if mode=='one_shot' else 6)
        assert len({c['run_id'] for c in selection.calls})==len(selection.calls)
        assert not ScriptedSession.instances
    metrics=json.loads((manifests[0].parent/'evaluation/metrics.json').read_text())
    assert metrics['execution_mode']==mode
    report=selection.root/'results/cost266/experiments'/metadata['experiment_id']
    for filename in ('runs.csv','checks.csv','summary.csv','stages.csv'):
        frame=pd.read_csv(report/filename)
        assert set(frame['execution_mode'])=={mode}
    from openpyxl import load_workbook
    book=load_workbook(report/'benchmark.xlsx',read_only=True)
    assert all('execution_mode' in [c.value for c in next(book[sheet].iter_rows())]
               for sheet in ('Runs','Checks','Summary','Stages'))
    book.close()


@pytest.mark.parametrize('mode,strategy',[('one_shot','incremental'),('incremental_isolated','one_shot'),
                                         ('incremental_continuous','one_shot')])
def test_contradictory_strategy_rejected_before_dataset(selection,monkeypatch,capsys,mode,strategy):
    monkeypatch.setattr(cli,'load_dataset',lambda *a:pytest.fail('dataset before argument validation'))
    assert cli.main(['--execution-mode',mode,'--strategy',strategy,'--dry-run'])==1
    assert 'contraddittori' in capsys.readouterr().err
    assert not (selection.root/'runs').exists()


@pytest.mark.parametrize('mode,file',[('incremental_continuous','cost266_v1.yaml'),
                                     ('incremental_isolated','cost266.yaml')])
def test_explicit_incompatible_file_preserved(selection,monkeypatch,capsys,mode,file):
    path=selection.root/'experiments'/file;before=path.read_bytes()
    monkeypatch.setattr(cli,'load_dataset',lambda *a:pytest.fail('dataset before protocol validation'))
    assert cli.main([str(path),*arguments(mode,'--dry-run')])==1
    assert 'Configurazione incompatibile' in capsys.readouterr().err
    assert path.read_bytes()==before


def test_alias_and_matching_legacy_strategy(selection,capsys):
    assert cli.main(['--mode','incremental_isolated','--strategy','incremental','--prompt-type','T2',
                     '--skill-mode','no_skill','--only-replicate','2','--dry-run'])==0
    text=capsys.readouterr().out
    assert 'Execution mode: incremental_isolated' in text and 'Prompt type: T2' in text and 'Repetition: 2' in text


def test_no_mode_preserves_previous_matrix_and_filters(selection,capsys):
    forced(selection,'auto')
    assert cli.main(['--dry-run'])==0
    text=capsys.readouterr().out
    assert text.count('Execution mode:')==16
    assert text.count('Execution mode: one_shot')==8 and text.count('Execution mode: incremental_continuous')==8
    assert cli.main(['--strategy','one_shot','--prompt-type','T1','--skill-mode','no_skill','--dry-run'])==0
    assert capsys.readouterr().out.count('Execution mode: one_shot')==2
    # Vecchio filtro: una Skill non pianificata non viene aggiunta implicitamente.
    assert cli.main(['--skill-mode','dns_only','--dry-run'])==1


def test_explicit_one_shot_legacy_keeps_protocol_dataset_and_identity(selection,capsys):
    path=selection.root/'experiments/cost266_v1.yaml'
    selected=resolve_selection(selection.root,selection.root,path,mode='one_shot')
    assert selected.spec.protocol==VERSION and selected.spec.experiment_id=='test_isolated'
    assert selected.spec.dataset==selection.dataset
    assert cli.main([str(path),*arguments('one_shot','--dry-run')])==0
    assert VERSION in capsys.readouterr().out


def test_default_v1_v2_observations_do_not_collide(selection):
    assert cli.main(arguments('incremental_isolated'))==0
    assert cli.main(arguments('incremental_continuous'))==0
    paths=list((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    assert len(paths)==2
    rows=[json.loads(p.read_text()) for p in paths]
    assert len({r['run_id'] for r in rows})==2
    assert {r['execution_mode'] for r in rows}=={'incremental_isolated','incremental_continuous'}


def test_skill_selection_is_independent_and_gate_is_not_disabled(selection):
    forced(selection,'dns_only')
    path=selection.root/'experiments/cost266.yaml';before=path.read_bytes()
    assert cli.main(['--execution-mode','incremental_continuous','--skill-mode','dns_only',
                     '--prompt-type','T1','--only-replicate','1'])==0
    session=ScriptedSession.instances[0]
    assert session.creates==[True,False] and len([p for p in session.received if not p[0]])==6
    assert path.read_bytes()==before
    metadata=next((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    gate=json.loads((metadata.parent/'logs/aut/skill_gate.json').read_text())
    assert gate['skill_gate_read_attempts']==1 and gate['skill_gate_verified_skills']==['kathara-dns']


def test_v1_incompatible_skill_and_explicit_skill_exclusion_are_errors(selection,monkeypatch,capsys):
    forced(selection,'dns_only')
    monkeypatch.setattr(cli,'load_dataset',lambda *a:pytest.fail('must reject before dataset'))
    assert cli.main(['--execution-mode','incremental_isolated','--skill-mode','dns_only','--dry-run'])==1
    assert 'più chiamate' in capsys.readouterr().err
    assert cli.main([str(selection.root/'experiments/cost266.yaml'),'--execution-mode','incremental_continuous',
                     '--skill-mode','dns_only','--dry-run'])==1
    assert 'non abilita' in capsys.readouterr().err


@pytest.mark.parametrize('mode',['one_shot','incremental_isolated','incremental_continuous'])
def test_resume_and_rerun_address_exact_observation(selection,mode):
    args=arguments(mode)
    assert cli.main(args)==0
    aut_calls=len(selection.calls);sessions=len(ScriptedSession.instances)
    assert cli.main(args+['--resume'])==0
    assert cli.main(args+['--rerun-correction'])==0
    assert len(selection.calls)==aut_calls and len(ScriptedSession.instances)==sessions
    metadata=json.loads(next((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json')).read_text())
    assert metadata['execution_mode']==mode and metadata['evaluation_revision']==1


def test_isolated_checkpoint_resume_and_continuous_resume_policy_unchanged(selection,monkeypatch,capsys):
    monkeypatch.setattr(runner,'run_aut',fake_aut(selection,fail_at=3))
    args=arguments('incremental_isolated')
    assert cli.main(args)==1 and len(selection.calls)==3
    monkeypatch.setattr(runner,'run_aut',fake_aut(selection))
    assert cli.main(args+['--resume'])==0
    assert [c['stage'] for c in selection.calls]==[1,2,3,3,4,5,6]
    ScriptedSession.fault='failure'
    args=arguments('incremental_continuous')
    assert cli.main(args)==1
    assert cli.main(args+['--resume'])==1
    assert 'stessa sandbox/thread' in capsys.readouterr().err
    assert len(ScriptedSession.instances)==1 and len(ScriptedSession.instances[0].received)==3


def test_explicit_strategy_disabled_is_rejected(selection,monkeypatch,capsys):
    path=selection.root/'experiments/cost266.yaml'
    data=yaml.safe_load(path.read_text());data['strategies']=['one_shot'];path.write_text(yaml.safe_dump(data))
    monkeypatch.setattr(cli,'load_dataset',lambda *a:pytest.fail('incompatible plan must fail first'))
    assert cli.main([str(path),*arguments('incremental_continuous','--dry-run')])==1
    assert 'non abilita la strategia' in capsys.readouterr().err


def test_incoherent_dataset_remains_fail_closed(selection,monkeypatch):
    write_json(selection.dataset/'inventory.json',selection.inventory)
    preparation={**selection.preparation,'inventory_sha256':hashlib.sha256((selection.dataset/'inventory.json').read_bytes()).hexdigest()}
    write_json(selection.dataset/'preparation.json',preparation)
    with (selection.dataset/'lab/lab.conf').open('a') as f:f.write('# mismatch\n')
    original=(selection.dataset/'preparation.json').read_bytes()
    monkeypatch.setattr(cli,'load_dataset',assets.load_dataset)
    assert cli.main(arguments('incremental_continuous','--dry-run'))==1
    assert not ScriptedSession.instances and not selection.calls
    assert (selection.dataset/'preparation.json').read_bytes()==original


def test_historical_metadata_is_labelled_without_rewriting(selection):
    assert cli.main(arguments('incremental_isolated'))==0
    path=next((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    data=json.loads(path.read_text());data.pop('execution_mode');path.write_text(json.dumps(data))
    metrics=path.parent/'evaluation/metrics.json';saved=json.loads(metrics.read_text());saved.pop('execution_mode')
    metrics.write_text(json.dumps(saved));before=path.read_bytes()
    frames=aggregate_cost266(selection.root,selection.root/'results/test_isolated')
    assert frames[0]['execution_mode'].iloc[0]=='incremental_isolated'
    assert path.read_bytes()==before


def test_cross_protocol_comparison_checks_all_controls(selection):
    assert cli.main(arguments('one_shot'))==0
    assert cli.main(arguments('incremental_isolated'))==0
    rows=[json.loads(p.read_text()) for p in (selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json')]
    assert comparison_mismatches(*rows)==[]
    for field in ('baseline_sha256','correction_sha256','inventory_sha256','model','reasoning_effort',
                  'skill_mode','skill_protocol','skill_bundles','budgets','config_sha256'):
        changed=deepcopy(rows[1]);changed['conditions'][field]='different'
        assert field in comparison_mismatches(rows[0],changed)
    changed=deepcopy(rows[1]);changed['requirements_sha256']='different'
    assert 'requirements_sha256' in comparison_mismatches(rows[0],changed)


def test_pairs_report_marks_mismatched_conditions_non_comparable(selection):
    assert cli.main(arguments('one_shot'))==0
    selection.config.data['aut']['model']='other-model'
    assert cli.main(arguments('incremental_continuous'))==0
    pairs=pd.read_csv(selection.root/'results/cost266/experiments/test_continuous/pairs.csv')
    assert len(pairs)==1 and not pairs['comparable_evaluated_pair'].iloc[0]
    assert 'model' in pairs['reason'].iloc[0]
    assert pd.isna(pairs['delta_final_pass_rate'].iloc[0])


def test_inconsistent_execution_label_cannot_resume(selection,capsys):
    args=arguments('incremental_isolated')
    assert cli.main(args)==0
    path=next((selection.root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json'))
    data=json.loads(path.read_text());data['execution_mode']='incremental_continuous'
    path.write_text(json.dumps(data));calls=len(selection.calls)
    assert cli.main(args+['--resume'])==1
    assert 'Execution mode incoerente' in capsys.readouterr().err
    assert len(selection.calls)==calls
