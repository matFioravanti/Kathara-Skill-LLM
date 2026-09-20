#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark_core.agent_factory import AGENTS
from benchmark_core.aggregation import aggregate
from benchmark_core.config import load_config, verify_skills
from benchmark_core.pipeline import run_one
from benchmark_core.preflight import preflight
from benchmark_core.scenario_loader import discover_scenarios


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Codex CLI locale / Kathara DNS-web")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.yaml")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scenario")
    group.add_argument("--all", action="store_true")
    group.add_argument("--check-skills", action="store_true")
    group.add_argument("--preflight", action="store_true")
    parser.add_argument("--agent", choices=list(AGENTS))
    parser.add_argument("--repetitions", type=int)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.check_skills:
        for name, path in verify_skills(config).items():
            print(f"OK {name}: {path}")
        return 0
    agent = args.agent or config.data["aut"]["agent"]
    repetitions = args.repetitions if args.repetitions is not None else config.data["benchmark"]["repetitions"]
    if repetitions < 1:
        parser.error("--repetitions deve essere positivo")
    if not (args.scenario or args.all or args.preflight):
        parser.error("specificare --scenario, --all, --check-skills o --preflight")
    scenarios = discover_scenarios(config.root / "scenarios")
    if args.scenario and args.scenario not in scenarios:
        parser.error(f"Scenario non trovato: {args.scenario}; disponibili: {', '.join(scenarios)}")
    if not scenarios:
        raise ValueError("Nessuno scenario trovato.")
    preflight(config, agent)
    if args.preflight:
        print("Prerequisiti disponibili; nessuna chiamata modello eseguita.")
        return 0
    selected = [scenarios[args.scenario]] if args.scenario else list(scenarios.values())
    failed = False
    try:
        for scenario in selected:
            for repetition in range(1, repetitions + 1):
                try:
                    run = run_one(config, scenario, agent, repetition)
                    metadata = json.loads((run / "manifest.json").read_text())
                    run_failed = metadata["pipeline_state"] != "COMPLETED"
                except Exception as exc:
                    print(f"Errore preparazione run {scenario.scenario_id}: {exc}", file=sys.stderr)
                    run_failed = True
                failed |= run_failed
                if run_failed and not config.data["benchmark"]["continue_on_error"]:
                    return 1
    finally:
        aggregate(config.root / "runs", config.path(config.data["results"]["directory"]))
    # Un task scorretto con checker completato è un risultato valido, non un errore CLI.
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        raise SystemExit(1)
