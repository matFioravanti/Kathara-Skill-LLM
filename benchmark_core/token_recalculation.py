"""Explicit offline exports. Source runs, receipts and prior results stay immutable."""
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import re
import shutil

import pandas as pd

from .token_usage import (UsageLedger, FIELDS, SCHEMA, read, record_turn, save,
                          aggregate_accounting, events_at)
from .run_metrics import codex_usage, accounting_fields


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular_files(root):
    return [p for p in sorted(root.rglob('*')) if p.is_file()
            and not any(part.is_symlink() for part in (p,*p.parents))]


def rank(directory):
    parts=directory.parts
    if directory.name=='phase_a':return (0,0,0,0),True
    if directory.parent.name=='retries' and re.fullmatch(r'attempt_\d+',directory.name):
        return (1,int(directory.name.split('_')[-1]),0,0),True
    if directory.name=='fallback':return (2,0,0,0),True
    if 'steps' in parts:
        at=parts.index('steps')
        try:
            stage=int(parts[at+1])
            attempt=int(parts[parts.index('attempts')+1]) if 'attempts' in parts else 1
            return (3,stage,attempt,0),True
        except (ValueError,IndexError):pass
    match=re.fullmatch(r'turn[_-]?(\d+)',directory.name)
    if match:return (3,int(match[1]),1,0),True
    if directory.name=='phase_b':return (3,1,1,0),True
    return (4,0,0,0),False


def discover(source):
    directories=set()
    for path in regular_files(source):
        if path.name not in ('events.jsonl','result.json'):continue
        directory=path.parent
        if 'logs' not in directory.relative_to(source).parts:continue
        if 'history' in directory.relative_to(source).parts:continue
        directories.add(directory)
    aliases=[]
    selected=[]
    for directory in sorted(directories):
        if (directory/'turn/events.jsonl').exists():
            aliases.append({'path':str(directory.relative_to(source)),'reason':'functional turn raw child preferred'})
            continue
        if (directory/'phase_a').is_dir():
            aliases.append({'path':str(directory.relative_to(source)),'reason':'gate compatibility aggregate excluded'})
            # Include declared missing retries as unobservable turns.
            gate=read(directory/'skill_gate.json')
            retries=gate.get('skill_gate_retry_count')
            if type(retries) is int and 0<=retries<=10:
                for index in range(1,retries+1):
                    missing=directory/'retries'/f'attempt_{index:02d}'
                    if missing not in directories:selected.append(missing)
            if gate.get('skill_gate_fallback_used') is True and directory/'fallback' not in directories:
                selected.append(directory/'fallback')
            if directory/'phase_a' not in directories:selected.append(directory/'phase_a')
            continue
        if directory.name=='phase_b':
            run=directory.parent.parent.parent
            candidates=sorted((run/'steps/01').glob('attempts/*/logs/aut/turn'))
            candidates+=sorted((run/'steps/01').glob('attempts/*/logs/aut'))
            matches=[p for p in candidates if all((p/name).is_file() and (directory/name).is_file()
                      and sha(p/name)==sha(directory/name) for name in ('events.jsonl','invocation.json'))]
            if matches:
                aliases.append({'path':str(directory.relative_to(source)),
                                'reason':'phase_b aliases first functional turn','original':str(matches[0].relative_to(source))})
                continue
        selected.append(directory)
    return sorted(set(selected),key=lambda p:(rank(p)[0],str(p))),aliases


def version_for(directory, source, assertion):
    candidates=[]
    provenance='observed_runtime'
    for parent in (directory,*directory.parents):
        if not parent.is_relative_to(source):break
        for filename in ('invocation.json','sandbox_metadata.json','continuous_session.json'):
            data=read(parent/filename)
            value=data.get('codex_sandbox_version')
            if value:candidates.append(str(value).removeprefix('codex-cli ').strip())
    if not candidates:
        events,_=events_at(directory)
        ids={e.get('thread_id') for e in events if e.get('type')=='thread.started'}
        # Some probes retain the Codex state itself. Only use metadata bound
        # to this exact thread, never a version belonging to another session.
        for path in regular_files(source/'state/sessions') if (source/'state/sessions').is_dir() else []:
            if path.suffix!='.jsonl':continue
            for line in path.read_text().splitlines():
                try:item=json.loads(line)
                except ValueError:continue
                if not isinstance(item,dict):continue
                payload=item.get('payload') or {}
                if not isinstance(payload,dict):continue
                if (item.get('type')=='session_meta' and payload.get('id') in ids
                        and payload.get('cli_version')):
                    candidates.append(payload['cli_version'])
                    provenance='codex_session_metadata'
    values=set(candidates)
    if len(values)>1 or assertion and values and assertion not in values:
        return None,'version_evidence_conflict'
    # An expected version is a consistency check, not evidence of the runtime
    # that produced historical counters.
    return (next(iter(values)) if values else None),(provenance if values else 'version_unknown')


def category(directory):
    if directory.name=='phase_a':return 'initial_read'
    if directory.parent.name=='retries':return 'retry'
    if directory.name=='fallback':return 'fallback'
    return 'functional'


def recalculate(source, output, *, codex_version=None, inspect_logs=True):
    source,output=Path(source).absolute(),Path(output).absolute()
    if any(p.is_symlink() for path in (source,output) for p in (path,*path.parents)):
        raise ValueError('Source/output must use canonical paths without symlinks')
    if not source.is_dir():raise ValueError('Source directory missing')
    if output.exists() or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Output must be new and outside source')
    metadata=read(source/'manifest.json')
    verified_receipts=False
    if metadata.get('schema')=='cost266_v1':
        from .cost266.runner import verify_run
        verify_run(source,metadata['conditions'])
        verified_receipts=True
    directories,aliases=discover(source)
    if not directories:raise ValueError('No original turn logs found')
    files=regular_files(source)
    before={str(p.relative_to(source)):sha(p) for p in files}
    output.mkdir(parents=True,exist_ok=False)
    backups=[]
    for path in files:
        if (path.suffix in ('.csv','.xlsx','.eval') or path.name in
            ('metrics.json','skill_gate.json','gate_turn_metrics.json','evidenze.json')
            or path.name.endswith('_result.json')):
            relative=path.relative_to(source)
            dest=output/'previous_results'/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dest);backups.append(str(relative))
    ledger,history,items,rows=UsageLedger(),[],[],[]
    previous_stage,previous_retry={},{}
    for index,directory in enumerate(directories):
        version,version_source=version_for(directory,source,codex_version)
        order,known_order=rank(directory)
        invocation=read(directory/'invocation.json')
        expected=invocation.get('session_expected')
        gap=False
        if expected and order[0]==3 and 'steps' in directory.parts:
            previous=previous_stage.get(expected,0)
            gap=order[1]>previous+1
        if expected and order[0]==1:
            gap=order[1]>previous_retry.get(expected,0)+1
        if gap:ledger.invalidate(expected)
        item=record_turn(directory,ledger,version=version,history=history,order_verified=known_order)
        thread=item.get('thread_id')
        if order[0]==3 and thread:previous_stage[thread]=order[1]
        if order[0]==1 and thread:previous_retry[thread]=order[1]
        item.update(path=str(directory.relative_to(source)),category=category(directory),version_source=version_source)
        if gap:item['usage_diagnostics']['history']='missing_intermediate_turn'
        if version_source=='version_evidence_conflict':
            item['usage_diagnostics']['version']=version_source
        # Bind each export to the ordered source prefix, including failed turns.
        history=item['sources']
        items.append(item)
        target=output/'normalized'/directory.relative_to(source)
        save(target/'usage_accounting.json',item)
        tokens=codex_usage([{'type':'turn.completed','usage':item['usage_delta']}])
        log_root=directory.parent if directory.name=='turn' else directory
        old=read(log_root.parent.parent/'evaluation/metrics.json')
        updated={**old,'tokens':tokens,**accounting_fields(item)}
        save(target/'metrics.json',updated)
        if inspect_logs:
            from .inspect_adapter import create_inspect_eval_log
            create_inspect_eval_log(directory,f'recalculated-{index:04d}',model=metadata.get('model'),
                                    usage_accounting=item,output_path=target/'normalized.eval')
        row={'path':item['path'],'thread_id':thread,'category':item['category'],
             'usage_semantics':item['usage_semantics'],'usage_verified':item['usage_verified'],
             'diagnostics':json.dumps(item['usage_diagnostics'],sort_keys=True)}
        row.update({key:item['usage_delta'].get(key) for key in FIELDS})
        row.update({'raw_'+key:(item.get('usage_raw') or {}).get(key) for key in FIELDS})
        row['total_calculated']=tokens['total_calculated']
        rows.append(row)
    aggregate=aggregate_accounting(items)
    tokens=codex_usage([{'type':'turn.completed','usage':aggregate['usage_delta']}])
    old=read(source/'evaluation/metrics.json')
    updated={**old,'tokens':tokens,**accounting_fields(aggregate),
             'cumulative_input_tokens':tokens['input'],'cumulative_output_tokens':tokens['output']}
    groups=defaultdict(list)
    threads=defaultdict(list)
    for item in items:
        groups[item['category']].append(item)
        threads[item.get('thread_id')].append(item)
    totals=[]
    for name,parts in [('all',items),('gate',[i for i in items if i['category']!='functional']),
                       ('functional',groups['functional'])]:
        counted=aggregate_accounting(parts)
        totals.append({'category':name,'usage_verified':counted['usage_verified'],**counted['usage_delta']})
        if name!='all':
            for kind in ('input','output'):
                updated[f'{name}_{kind}_tokens']=counted['usage_delta'][kind+'_tokens'] if parts else 0
    save(output/'recalculated_metrics.json',updated)
    thread_rows=[{'thread_id':name,'usage_verified':(a:=aggregate_accounting(parts))['usage_verified'],
                  **a['usage_delta']} for name,parts in threads.items()]
    turns_frame,totals_frame,threads_frame=pd.DataFrame(rows),pd.DataFrame(totals),pd.DataFrame(thread_rows)
    turns_frame.to_csv(output/'turns.csv',index=False)
    totals_frame.to_csv(output/'totals.csv',index=False)
    with pd.ExcelWriter(output/'benchmark.xlsx',engine='openpyxl') as book:
        turns_frame.to_excel(book,sheet_name='Turns',index=False)
        totals_frame.to_excel(book,sheet_name='Totals',index=False)
        threads_frame.to_excel(book,sheet_name='Threads',index=False)
    after={str(p.relative_to(source)):sha(p) for p in regular_files(source)}
    if before!=after:raise ValueError('Source changed during recalculation; export is not verified')
    report={'schema':'token_recalculation_v1','source':str(source),'source_sha256':before,
            'source_unchanged':True,'cost266_receipts_verified':verified_receipts,
            'codex_version_assertion':codex_version,'previous_results':backups,
            'turn_count':len(items),'excluded_aliases':aliases,
            'usage_verified':aggregate['usage_verified'],'tokens':tokens,
            'diagnostics':[{'path':i['path'],**i['usage_diagnostics']} for i in items if i['usage_diagnostics']]}
    save(output/'recalculation_manifest.json',report)
    return report
