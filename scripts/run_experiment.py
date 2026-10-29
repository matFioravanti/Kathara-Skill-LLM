#!/usr/bin/env python3
"""Execute explicitly assigned DNS tasks, or display a static execution plan."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark_core.aggregation import aggregate
from benchmark_core.config import load_config
from benchmark_core.correction_input import correction_path
from benchmark_core.experiment import (analyse_existing_runs, build_run_matrix,
    compute_resume_plan, load_experiment, validate_experiment_prerequisites)
from benchmark_core.pipeline import reevaluate_run, run_one
from benchmark_core.preflight import preflight
from benchmark_core.prompts import PROMPT_TYPES, resolve_prompt
from benchmark_core.scenario_loader import discover_scenarios
from benchmark_core.skill_modes import SKILL_MODE_CHOICES, validate_mode_sources
from benchmark_core.task_catalog import TASK_LEVELS


def main(argv=None):
    parser = argparse.ArgumentParser(description="Esegue un esperimento DNS con assegnazioni esplicite")
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.yaml")
    parser.add_argument("--lab", "--filter-scenario", dest="lab")
    parser.add_argument("--dns-tree")
    parser.add_argument("--task-level", choices=TASK_LEVELS)
    parser.add_argument("--prompt-type", "--filter-prompt", dest="prompt_type", choices=PROMPT_TYPES)
    parser.add_argument("--skill-mode", "--filter-skill-mode", dest="skill_mode", choices=SKILL_MODE_CHOICES)
    parser.add_argument("--repetitions", type=int)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--resume", action="store_true")
    modes.add_argument("--rerun-correction", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        spec = load_experiment(args.experiment)
        if not spec.assignments:
            raise ValueError("L'esperimento legacy usa scenarios: definire assignments espliciti prima dell'esecuzione")
        assignments = tuple(a for a in spec.assignments if
            (not args.lab or a.lab_id == args.lab) and
            (not args.dns_tree or a.dns_tree_id == args.dns_tree) and
            (not args.task_level or a.task_level == args.task_level))
        prompts = tuple(p for p in spec.prompt_types if not args.prompt_type or p == args.prompt_type)
        skills = tuple(s for s in spec.skill_modes if not args.skill_mode or s == args.skill_mode)
        if not assignments or not prompts or not skills:
            raise ValueError("Nessuna combinazione abilitata corrisponde ai filtri")
        if args.repetitions is not None and args.repetitions < 1:
            raise ValueError("repetitions deve essere positivo")
        if args.rerun_correction and args.repetitions is not None:
            raise ValueError("--repetitions non si applica alla rivalutazione")
        spec = replace(spec, assignments=assignments, scenarios=tuple(dict.fromkeys(a.lab_id for a in assignments)),
                       prompt_types=prompts, skill_modes=skills,
                       repetitions=args.repetitions or spec.repetitions)
        agent = config.data["aut"]["agent"]
        if agent != "codex" and any(mode != "no_skill" for mode in skills):
            raise ValueError("Antigravity usa solo no_skill nel protocollo esistente")
        labs = discover_scenarios(config.root / "scenarios")
        validate_experiment_prerequisites(spec, config, labs)
        if agent == "codex":
            for mode in skills:
                validate_mode_sources(config, mode)
        elif agent == "antigravity":
            from benchmark_core.config import verify_skills
            if not config.data.get("aut", {}).get("dns_skill"):
                raise ValueError("La configurazione Antigravity richiede aut.dns_skill")
            verify_skills(config, ("kathara-dns",))
        runs_root = config.root / "runs"
        analyses = analyse_existing_runs(runs_root, spec)
        decisions = compute_resume_plan(spec, analyses)
        if args.rerun_correction:
            candidates = [r.run for analysis in analyses.values() for r in analysis.all_runs]
            if not candidates:
                raise ValueError("Nessuna run corrispondente da rivalutare")
            for run in candidates:
                print(f"RERUN {run.relative_to(config.root)}")
            if args.dry_run:
                return 0
            failed = False
            for run in candidates:
                try:
                    reevaluate_run(config, run)
                    failed |= json.loads((run / "manifest.json").read_text()).get("pipeline_state") != "COMPLETED"
                except Exception as exc:
                    print(f"Errore rivalutazione {run}: {exc}", file=sys.stderr)
                    failed = True
            aggregate(runs_root, config.path(config.data["results"]["directory"]))
            return int(failed)
        if not args.resume:
            from benchmark_core.experiment import ResumeDecision
            decisions = [ResumeDecision(c, True, "requested") for c in build_run_matrix(spec)]
        selected = [d for d in decisions if d.should_run]
        print(f"Esperimento {spec.experiment_id}: {len(decisions)} osservazioni, {len(selected)} da eseguire")
        if args.dry_run:
            for d in decisions:
                c = d.cell
                print(f"{'RUN' if d.should_run else 'SKIP'} {c.lab_id}/{c.dns_tree_id}/{c.task_level}/{c.prompt_type}/{c.skill_mode} rep={c.replicate} prompt={resolve_prompt(config.root, c.dns_tree_id, c.prompt_type, c.task_level).relative_to(config.root)} correction={correction_path(config.root, c.assignment).relative_to(config.root)}")
            return 0
        if not selected:
            return 0
        preflight(config, agent, skill_mode=skills[0] if agent == "codex" else None, assignments=assignments)
        failed = False
        try:
            for decision in selected:
                c = decision.cell
                try:
                    run = run_one(config, labs[c.lab_id], agent, c.prompt_type, skill_mode=c.skill_mode,
                                  experiment_id=c.experiment_id, replicate=c.replicate, assignment=c.assignment)
                    state = json.loads((run / "manifest.json").read_text()).get("pipeline_state")
                    print(f"{run.relative_to(config.root)}: {state}")
                    if state != "COMPLETED":
                        failed = True
                except Exception as exc:
                    print(f"Errore esecuzione {c}: {exc}", file=sys.stderr)
                    failed = True
                if failed and not config.data["benchmark"]["continue_on_error"]:
                    break
        finally:
            aggregate(runs_root, config.path(config.data["results"]["directory"]))
        return int(failed)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
