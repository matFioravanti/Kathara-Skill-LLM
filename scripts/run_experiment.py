#!/usr/bin/env python3
"""Execute explicitly assigned DNS tasks, or display a static execution plan."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import hashlib
import tempfile
import fcntl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark_core.aggregation import aggregate, validate_report_destination
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
from benchmark_core.report_paths import general_experiment


def _notify_benchmark_finished():
    """Play a best-effort notification without waiting for audio playback."""
    if sys.platform != "darwin":
        return
    try:
        subprocess.Popen(
            ["/usr/bin/afplay", "/System/Library/Sounds/Glass.aiff"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        # A notification must never change the benchmark's result.
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Esegue un esperimento DNS con assegnazioni esplicite")
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.yaml")
    parser.add_argument("--report-output", type=Path, help="directory per le nuove generazioni di report")
    parser.add_argument("--lab", "--filter-scenario", dest="lab")
    parser.add_argument("--dns-tree")
    parser.add_argument("--task-level", choices=TASK_LEVELS)
    parser.add_argument("--prompt-type", "--filter-prompt", dest="prompt_type", choices=PROMPT_TYPES)
    parser.add_argument("--skill-mode", "--filter-skill-mode", dest="skill_mode", choices=SKILL_MODE_CHOICES)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--only-replicate", type=int, metavar="N",
                        help="seleziona soltanto la ripetizione logica N")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--resume", action="store_true")
    modes.add_argument("--rerun-correction", action="store_true")
    parser.add_argument("--resume-allow-unverified", action="store_true",
                        help="consenti il riuso di manifest storici senza fingerprint completa, se i campi disponibili coincidono")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    benchmark_started = False
    experiment_lock = None
    try:
        config = load_config(args.config)
        spec = load_experiment(args.experiment)
        if not args.dry_run:
            # Lock the entire experiment before planning, so two launchers cannot
            # both plan the same missing logical observation and then execute it.
            lock_root = Path(tempfile.gettempdir()) / 'kathara-experiment-locks'
            lock_root.mkdir(parents=True, exist_ok=True)
            lock_id = hashlib.sha256(f'{config.root.resolve()}\0{spec.experiment_id}'.encode()).hexdigest()
            experiment_lock = (lock_root / f'{lock_id}.lock').open('a+')
            try:
                fcntl.flock(experiment_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(f"Esperimento già in esecuzione: {spec.experiment_id}") from exc
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
        if args.rerun_correction and args.only_replicate is not None:
            raise ValueError("--only-replicate non si applica alla rivalutazione")
        if args.resume_allow_unverified and not args.resume:
            raise ValueError("--resume-allow-unverified richiede --resume")
        spec = replace(spec, assignments=assignments, scenarios=tuple(dict.fromkeys(a.lab_id for a in assignments)),
                       prompt_types=prompts, skill_modes=skills,
                       repetitions=args.repetitions or spec.repetitions)
        if args.only_replicate is not None and not 1 <= args.only_replicate <= spec.repetitions:
            raise ValueError(f"--only-replicate deve essere compreso tra 1 e {spec.repetitions}")
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
        report_output = (args.report_output or
                         general_experiment(config, spec.experiment_id)).resolve()
        if report_output == config.root or any(report_output.is_relative_to(config.root / name)
                                               for name in ('runs', 'scenarios', 'skills', 'prompt')):
            raise ValueError(f"Directory report non consentita: {report_output}")
        def update_reports():
            print(f"Aggiornamento report di {spec.experiment_id} in {report_output}...", flush=True)
            aggregate(runs_root, report_output, experiment_id=spec.experiment_id)
            print("Report aggiornati.", flush=True)
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
            validate_report_destination(report_output)
            benchmark_started = True
            failed = False
            for run in candidates:
                try:
                    reevaluate_run(config, run)
                    failed |= json.loads((run / "manifest.json").read_text()).get("pipeline_state") != "COMPLETED"
                except Exception as exc:
                    print(f"Errore rivalutazione {run}: {exc}", file=sys.stderr)
                    failed = True
                finally:
                    update_reports()
            return int(failed)
        if not args.resume:
            from benchmark_core.experiment import ResumeDecision
            decisions = [ResumeDecision(c, True, "requested") for c in build_run_matrix(spec)]
        if args.only_replicate is not None:
            decisions = [d for d in decisions if d.cell.replicate == args.only_replicate]
        conflicts = {}
        if args.resume:
            from benchmark_core.experiment import completed_artifact_error
            from benchmark_core.fingerprint import conditions, compare
            for d in decisions:
                c = d.cell
                key = (c.lab_id, c.dns_tree_id, c.task_level, c.prompt_type, c.skill_mode)
                existing = [r for r in analyses[key].all_runs if r.replicate == c.replicate]
                completed = [r for r in existing if r.is_completed]
                if len(completed) > 1:
                    conflicts[c] = 'osservazioni COMPLETED duplicate: ' + ', '.join(str(r.run) for r in completed)
                elif completed:
                    run = completed[0]
                    error = completed_artifact_error(run)
                    if error:
                        conflicts[c] = 'artefatti incompleti o non validi: ' + error
                    else:
                        expected = conditions(config, labs[c.lab_id], c.prompt_type, c.skill_mode, c.assignment)
                        comparison, reasons = compare(run.manifest, expected)
                        if comparison == 'conflict' or (comparison == 'unverified' and not args.resume_allow_unverified):
                            conflicts[c] = f'condizioni {comparison}: {", ".join(reasons)} ({run.run})'
                        elif comparison == 'unverified':
                            print(f'AVVISO: condizioni storiche non verificabili: {run.run}')
                else:
                    interrupted = [r for r in existing if r.pipeline_state in ('PENDING', 'AUT_RUNNING', 'AUT_COMPLETED', 'FINALIZING') or
                                   (r.pipeline_state in ('CHECKER_FAILED', 'CORRECTION_INVALID', 'CORRECTION_MISSING') and r.manifest.get('aut_execution_success') is True)]
                    if interrupted:
                        conflicts[c] = 'run interrotta o valutazione recuperabile; esaminare prima di rilanciare: ' + ', '.join(str(r.run) for r in interrupted)
            for cell, reason in conflicts.items():
                print(f'CONFLICT {cell.lab_id}/{cell.dns_tree_id}/{cell.task_level}/{cell.prompt_type}/{cell.skill_mode} rep={cell.replicate}: {reason}', file=sys.stderr)
        selected = [d for d in decisions if d.should_run and d.cell not in conflicts]
        print(f"Esperimento {spec.experiment_id}: {len(decisions)} osservazioni, {len(selected)} da eseguire, {len(conflicts)} conflitti")
        if args.dry_run:
            for d in decisions:
                c = d.cell
                print(f"{'CONFLICT' if c in conflicts else 'RUN' if d.should_run else 'SKIP'} {c.lab_id}/{c.dns_tree_id}/{c.task_level}/{c.prompt_type}/{c.skill_mode} rep={c.replicate} prompt={resolve_prompt(config.root, c.dns_tree_id, c.prompt_type, c.task_level).relative_to(config.root)} correction={correction_path(config.root, c.assignment).relative_to(config.root)}")
            return int(bool(conflicts))
        if conflicts:
            return 1
        if not selected:
            return 0
        validate_report_destination(report_output)
        preflight(config, agent, skill_mode=skills[0] if agent == "codex" else None, assignments=assignments)
        benchmark_started = True
        failed = False
        needs_aggregation = False
        try:
            for decision in selected:
                c = decision.cell
                needs_aggregation = True
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
                needs_aggregation = False
                update_reports()
                if failed and not config.data["benchmark"]["continue_on_error"]:
                    break
        finally:
            pending = sys.exc_info()[1]
            try:
                if needs_aggregation:
                    update_reports()
            except Exception as exc:
                if pending is None:
                    raise
                print(f"Errore aggiuntivo aggregazione: {exc}", file=sys.stderr)
        return int(failed)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1
    finally:
        if experiment_lock is not None:
            experiment_lock.close()
        if benchmark_started:
            _notify_benchmark_finished()


if __name__ == "__main__":
    raise SystemExit(main())
