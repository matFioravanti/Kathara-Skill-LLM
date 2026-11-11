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
from benchmark_core.cost266.protocol import STRATEGIES, cells, load_spec
from benchmark_core.cost266.runner import execute, experiment_lock, plan
from benchmark_core.cost266.reports import aggregate_cost266
from benchmark_core.preflight import preflight
from benchmark_core.skill_modes import SKILL_MODE_CHOICES, validate_mode_sources
from benchmark_core.prompts import PROMPT_TYPES


def main(argv=None):
    parser = argparse.ArgumentParser(description='Benchmark COST266 incremental_no_feedback')
    parser.add_argument('experiment',nargs='?',type=Path,default=ROOT/'experiments/cost266.yaml')
    parser.add_argument('--config',type=Path,default=ROOT/'benchmark.yaml')
    parser.add_argument('--prepare',nargs='?',type=Path,default=argparse.SUPPRESS,metavar='INPUT_DIRECTORY',
                        help='Prepara offline dai sorgenti della checkout (override: directory o COST266_INPUTS)')
    parser.add_argument('--strategy',choices=STRATEGIES)
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
        spec = load_spec(args.experiment,config.root)
        if hasattr(args,'prepare'):
            if args.dry_run or args.resume or args.rerun_correction:
                raise ValueError('--prepare è separato da dry-run/resume/rerun-correction')
            with experiment_lock(config.root,spec.experiment_id):
                report = prepare(args.prepare,spec.dataset)
            print(json.dumps(report,indent=2))
            return 0
        inventory, preparation = load_dataset(spec.dataset)
        selected = [cell for cell in cells(spec) if
            (not args.strategy or cell.strategy==args.strategy) and
            (not args.skill_mode or cell.skill_mode==args.skill_mode) and
            (not args.prompt_type or cell.prompt_type==args.prompt_type) and
            (args.only_replicate is None or cell.repetition==args.only_replicate)]
        if not selected:
            raise ValueError('Nessuna cella selezionata; controllare filtri/ripetizione')
        def planned():
            return [(cell,*plan(config,spec,cell,inventory,preparation,resume=args.resume,rerun=args.rerun_correction)) for cell in selected]
        if args.dry_run:
            for cell,action,run in planned():
                print(f'{action} {cell.relative} stages={1 if cell.strategy=="one_shot" else 6} baseline={preparation["baseline_sha256"]} oracle={preparation["correction_sha256"]}')
            return 0
        with experiment_lock(config.root,spec.experiment_id):
            decisions = planned()
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
                    run = execute(config,spec,cell,inventory,preparation,resume=args.resume,rerun=args.rerun_correction)
                    aggregate_cost266(config.root,config.path(config.data['results']['directory'])/spec.experiment_id)
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
