#!/usr/bin/env python3
"""Regenerate COST266 reports from saved runs, without executing the AUT."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmark_core.config import load_config
from benchmark_core.cost266.runner import experiment_lock
from benchmark_core.report_paths import cost266_experiment, publish_cost266_report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'benchmark.yaml')
    parser.add_argument('--experiment',required=True)
    parser.add_argument('--output',type=Path,help='Directory di destinazione con nome uguale all’experiment ID')
    args=parser.parse_args(argv)
    try:
        config=load_config(args.config)
        default_output=cost266_experiment(config,args.experiment)
        output=args.output if args.output is not None else default_output
        if output.name!=args.experiment:raise ValueError('Il nome della directory output deve essere l’experiment ID')
        if not list((config.root/'runs'/args.experiment).glob('*/*/cost266/*/*/*/r*/manifest.json')):
            raise ValueError('Nessuna run COST266 trovata per questo esperimento')
        with experiment_lock(config.root,args.experiment):
            frames=publish_cost266_report(config.root,output)
        print(f'{args.experiment}: {len(frames[0])} osservazioni; report: {output}')
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(f'Errore aggregazione COST266: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
