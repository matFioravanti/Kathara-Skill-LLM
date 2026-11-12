"""Offline comparison of verified COST266 observations across experiments."""
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import hashlib
import json
import math
import re
import statistics
import zipfile

import pandas as pd

from .cost266.comparison import FIELDS, comparison_mismatches
from .cost266.protocol import CONTINUOUS_VERSION, execution_mode, fingerprint, safe_path
from .cost266.runner import collect_metrics, read_json, verify_run
from .aggregation import _run_record
from .prompts import PROMPT_TYPES
from .skill_modes import SKILL_MODE_CHOICES

MODES=('one_shot','incremental_isolated','incremental_continuous')
PAIRS=((MODES[0],MODES[1]),(MODES[1],MODES[2]),(MODES[0],MODES[2]))
KEYS=('scenario_id','dns_tree_id','task_level','prompt_type','skill_mode','replicate')
TOKEN_METRICS=('input_tokens','output_tokens','cached_input_tokens','reasoning_tokens','total_tokens',
               'gate_input_tokens','gate_output_tokens','functional_input_tokens','functional_output_tokens')
METRICS=('task_success','checker_execution_success','checks_passed','checks_total','final_pass_rate',
         'total_seconds','agent_seconds','checker_seconds','sandbox_overhead_seconds',*TOKEN_METRICS,
         'functional_turns','gate_turns','session_count','sandbox_count','protected_sandbox_count',
         'writable_sandbox_count','context_continuity_verified','session_cleanup_ok')
PROPERTY_TYPES=('soa','authority','apex_ns','ns_address','delegation_glue','record','client_resolver','client_resolution')
PROPERTY_COLUMNS=tuple(f'{kind}_{field}' for kind in PROPERTY_TYPES for field in ('passed','observed','expected','pass_rate','coverage_complete'))
METRICS=METRICS+PROPERTY_COLUMNS
DELTAS=('final_pass_rate','checks_passed','agent_seconds','input_tokens','output_tokens','total_tokens','sandbox_overhead_seconds','total_seconds')


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value):
    return value if type(value) in (int,float) and math.isfinite(value) else None


def _stat_value(field, value):
    if (field in ('task_success','checker_execution_success','context_continuity_verified','session_cleanup_ok')
            or field.endswith('_coverage_complete')) and type(value) is bool:
        return int(value)
    return _number(value)


def _condition_key(meta, agent_runtime_version):
    conditions=meta.get('conditions') or {}
    selected={key:conditions.get(key) for key in FIELDS}
    selected['requirements_sha256']=meta.get('requirements_sha256')
    selected['implementation_sha256']=conditions.get('implementation_sha256')
    selected['agent_runtime_version']=agent_runtime_version
    selected['execution_backend']=meta.get('execution_backend')
    return fingerprint(selected)


def _observe(path, root):
    run=path.parent
    relative=run.relative_to(root/'runs');parts=relative.parts
    repetition=int(parts[7][1:]) if re.fullmatch(r'r\d+',parts[7]) else None
    row={'source_path':str(run.relative_to(root)), 'integrity_verified':False,
         'experiment_id':parts[0],'scenario_id':parts[1],'dns_tree_id':parts[2],
         'task_level':parts[3],'prompt_type':parts[4],'strategy':parts[5],
         'skill_mode':parts[6],'replicate':repetition}
    meta={};metrics={};artifacts={}
    try:
        meta=read_json(path)
        if meta.get('schema')!='cost266_v1':raise ValueError('Schema COST266 non valido')
        conditions=meta['conditions']
        relative=run.relative_to(root/'runs')
        if conditions.get('identity')!=relative.as_posix() or meta.get('run_id')!='__'.join(relative.parts):
            raise ValueError('Identità manifest/percorso non coerente')
        if meta.get('experiment_id')!=relative.parts[0]:raise ValueError('Experiment ID incoerente')
        if meta.get('prompt_type') not in PROMPT_TYPES or meta.get('skill_mode') not in SKILL_MODE_CHOICES:
            raise ValueError('Prompt type o modalità Skill non valida')
        repetitions=[meta[field] for field in ('replicate','repetition','run_number') if meta.get(field) is not None]
        if not repetitions or any(type(value) is not int or value<1 or value!=repetitions[0] for value in repetitions):
            raise ValueError('Ripetizione non valida')
        for field,index in (('scenario_id',1),('dns_tree_id',2),('task_level',3),('prompt_type',4),('strategy',5),('skill_mode',6)):
            if meta.get(field)!=relative.parts[index]:raise ValueError('Identità incoerente: '+field)
        if relative.parts[7]!=f"r{repetitions[0]:03d}":raise ValueError('Ripetizione incoerente')
        version=conditions['protocol']
        if (meta.get('protocol_version') or version)!=version:raise ValueError('Protocollo manifest incoerente')
        for field in ('agent','model','reasoning_effort','skill_protocol'):
            if meta.get(field) is not None and meta[field]!=conditions.get(field):
                raise ValueError('Condizione manifest incoerente: '+field)
        mode=execution_mode(version,meta['strategy'])
        row.update({key:meta.get(key) for key in (*KEYS,'experiment_id','run_id','strategy')})
        row['replicate']=repetitions[0]
        row.update(protocol_version=version,execution_mode=mode,legacy_one_shot=(mode=='one_shot' and version!=CONTINUOUS_VERSION),
                   pipeline_state=meta.get('pipeline_state'),checker_execution_success=meta.get('checker_execution_success'),
                   task_success=meta.get('task_success'),revision=conditions.get('repository_revision'))
        for key in ('agent','model','reasoning_effort','skill_protocol','baseline_sha256','correction_sha256','inventory_sha256','config_sha256'):
            row[key]=conditions.get(key)
        row['requirements_sha256']=meta.get('requirements_sha256')
        for key in ('skill_bundles','budgets','component_versions'):
            row[key]=json.dumps(conditions.get(key),sort_keys=True,ensure_ascii=False)
        for key in KEYS:
            if row[key] is None or row[key]=='':raise ValueError('identità incompleta: '+key)
        if meta.get('skill_mode')!=conditions.get('skill_mode'):raise ValueError('skill_mode incoerente')
        _,completed=verify_run(run,conditions)
        row['integrity_verified']=True
        metric_path=run/'evaluation/metrics.json'
        metrics=read_json(metric_path) if metric_path.is_file() else {}
        normalized=_run_record(metrics,meta)
        tokens=metrics.get('tokens') or {};timing=metrics.get('timing') or {};checker=metrics.get('checker') or {}
        if meta.get('pipeline_state')=='COMPLETED':
            from .checker_runner import parse_reports
            checker_result,_=parse_reports(run/'results')
            for stored,actual in ((checker.get('pass_rate'),checker_result['check_pass_rate']),
                                  (metrics.get('final_pass_rate'),checker_result['check_pass_rate']),
                                  (checker.get('failed'),checker_result['checks_failed'])):
                if stored is not None and stored!=actual:raise ValueError('Metriche checker incoerenti con i report')
        row.update(checks_passed=checker.get('passed'),checks_total=checker.get('total'),
                   final_pass_rate=metrics.get('final_pass_rate',checker.get('pass_rate')),
                   total_seconds=timing.get('total_seconds'),agent_seconds=timing.get('agent_seconds'),
                   checker_seconds=timing.get('checker_seconds'),sandbox_overhead_seconds=timing.get('sandbox_overhead_seconds'),
                   input_tokens=tokens.get('input'),output_tokens=tokens.get('output'),
                   cached_input_tokens=tokens.get('cached_input'),reasoning_tokens=tokens.get('reasoning'),total_tokens=tokens.get('total'))
        for key in METRICS:
            if key not in row:row[key]=metrics.get(key,meta.get(key))
        for kind in PROPERTY_TYPES:
            values=(metrics.get('dns_property_checks') or {}).get(kind) or {}
            for field in ('passed','observed','expected','pass_rate','coverage_complete'):
                row[f'{kind}_{field}']=values.get(field)
        phase_paths=sorted((run/'steps').glob('*/attempts/*/evaluation/metrics.json'))
        phases=[read_json(p) for p in phase_paths]
        row['phase_times']=json.dumps([{'stage':item.get('stage_index'),
            'agent_seconds':(item.get('timing') or {}).get('agent_seconds')} for item in phases],sort_keys=True)
        backend=meta.get('execution_backend')
        row['execution_backend']=backend
        version_key='codex_sandbox_version' if backend=='docker_sandbox' else 'codex_host_version'
        versions=[]
        for item in phases:
            value=item.get(version_key) or (item.get('sandbox') or {}).get(version_key)
            versions.append(str(value).removeprefix('codex-cli ').strip() if value else None)
        if conditions.get('agent')!='codex':
            versions=[meta.get('agent_version')]
        row['agent_runtime_version']=versions[0] if versions and all(v and v==versions[0] for v in versions) else None
        if (not backend or len(phases)<max(len(completed),len(meta.get('attempt_history') or []))
                or any(item.get('execution_backend')!=backend for item in phases)):
            row['agent_runtime_version']=None
        row['usage_verified']=False
        if metrics.get('usage_verified') is True:
            try:
                computed=collect_metrics(run,meta)
                row['usage_verified']=(computed.get('usage_verified') is True and computed.get('tokens')==tokens)
            except (OSError,ValueError,KeyError,TypeError):
                row['usage_verified']=False
        if not row['usage_verified']:
            for key in TOKEN_METRICS:row[key]=None
        row['status']='complete' if normalized['_evaluated'] else ('checker_unavailable' if meta.get('pipeline_state')=='CHECKER_FAILED' else 'incomplete')
        if row['status']=='complete' and row.get('task_success') is False:row['status']='task_failed'
        row['condition_group']=_condition_key(meta,row['agent_runtime_version'])
    except (ValueError,KeyError,TypeError,OSError,AttributeError) as exc:
        row.update(status='integrity_error',integrity_error=str(exc),usage_verified=False)
    for item in sorted(run.rglob('*')):
        if item.is_symlink():
            row.update(status='integrity_error',integrity_verified=False,integrity_error='symlink in run')
            continue
        if item.is_file():artifacts[str(item.relative_to(run))]=file_hash(item)
    return {'row':row,'meta':meta,'metrics':metrics,'artifacts':artifacts}


def _pair(a,b,kind,key):
    row={**dict(zip(KEYS,key)),'mode_a':kind[0],'mode_b':kind[1],
         'run_a':a['row'].get('run_id') if a else None,'run_b':b['row'].get('run_id') if b else None}
    reasons=[]
    if not a or not b:reasons.append('modalità mancante')
    else:
        for obj in (a,b):
            if not obj['row'].get('integrity_verified'):reasons.append('integrità non verificata')
            if obj['row'].get('status') not in ('complete','task_failed'):reasons.append('run incompleta o checker non disponibile')
            conditions=obj['meta'].get('conditions') or {}
            for field in ('skill_mode','skill_protocol','budgets','config_sha256','component_versions'):
                if not conditions.get(field):reasons.append(field+' non verificabile')
            budgets=conditions.get('budgets')
            if not isinstance(budgets,list) or len(budgets)!=3 or any(type(value) is not int or value<=0 for value in budgets):
                reasons.append('budgets non verificabile')
            components=conditions.get('component_versions')
            if not isinstance(components,dict) or not components or any(not isinstance(value,str) or not value for value in components.values()):
                reasons.append('component_versions non verificabile')
            for field in ('baseline_sha256','correction_sha256','inventory_sha256','config_sha256','implementation_sha256'):
                if not re.fullmatch(r'[0-9a-f]{64}',str(conditions.get(field) or '')):
                    reasons.append(field+' non verificabile')
            requirement=obj['meta'].get('requirements_sha256')
            if requirement is not None and not re.fullmatch(r'[0-9a-f]{64}',str(requirement)):
                reasons.append('requirements_sha256 non verificabile')
            if not isinstance(conditions.get('skill_bundles'),dict):reasons.append('skill_bundles non verificabile')
            if conditions.get('skill_mode')!='no_skill' and not conditions.get('skill_bundles'):
                reasons.append('skill_bundles non verificabile')
            if isinstance(conditions.get('skill_bundles'),dict) and any(
                    not re.fullmatch(r'[0-9a-f]{64}',str(value or '')) for value in conditions['skill_bundles'].values()):
                reasons.append('skill_bundles non verificabile')
        reasons+=comparison_mismatches(a['meta'],b['meta'])
        if (a['meta'].get('conditions') or {}).get('implementation_sha256') != (b['meta'].get('conditions') or {}).get('implementation_sha256'):
            reasons.append('implementation_sha256')
        if not a['row'].get('agent_runtime_version') or not b['row'].get('agent_runtime_version'):
            reasons.append('versione runtime agente non verificabile')
        elif a['row']['agent_runtime_version']!=b['row']['agent_runtime_version']:
            reasons.append('agent_runtime_version')
        if not a['row'].get('execution_backend') or a['row'].get('execution_backend')!=b['row'].get('execution_backend'):
            reasons.append('execution_backend non confrontabile')
    row['comparable']=not reasons
    row['reason']='; '.join(dict.fromkeys(reasons))
    row['token_reason']='' if a and b and a['row'].get('usage_verified') and b['row'].get('usage_verified') else 'token non verificati'
    for field in DELTAS:
        av=_number(a['row'].get(field)) if a else None
        bv=_number(b['row'].get(field)) if b else None
        row['delta_'+field]=(bv-av if row['comparable'] and av is not None and bv is not None
                            and (field not in TOKEN_METRICS or not row['token_reason']) else None)
        row['delta_'+field+'_reason']=('condizioni non confrontabili' if not row['comparable'] else
            row['token_reason'] if field in TOKEN_METRICS and row['token_reason'] else
            'valore non disponibile' if av is None or bv is None else '')
    return row


def compare(root, output, experiments=None):
    root=safe_path(Path(root).absolute());output=safe_path(Path(output).absolute())
    if output.exists() or output==root or output.is_relative_to(root/'runs') or output.is_relative_to(root/'experiments'):
        raise ValueError('Output deve essere una nuova directory esterna alle run e agli asset')
    selected=set(experiments or [])
    observations=[]
    for path in sorted((root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json')):
        if path.is_symlink():raise ValueError('Manifest symlink non consentito')
        if selected and path.relative_to(root/'runs').parts[0] not in selected:continue
        obj=_observe(path,root)
        if obj is not None:observations.append(obj)
    if selected:
        missing=selected-{o['row'].get('experiment_id') for o in observations}
        if missing:raise ValueError('Esperimenti senza osservazioni: '+', '.join(sorted(missing)))
    groups=defaultdict(lambda:defaultdict(list))
    for obj in observations:
        row=obj['row'];key=tuple(row.get(k) for k in KEYS)
        if any(value is None or value=='' for value in key):continue
        treatment='one_shot_v1_legacy' if row.get('legacy_one_shot') else row.get('execution_mode')
        groups[key][treatment].append(obj)
    pairs=[];triples=[];diagnostics=[];eligible=set()
    for obj in observations:
        row=obj['row']
        if row.get('status') in ('integrity_error','incomplete','checker_unavailable'):
            diagnostics.append({**{key:row.get(key) for key in KEYS},
                'issue':row.get('integrity_error') or row['status'],
                'mode':row.get('execution_mode'),'count':1})
    for key,group in sorted(groups.items(),key=lambda item:str(item[0])):
        unique={mode:items[0] if len(items)==1 else None for mode,items in group.items()}
        duplicate={mode for mode,items in group.items() if len(items)>1}
        # A valid singleton contributes to its own condition stratum even if
        # another treatment is missing; no cross-condition pooling is allowed.
        for mode in MODES:
            obj=unique.get(mode)
            if obj and _pair(obj,obj,(mode,mode),key)['comparable']:
                eligible.add(id(obj))
        for mode in sorted(duplicate,key=str):
            diagnostics.append({**dict(zip(KEYS,key)),'issue':'duplicate','mode':mode,'count':len(group[mode])})
        current=[]
        for kind in PAIRS:
            p=_pair(unique.get(kind[0]),unique.get(kind[1]),kind,key)
            if duplicate.intersection(kind):p.update(comparable=False,reason='osservazioni duplicate',**{'delta_'+f:None for f in DELTAS})
            if p['comparable']:
                eligible.update((id(unique[kind[0]]),id(unique[kind[1]])))
            if p['reason']:
                diagnostics.append({**dict(zip(KEYS,key)),'issue':p['reason'],'mode':' vs '.join(kind),'count':1})
            if p['token_reason'] and p['comparable']:
                diagnostics.append({**dict(zip(KEYS,key)),'issue':p['token_reason'],'mode':' vs '.join(kind),'count':1})
            pairs.append(p);current.append(p)
        triple={**dict(zip(KEYS,key)),'complete':all(unique.get(mode) for mode in MODES),
                'comparable':all(p['comparable'] for p in current),
                'reason':'; '.join(dict.fromkeys(p['reason'] for p in current if p['reason']))}
        for mode in MODES:
            entry=unique.get(mode);triple[mode+'_status']='duplicate' if mode in duplicate else entry['row'].get('status') if entry else 'missing'
            triple[mode+'_run_id']=entry['row'].get('run_id') if entry else None
            for field in METRICS:triple[mode+'_'+field]=entry['row'].get(field) if entry else None
            triple[mode+'_usage_verified']=entry['row'].get('usage_verified',False) if entry else False
        triples.append(triple)
    rows=[o['row'] for o in observations]
    summary=[]
    # Retain the treatment in every summary, even when grouping by prompt or
    # Skill: averaging across modes would obscure the experimental effect.
    for dimensions in [('execution_mode',),('execution_mode','prompt_type'),
                       ('execution_mode','skill_mode'),('execution_mode','prompt_type','skill_mode')]:
        categories=defaultdict(list)
        for obj in observations:categories[tuple(obj['row'].get(k) for k in dimensions)].append(obj)
        for category,items in sorted(categories.items(),key=lambda x:str(x[0])):
            partitions=defaultdict(list)
            for obj in items:
                row=obj['row']
                if id(obj) in eligible and not row.get('legacy_one_shot'):
                    partitions[row.get('condition_group')].append(obj)
            if not partitions:partitions[None]=[]
            for partition,valid in sorted(partitions.items(),key=lambda x:str(x[0])):
                for field in METRICS:
                    nums=[v for obj in valid if (field not in TOKEN_METRICS or obj['row'].get('usage_verified'))
                          if (v:=_stat_value(field,obj['row'].get(field))) is not None]
                    summary.append({'group_by':'+'.join(dimensions),**dict(zip(dimensions,category)),'condition_group':partition,
                        'metric':field,'observations_total':len(items),'observations_valid':len(nums),'observations_excluded':len(items)-len(nums),
                        'mean':statistics.mean(nums) if nums else None,'median':statistics.median(nums) if nums else None,
                        'stdev':statistics.stdev(nums) if len(nums)>1 else None})
    output.mkdir(parents=True,exist_ok=False)
    obscols=list(dict.fromkeys([*KEYS,'experiment_id','run_id','source_path','execution_mode','protocol_version','legacy_one_shot',
        'agent','model','reasoning_effort','skill_protocol','skill_bundles','budgets','component_versions','execution_backend','agent_runtime_version',
        'baseline_sha256','correction_sha256','inventory_sha256','requirements_sha256','config_sha256',
        'status','integrity_verified','integrity_error','usage_verified','phase_times','condition_group',*METRICS]))
    paircols=[*KEYS,'mode_a','mode_b','run_a','run_b','comparable','reason','token_reason',
              *(name for f in DELTAS for name in ('delta_'+f,'delta_'+f+'_reason'))]
    triplecols=[*KEYS,'complete','comparable','reason',*(mode+'_'+field for mode in MODES for field in ('status','run_id',*METRICS,'usage_verified'))]
    summarycols=['group_by','execution_mode','prompt_type','skill_mode','condition_group','metric','observations_total','observations_valid','observations_excluded','mean','median','stdev']
    frames={'Observations':pd.DataFrame(rows).reindex(columns=obscols),'Pairwise':pd.DataFrame(pairs).reindex(columns=paircols),
            'Three Modes':pd.DataFrame(triples).reindex(columns=triplecols),'Summary':pd.DataFrame(summary).reindex(columns=summarycols),'Diagnostics':pd.DataFrame(diagnostics,columns=[*KEYS,'issue','mode','count'])}
    for sheet,name in [('Observations','observations.csv'),('Pairwise','pairwise_comparisons.csv'),('Three Modes','three_modes_comparison.csv'),('Summary','summary.csv')]:
        frames[sheet].to_csv(output/name,index=False,lineterminator='\n')
    with pd.ExcelWriter(output/'benchmark_comparison.xlsx',engine='openpyxl') as writer:
        for sheet,frame in frames.items():frame.to_excel(writer,sheet_name=sheet,index=False)
        from datetime import datetime
        writer.book.properties.created=writer.book.properties.modified=datetime(2000,1,1)
    workbook=output/'benchmark_comparison.xlsx'
    with zipfile.ZipFile(workbook) as archive:contents=[(i.filename,archive.read(i.filename)) for i in archive.infolist()]
    with zipfile.ZipFile(workbook,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in contents:
            if name=='docProps/core.xml':
                data=re.sub(rb'(<dcterms:modified\b[^>]*>)[^<]+(</dcterms:modified>)',
                            rb'\g<1>2000-01-01T00:00:00Z\g<2>',data)
            entry=zipfile.ZipInfo(name,(2000,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(entry,data)
    manifest={'algorithm':'cost266_comparison_v1','delta':'B - A','pairing_keys':KEYS,
        'experiments':sorted(selected) if selected else sorted({r.get('experiment_id') for r in rows if r.get('experiment_id')}),
        'observations_read':len(rows),'valid_pairs':sum(p['comparable'] for p in pairs),
        'valid_triples':sum(t['comparable'] for t in triples),
        'exclusion_reasons':dict(sorted(Counter(p['reason'] for p in pairs if p['reason']).items())),
        'sources':[{'path':o['row']['source_path'],'run_id':o['row'].get('run_id'),'revision':o['row'].get('revision'),'artifacts_sha256':o['artifacts']} for o in observations]}
    (output/'comparison_manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2,ensure_ascii=False)+'\n')
    return manifest
