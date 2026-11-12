#!/usr/bin/env python3
"""Produce an offline comparison across COST266 experiment IDs."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmark_core.cost266_comparative_report import compare
from benchmark_core.config import load_config
from benchmark_core.report_paths import cost266_comparison


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT,help='Root containing runs/')
    parser.add_argument('--experiments',nargs='+')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--comparison-id',default='comparison')
    args=parser.parse_args(argv)
    try:
        if args.output:
            output=args.output if args.output.is_absolute() else args.root/args.output
        else:
            config=load_config(args.config or args.root/'benchmark.yaml')
            output=cost266_comparison(config,args.comparison_id)
        manifest=compare(args.root,output,args.experiments)
        print(f"Osservazioni: {manifest['observations_read']}; coppie: {manifest['valid_pairs']}; terne: {manifest['valid_triples']}")
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(f'Errore confronto COST266: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
