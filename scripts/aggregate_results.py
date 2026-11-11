#!/usr/bin/env python3
from pathlib import Path
import argparse
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.aggregation import aggregate
from benchmark_core.config import load_config


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
    results = args.output or config.path(config.data["results"]["directory"])
    runs_root = args.runs or config.root / "runs"
    if not args.experiment and not args.output:
        if not runs_root.is_dir():
            parser.error(f"Directory delle run inesistente: {runs_root}")
        experiments = sorted(p.name for p in runs_root.iterdir()
                             if p.is_dir() and any(p.glob('*/*/*/*/*/r*/manifest.json')))
        if not experiments:
            parser.error("Nessun esperimento trovato; usare --output per le run legacy")
        for experiment in experiments:
            output = results / experiment
            runs, checks, summary = aggregate(runs_root, output, experiment_id=experiment)
            print(f"{experiment}: {len(runs)} run, {len(checks)} check, {len(summary)} gruppi: {output.resolve()}")
        return 0
    if args.experiment and not args.output:
        results = results / args.experiment
    runs, checks, summary = aggregate(runs_root, results, experiment_id=args.experiment)
    print(f"{len(runs)} run, {len(checks)} check, {len(summary)} gruppi; CSV e benchmark.xlsx: {results.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
