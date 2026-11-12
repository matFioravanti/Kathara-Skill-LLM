#!/usr/bin/env python3
"""Recalculate token metrics from immutable original logs; never invokes AUT."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmark_core.token_recalculation import recalculate


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path,help='Original COST266 run or probe directory')
    parser.add_argument('--output',required=True,type=Path,help='New directory outside source')
    parser.add_argument('--codex-version',help='Expected version; requires matching runtime evidence and never overrides it')
    args=parser.parse_args(argv)
    try:
        result=recalculate(args.source,args.output,codex_version=args.codex_version)
        print(json.dumps({key:result[key] for key in ('turn_count','usage_verified','tokens','source_unchanged')},indent=2))
        return 0 if result['usage_verified'] else 2
    except (OSError,ValueError,KeyError) as exc:
        print('Token recalculation failed: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
