#!/usr/bin/env python3
"""CLI separata per preparazione, dry-run, esecuzione e resume COST266."""
from dataclasses import replace
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import json
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from benchmark_core.config import Config, load_config
from benchmark_core.cost266.assets import load_dataset, prepare
from benchmark_core.cost266.protocol import STRATEGIES, load_spec, EXECUTION_MODES, validate_backend
from benchmark_core.cost266.selection import resolve_selection, describe_cell
from benchmark_core.cost266.runner import execute, experiment_lock, plan, progress, _duration
from benchmark_core.report_paths import cost266_experiment, publish_cost266_report, validate_cost266_report_destination
from benchmark_core.preflight import preflight
from benchmark_core.skill_modes import SKILL_MODE_CHOICES, validate_mode_sources
from benchmark_core.prompts import PROMPT_TYPES


def main(argv=None):
    parser = argparse.ArgumentParser(description='Benchmark COST266: one-shot, incrementale isolato o continuo')
    parser.add_argument('experiment',nargs='?',type=Path,default=None)
    parser.add_argument('--config',type=Path,default=ROOT/'benchmark.yaml')
    parser.add_argument('--model',help='Modello AUT per questa esecuzione')
    parser.add_argument('--reasoning-effort',choices=('low','medium','high','xhigh'),
                        help='Livello di reasoning per questa esecuzione')
    parser.add_argument('--experiment-id',help='Identificativo separato per run e report')
    parser.add_argument('--prepare',nargs='?',type=Path,default=argparse.SUPPRESS,metavar='INPUT_DIRECTORY',
                        help='Prepara offline dai sorgenti della checkout (override: directory o COST266_INPUTS)')
    parser.add_argument('--strategy',choices=STRATEGIES)
    parser.add_argument('--execution-mode','--mode',choices=EXECUTION_MODES,
                        help='seleziona automaticamente configurazione e protocollo v1/v2')
    parser.add_argument('--skill-mode',choices=SKILL_MODE_CHOICES)
    parser.add_argument('--prompt-type',choices=PROMPT_TYPES)
    parser.add_argument('--only-replicate',type=int, help='Seleziona una ripetizione positiva, anche oltre repetitions nello YAML')
    parser.add_argument('--generation-workers',type=int,default=5,
                        help='Generazioni parallele one-shot o incrementali continue (predefinito: 5)')
    parser.add_argument('--dry-run',action='store_true')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--resume',action='store_true')
    group.add_argument('--rerun-correction',action='store_true')
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.model is not None or args.reasoning_effort is not None:
            data = deepcopy(config.data)
            if args.model is not None:
                if not args.model.strip():
                    raise ValueError('--model non può essere vuoto')
                data['aut']['model'] = args.model.strip()
            if args.reasoning_effort is not None:
                data['aut']['reasoning_effort'] = args.reasoning_effort
            config = Config(config.root, data)
        selection = resolve_selection(ROOT,config.root,args.experiment,args.execution_mode,args.strategy,loader=load_spec)
        if args.experiment_id is not None:
            import re
            if not re.fullmatch(r'[A-Za-z0-9_-]+',args.experiment_id):
                raise ValueError('--experiment-id non valido')
            selection = replace(selection, spec=replace(selection.spec, experiment_id=args.experiment_id))
        spec = selection.spec
        if args.generation_workers < 1:
            raise ValueError('--generation-workers deve essere positivo')
        if hasattr(args,'prepare'):
            if args.dry_run or args.resume or args.rerun_correction:
                raise ValueError('--prepare è separato da dry-run/resume/rerun-correction')
            with experiment_lock(config.root,spec.experiment_id):
                report = prepare(args.prepare,spec.dataset)
            print(json.dumps(report,indent=2))
            return 0
        selected = selection.selected_cells(prompt_type=args.prompt_type,skill_mode=args.skill_mode,
                                            repetition=args.only_replicate)
        if not selected:
            raise ValueError('Nessuna cella selezionata; controllare filtri/ripetizione')
        if args.execution_mode:
            for cell in selected:
                validate_backend(config,cell.skill_mode,strategy=cell.strategy,protocol=spec.protocol)
        inventory, preparation = load_dataset(spec.dataset)
        def planned():
            return [(cell,*plan(config,spec,cell,inventory,preparation,resume=args.resume,rerun=args.rerun_correction)) for cell in selected]
        if args.dry_run:
            print(f'Modello: {config.model()} | Reasoning effort: {config.reasoning_effort()}')
            for cell,action,run in planned():
                print(describe_cell(spec,cell))
                print(f'{action} {run} stages={1 if cell.strategy=="one_shot" else 6} baseline={preparation["baseline_sha256"]} oracle={preparation["correction_sha256"]}')
            return 0
        with experiment_lock(config.root,spec.experiment_id):
            decisions = planned()
            report_output = cost266_experiment(config,spec.experiment_id)
            if any(action not in ('SKIP','MISSING') for _,action,_ in decisions):
                validate_cost266_report_destination(report_output)
            if any(action in ('RUN','RESUME') for _,action,_ in decisions):
                for mode in dict.fromkeys(c.skill_mode for c,action,_ in decisions if action in ('RUN','RESUME')):
                    if config.data['aut']['agent']=='codex':
                        validate_mode_sources(config,mode)
                    preflight(config,config.data['aut']['agent'],skill_mode=mode,scenario_ids=())
            failed = False
            def publish_report(report_cells):
                started = time.monotonic()
                for cell in report_cells:
                    progress(config.root,spec.experiment_id,cell,'Generazione report XLSX/CSV avviata...')
                try:
                    publish_cost266_report(config.root,report_output)
                except BaseException as exc:
                    for cell in report_cells:
                        progress(config.root,spec.experiment_id,cell,
                                 f'ERRORE generazione report: {type(exc).__name__}: {exc}; durata: {_duration(time.monotonic()-started)}')
                    raise
                for cell in report_cells:
                    progress(config.root,spec.experiment_id,cell,
                             f'Report salvati: {report_output}; durata: {_duration(time.monotonic()-started)}')
            if args.execution_mode in ('one_shot', 'incremental_continuous'):
                checker_lock = threading.BoundedSemaphore(5)
                generation_lock = threading.BoundedSemaphore(args.generation_workers)
                active = [(cell,action,run) for cell,action,run in decisions if action not in ('SKIP','MISSING')]
                for cell,action,run in decisions:
                    if action == 'MISSING':
                        progress(config.root,spec.experiment_id,cell,f'MISSING {run}')
                    elif action == 'SKIP':
                        metadata = json.loads((run/'manifest.json').read_text())
                        progress(config.root,spec.experiment_id,cell,f'SKIP {run}: {metadata["pipeline_state"]}, task_success={metadata["task_success"]}')
                        failed |= metadata.get('task_success') is not True
                if active:
                    for cell,_,_ in active:
                        progress(config.root,spec.experiment_id,cell,f'Pianificata: {len(active)} run, fino a {min(args.generation_workers,len(active))} generazioni parallele; fino a 5 checker paralleli')
                    with ThreadPoolExecutor(max_workers=len(active)) as pool:
                        futures = {pool.submit(execute,config,spec,cell,inventory,preparation,
                                               resume=args.resume,rerun=args.rerun_correction,checker_lock=checker_lock,
                                               generation_lock=generation_lock,checker_isolated=True): cell
                                   for cell,_,_ in active}
                        for future in as_completed(futures):
                            cell = futures[future]
                            run = future.result()
                            metadata = json.loads((run/'manifest.json').read_text())
                            failed |= metadata.get('task_success') is not True
                    publish_report([cell for cell,_,_ in active])
                return int(failed)
            for cell,action,run in decisions:
                if action == 'MISSING':
                    progress(config.root,spec.experiment_id,cell,f'MISSING {run}')
                    continue
                if action != 'SKIP':
                    validate_cost266_report_destination(report_output)
                    run = execute(config,spec,cell,inventory,preparation,resume=args.resume,rerun=args.rerun_correction)
                    publish_report([cell])
                metadata = json.loads((run/'manifest.json').read_text())
                if action == 'SKIP':
                    progress(config.root,spec.experiment_id,cell,f'SKIP {run}: {metadata["pipeline_state"]}, task_success={metadata["task_success"]}')
                failed |= metadata.get('task_success') is not True
                if metadata['pipeline_state'] != 'COMPLETED' and not config.data['benchmark']['continue_on_error']:
                    break
            return int(failed)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as exc:
        if not args.dry_run and 'selected' in locals() and selected and 'spec' in locals() and 'config' in locals():
            for cell in selected:
                try:
                    progress(config.root,spec.experiment_id,cell,f'ERRORE CLI/preparazione o report: {type(exc).__name__}: {exc}')
                except OSError:
                    print(f'Errore COST266 durante la scrittura del log: {exc}',file=sys.stderr,flush=True)
        else:
            print(f'Errore COST266: {exc}',file=sys.stderr,flush=True)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
