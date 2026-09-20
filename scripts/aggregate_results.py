#!/usr/bin/env python3
from pathlib import Path
import argparse
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
    args = parser.parse_args()
    config = load_config(args.config)
    results = args.output or config.path(config.data["results"]["directory"])
    summary, detailed = aggregate(args.runs or config.root / "runs", results)
    print(f"{len(summary)} run, {len(detailed)} check: {results.resolve()}")
    if not summary.empty and summary["aggregation_error"].notna().any():
        print("Artefatti non interpretabili: vedere aggregation_error nel CSV.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
