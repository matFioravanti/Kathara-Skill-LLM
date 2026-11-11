"""Report COST266 basati sui normalizzatori e writer dell'aggregazione esistente."""
from pathlib import Path
import json

import pandas as pd

from ..aggregation import (RUN_COLUMNS, CHECK_COLUMNS, SUMMARY_COLUMNS, _run_record,
                           _check_records, _summary_records, _atomic_csv, _write_excel)
from ..workspace import write_json
from .protocol import safe_path
from .runner import read_json, verify_run

EXTRA = ['strategy','stage_count','completed_stages','aut_calls','sandbox_count','cumulative_agent_seconds',
         'cumulative_input_tokens','cumulative_output_tokens','final_pass_rate','pairing_sha256']
PROPERTY_TYPES = ('soa','authority','apex_ns','ns_address','delegation_glue','record','client_resolver','client_resolution')
PROPERTY_COLUMNS = [f'{kind}_{field}' for kind in PROPERTY_TYPES for field in ('passed','observed','expected','pass_rate','coverage_complete')]


def aggregate_cost266(root: Path, output: Path):
    safe_path(output)
    if output == root or output.is_relative_to(root/'runs') or output.is_relative_to(root/'experiments'):
        raise ValueError('Directory report non consentita')
    records, checks, phases = [], [], []
    seen = set()
    for path in sorted((root/'runs').glob('*/*/*/cost266/*/*/*/r*/manifest.json')):
        metadata = read_json(path)
        if metadata.get('schema') != 'cost266_v1':
            continue
        if metadata['experiment_id'] != output.name:
            continue
        identity = tuple(metadata[k] for k in ('experiment_id','lab_id','dns_tree_id','prompt_type','strategy','skill_mode','replicate'))
        if identity in seen:
            raise ValueError(f'Osservazione COST266 duplicata: {identity}')
        seen.add(identity)
        run = path.parent
        verify_run(run,metadata['conditions'])
        metrics = read_json(run/'evaluation/metrics.json') if (run/'evaluation/metrics.json').exists() else {}
        record = _run_record(metrics, metadata)
        record['_metrics'] = metrics
        record['experimental_fingerprint'] = metadata['conditions_sha256']
        record['conditions_status'] = 'verified_cost266_protocol'
        # _run_record mantiene conteggi parziali e semantiche storiche; _check_records
        # riconcilia i conteggi con i CSV reali del checker.
        check_rows = _check_records(run,record)
        record.update({key:metrics.get(key,metadata.get(key)) for key in EXTRA})
        for kind in PROPERTY_TYPES:
            property_metrics = (metrics.get('dns_property_checks') or {}).get(kind) or {}
            record.update({f'{kind}_{field}':property_metrics.get(field) for field in ('passed','observed','expected','pass_rate','coverage_complete')})
        record['run_directory'] = str(run.relative_to(root/'runs'))
        record['observation_selection'] = 'included' if record['_evaluated'] else 'unevaluated'
        records.append(record)
        checks += [{**row,'strategy':metadata['strategy']} for row in check_rows]
        for metric_path in sorted((run/'steps').glob('*/attempts/*/evaluation/metrics.json')):
            item = read_json(metric_path)
            stage = read_json(metric_path.parents[1]/'manifest.json')
            phases.append({'ID':stage['run_id'],'parent_run_id':metadata['run_id'],'strategy':metadata['strategy'],
                'prompt_type':metadata['prompt_type'],'skill_mode':metadata['skill_mode'],'replicate':metadata['replicate'],
                'stage_index':item['stage_index'],'attempt':item['attempt'],'status':item['status'],
                'agent_seconds':item['timing']['agent_seconds'],'wall_seconds':item['timing']['total_seconds'],
                'input_tokens':item['tokens']['input'],'output_tokens':item['tokens']['output'],
                'reasoning_tokens':item['tokens']['reasoning'],'cached_input_tokens':item['tokens']['cached_input'],
                'skill_gate_status':item.get('skill_gate_status'),'prompt_sent_sha256':stage.get('prompt_sent_sha256'),
                'static_validation_seconds':item.get('static_validation_seconds'),
                'static_regressions':';'.join(item.get('static_regressions') or []),
                'error':stage.get('pipeline_error')})
    summaries = []
    for strategy in ('one_shot','incremental'):
        summaries += [{**row,'strategy':strategy} for row in _summary_records([r for r in records if r['strategy']==strategy])]
    pairs = []
    grouped = {}
    for record in records:
        grouped.setdefault(record['pairing_sha256'],{})[record['strategy']] = record
    for key, group in sorted(grouped.items()):
        one, inc = group.get('one_shot'), group.get('incremental')
        evaluated = bool(one and inc and one['_evaluated'] and inc['_evaluated'])
        row = {'pairing_sha256':key,'one_shot_id':one['ID'] if one else None,
               'incremental_id':inc['ID'] if inc else None,'comparable_evaluated_pair':evaluated,
               'reason':None if evaluated else 'Coppia mancante o valutazione finale incompleta'}
        for field in ('final_pass_rate','cumulative_agent_seconds','cumulative_input_tokens','cumulative_output_tokens'):
            a,b = (one.get(field) if one else None),(inc.get(field) if inc else None)
            row['one_shot_'+field],row['incremental_'+field] = a,b
            row['delta_'+field] = b-a if evaluated and a is not None and b is not None else None
        pairs.append(row)
    frames = (pd.DataFrame(records,columns=list(dict.fromkeys(RUN_COLUMNS+EXTRA+PROPERTY_COLUMNS))),
              pd.DataFrame(checks,columns=CHECK_COLUMNS+['strategy']),
              pd.DataFrame(summaries,columns=SUMMARY_COLUMNS+['strategy']))
    extras = {'Stages':pd.DataFrame(phases),'Pairs':pd.DataFrame(pairs)}
    output.mkdir(parents=True,exist_ok=True)
    for name, frame in [*zip(('runs','checks','summary'),frames),('stages',extras['Stages']),('pairs',extras['Pairs'])]:
        _atomic_csv(output/(name+'.csv'),frame)
    _write_excel(output/'benchmark.xlsx',frames,extra_frames=extras)
    write_json(output/'report_manifest.json',{'schema':'cost266_v1','logical_observations':len(records),
        'duplicate_policy':'reject','legacy_columns_preserved':True})
    return frames
