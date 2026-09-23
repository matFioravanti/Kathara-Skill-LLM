#!/usr/bin/env python3
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.analysis import analyze
from benchmark_core.config import load_config


def main():
    parser = argparse.ArgumentParser(description="Analisi descrittiva del benchmark")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.yaml")
    parser.add_argument("--results", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    results = args.results or config.path(config.data["results"]["directory"])
    output = analyze(results)
    print(output.to_string(index=False))


if __name__ == "__main__":
    main()
