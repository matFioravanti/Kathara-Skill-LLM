#!/usr/bin/env python3
"""CLI separata per preparazione, dry-run, esecuzione e resume COST266."""
from dataclasses import replace
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from benchmark_core.config import load_config
from benchmark_core.cost266.assets import load_dataset, prepare
from benchmark_core.cost266.protocol import STRATEGIES, load_spec, EXECUTION_MODES, validate_backend
from benchmark_core.cost266.selection import resolve_selection, describe_cell
from benchmark_core.cost266.runner import execute, experiment_lock, plan
from benchmark_core.report_paths import cost266_experiment, publish_cost266_report, validate_cost266_report_destination
from benchmark_core.preflight import preflight
from benchmark_core.skill_modes import SKILL_MODE_CHOICES, validate_mode_sources
from benchmark_core.prompts import PROMPT_TYPES


def main(argv=None):
    parser = argparse.ArgumentParser(description='Benchmark COST266: one-shot, incrementale isolato o continuo')
    parser.add_argument('experiment',nargs='?',type=Path,default=None)
    parser.add_argument('--config',type=Path,default=ROOT/'benchmark.yaml')
    parser.add_argument('--prepare',nargs='?',type=Path,default=argparse.SUPPRESS,metavar='INPUT_DIRECTORY',
                        help='Prepara offline dai sorgenti della checkout (override: directory o COST266_INPUTS)')
    parser.add_argument('--strategy',choices=STRATEGIES)
    parser.add_argument('--execution-mode','--mode',choices=EXECUTION_MODES,
                        help='seleziona automaticamente configurazione e protocollo v1/v2')
    parser.add_argument('--skill-mode',choices=SKILL_MODE_CHOICES)
    parser.add_argument('--prompt-type',choices=PROMPT_TYPES)
    parser.add_argument('--only-replicate',type=int)
    parser.add_argument('--dry-run',action='store_true')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--resume',action='store_true')
    group.add_argument('--rerun-correction',action='store_true')
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        selection = resolve_selection(ROOT,config.root,args.experiment,args.execution_mode,args.strategy,loader=load_spec)
        spec = selection.spec
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
            for cell,action,run in planned():
                print(describe_cell(spec,cell))
                print(f'{action} {cell.relative} stages={1 if cell.strategy=="one_shot" else 6} baseline={preparation["baseline_sha256"]} oracle={preparation["correction_sha256"]}')
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
            for cell,action,run in decisions:
                if action == 'MISSING':
                    print(f'MISSING {cell.relative}')
                    continue
                if action != 'SKIP':
                    validate_cost266_report_destination(report_output)
                    run = execute(config,spec,cell,inventory,preparation,resume=args.resume,rerun=args.rerun_correction)
                    publish_cost266_report(config.root,report_output)
                metadata = json.loads((run/'manifest.json').read_text())
                print(f'{cell.relative}: {metadata["pipeline_state"]}, task_success={metadata["task_success"]}')
                failed |= metadata.get('task_success') is not True
                if metadata['pipeline_state'] != 'COMPLETED' and not config.data['benchmark']['continue_on_error']:
                    break
            return int(failed)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as exc:
        print(f'Errore COST266: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
