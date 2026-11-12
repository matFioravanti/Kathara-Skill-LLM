#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.aggregation import aggregate
from benchmark_core.config import load_config
from benchmark_core.report_paths import general_root, general_legacy, general_experiment, is_cost266_manifest


def _has_general_observation(directory,pattern):
    for manifest in directory.glob(pattern):
        data=json.loads(manifest.read_text())
        if not is_cost266_manifest(data):return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Rigenera i CSV dai dati grezzi in runs/")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.yaml")
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--experiment", help="ID esperimento da aggregare")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.experiment and not re.fullmatch(r"[A-Za-z0-9_-]+", args.experiment):
        parser.error("ID esperimento non valido")
    results = args.output or general_root(config)
    runs_root = args.runs or config.root / "runs"
    if not args.experiment and not args.output:
        if not runs_root.is_dir():
            parser.error(f"Directory delle run inesistente: {runs_root}")
        experiments = sorted(p.name for p in runs_root.iterdir()
                             if p.is_dir() and _has_general_observation(p,'*/*/*/*/*/r*/manifest.json'))
        legacy = any(p.is_dir() and _has_general_observation(p,'*/*/r*/manifest.json') for p in runs_root.iterdir())
        if not experiments and not legacy:
            parser.error("Nessun esperimento generale o run legacy trovato")
        outputs=[(experiment,general_experiment(config,experiment)) for experiment in experiments]
        for experiment,output in outputs:
            runs, checks, summary = aggregate(runs_root, output, experiment_id=experiment)
            print(f"{experiment}: {len(runs)} run, {len(checks)} check, {len(summary)} gruppi: {output.resolve()}")
        if legacy:
            output=general_legacy(config)
            runs, checks, summary=aggregate(runs_root,output,legacy_only=True)
            print(f"_legacy: {len(runs)} run, {len(checks)} check, {len(summary)} gruppi: {output.resolve()}")
        return 0
    if args.experiment and not args.output:
        results = general_experiment(config,args.experiment)
    runs, checks, summary = aggregate(runs_root, results, experiment_id=args.experiment)
    print(f"{len(runs)} run, {len(checks)} check, {len(summary)} gruppi; CSV e benchmark.xlsx: {results.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
