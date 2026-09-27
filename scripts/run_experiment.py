#!/usr/bin/env python3
"""
Orchestratore per experiment multi-scenario.

Uso:
    python scripts/run_experiment.py experiments/thesis_final.yaml
    python scripts/run_experiment.py experiments/thesis_final.yaml --resume
    python scripts/run_experiment.py experiments/thesis_final.yaml --rerun-correction
    python scripts/run_experiment.py experiments/thesis_final.yaml --rerun-correction \\
        --filter-scenario Lab_01 --filter-prompt T1 --filter-skill-mode no_skill

L'orchestratore esegue sequenzialmente tutte le combinazioni definite nell'experiment,
riutilizzando run_one() e reevaluate_run() senza duplicare la logica di pipeline.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark_core.agent_factory import AGENTS
from benchmark_core.aggregation import aggregate
from benchmark_core.config import load_config
from benchmark_core.experiment import (
    ExperimentSpec,
    analyse_existing_runs,
    build_run_matrix,
    compute_resume_plan,
    compute_summary,
    load_experiment,
    validate_experiment_prerequisites,
)
from benchmark_core.pipeline import reevaluate_run, run_one
from benchmark_core.preflight import preflight
from benchmark_core.scenario_loader import discover_scenarios
from benchmark_core.skill_modes import SKILL_MODE_CHOICES, mode_details
from benchmark_core import terminal_ui


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_rerun_runs(
    spec: ExperimentSpec,
    runs_root: Path,
    filter_scenario: str | None,
    filter_prompt: str | None,
    filter_skill_mode: str | None,
) -> list[Path]:
    """Raccoglie i path delle run esistenti per il --rerun-correction."""
    candidates: list[Path] = []
    for scenario_id in spec.scenarios:
        if filter_scenario and scenario_id != filter_scenario:
            continue
        for prompt_type in spec.prompt_types:
            if filter_prompt and prompt_type != filter_prompt:
                continue
            for skill_mode in spec.skill_modes:
                if filter_skill_mode and skill_mode != filter_skill_mode:
                    continue
                mode_root = runs_root / scenario_id / prompt_type / skill_mode
                if not mode_root.is_dir():
                    continue
                for run_dir in sorted(mode_root.iterdir(), key=lambda p: p.name):
                    if not run_dir.is_dir():
                        continue
                    if not re.fullmatch(r"r\d{3,}", run_dir.name):
                        continue
                    manifest_path = run_dir / "manifest.json"
                    if not manifest_path.is_file():
                        continue
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    run_exp = manifest.get("experiment_id")
                    if run_exp is not None and run_exp != spec.experiment_id:
                        continue
                    candidates.append(run_dir)
    return candidates


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Orchestratore experiment Kathara Skill Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("experiment", type=Path,
                        help="Percorso del file experiment.yaml (es. experiments/thesis_final.yaml)")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.yaml",
                        help="Configurazione benchmark (default: benchmark.yaml)")
    parser.add_argument("--resume", action="store_true",
                        help="Salta le replicate già completate con successo")
    parser.add_argument("--rerun-correction", action="store_true",
                        help="Rivaluta le run esistenti senza eseguire nuovi AUT")
    parser.add_argument("--filter-scenario",
                        help="Limita --rerun-correction a questo scenario")
    parser.add_argument("--filter-prompt", dest="filter_prompt",
                        help="Limita --rerun-correction a questo prompt_type")
    parser.add_argument("--filter-skill-mode", dest="filter_skill_mode",
                        choices=list(SKILL_MODE_CHOICES),
                        help="Limita --rerun-correction a questo skill_mode")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostra il piano senza eseguire nulla")
    args = parser.parse_args()

    if args.resume and args.rerun_correction:
        parser.error("--resume e --rerun-correction sono mutuamente esclusivi")

    # 1. Carica configurazione e experiment
    try:
        config = load_config(args.config)
    except (ValueError, OSError) as exc:
        print(f"Errore configurazione: {exc}", file=sys.stderr)
        return 1

    try:
        spec = load_experiment(args.experiment)
    except ValueError as exc:
        print(f"Errore experiment: {exc}", file=sys.stderr)
        return 1

    agent = config.data["aut"]["agent"]
    runs_root = config.root / "runs"
    results_dir = config.path(config.data["results"]["directory"])

    # 2. Discovery scenari
    try:
        scenarios_dict = discover_scenarios(config.root / "scenarios")
    except ValueError as exc:
        print(f"Errore discovery scenari: {exc}", file=sys.stderr)
        return 1

    # 3. Validazione prerequisiti statici (PRIMA di qualsiasi chiamata AUT)
    try:
        validate_experiment_prerequisites(spec, config, scenarios_dict)
    except ValueError as exc:
        print(f"Errore prerequisiti experiment: {exc}", file=sys.stderr)
        return 1

    # -----------------------------------------------------------------------
    # Modalità --rerun-correction
    # -----------------------------------------------------------------------
    if args.rerun_correction:
        candidates = _collect_rerun_runs(
            spec, runs_root,
            filter_scenario=args.filter_scenario,
            filter_prompt=args.filter_prompt,
            filter_skill_mode=args.filter_skill_mode,
        )
        if not candidates:
            print("Nessuna run esistente trovata per i criteri selezionati.", file=sys.stderr)
            return 1

        terminal_ui.experiment_rerun_correction_header(spec.experiment_id, len(candidates))

        if args.dry_run:
            print(f"  [dry-run] Rivaluterei {len(candidates)} run:")
            for run in candidates:
                print(f"    {run.relative_to(config.root)}")
            return 0

        failed = False
        for run in candidates:
            try:
                reevaluate_run(config, run)
                manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
                if manifest.get("pipeline_state") != "COMPLETED":
                    failed = True
            except Exception as exc:
                print(f"  ✗ Errore rivalutazione {run.relative_to(config.root)}: {exc}",
                      file=sys.stderr)
                failed = True
        aggregate(runs_root, results_dir)
        terminal_ui.pipeline_event("Results aggregated")
        return 1 if failed else 0

    # -----------------------------------------------------------------------
    # Modalità esecuzione normale (con o senza --resume)
    # -----------------------------------------------------------------------

    # 4. Preflight (verifica Docker, Kathara, AUT auth ecc.)
    try:
        # Per codex controlla skill mode; per antigravity nessun skill mode da validare
        skill_mode_for_preflight = spec.skill_modes[0] if agent == "codex" else None
        preflight(
            config, agent,
            skill_mode=skill_mode_for_preflight,
            scenario_ids=list(spec.scenarios),
        )
        # Valida tutti i skill mode presenti nell'experiment
        if agent == "codex":
            from benchmark_core.skill_modes import validate_mode_sources
            for sm in spec.skill_modes:
                validate_mode_sources(config, sm)
    except (RuntimeError, ValueError) as exc:
        print(f"Errore preflight: {exc}", file=sys.stderr)
        return 1

    # 5. Analisi run esistenti (per --resume o solo per il riepilogo)
    analyses = analyse_existing_runs(runs_root, spec)
    summary = compute_summary(spec, analyses)

    # Mostra riepilogo iniziale
    terminal_ui.experiment_header(spec.experiment_id, {
        "scenarios": len(spec.scenarios),
        "prompt_types": len(spec.prompt_types),
        "skill_modes": len(spec.skill_modes),
        "repetitions": spec.repetitions,
        "expected": summary.expected,
        "completed": summary.completed,
        "infra_failed": summary.infra_failed,
        "missing": summary.missing,
    })

    # 6. Piano di esecuzione
    all_cells = build_run_matrix(spec)
    if args.resume:
        decisions = compute_resume_plan(spec, analyses)
    else:
        # Senza --resume: esegui tutto (una nuova run per ogni cella)
        from benchmark_core.experiment import ResumeDecision
        decisions = [ResumeDecision(cell=c, should_run=True, reason="missing") for c in all_cells]

    cells_to_run = [d for d in decisions if d.should_run]
    cells_to_skip = [d for d in decisions if not d.should_run]

    if args.dry_run:
        print(f"\n[dry-run] Eseguirei {len(cells_to_run)} run, salterei {len(cells_to_skip)}:")
        for d in cells_to_run:
            c = d.cell
            print(f"  RUN   {c.scenario_id}/{c.prompt_type}/{c.skill_mode} rep={c.replicate}")
        for d in cells_to_skip:
            c = d.cell
            print(f"  SKIP  {c.scenario_id}/{c.prompt_type}/{c.skill_mode} rep={c.replicate} ({d.reason})")
        return 0

    run_total = len(cells_to_run)
    if run_total == 0:
        print("  Nessuna run da eseguire — tutte le replicate sono già completate.")
        aggregate(runs_root, results_dir)
        return 0

    # 7. Esecuzione sequenziale
    failed = False
    completed_count = 0
    infra_fail_count = 0

    for run_index, decision in enumerate(decisions, start=1):
        cell = decision.cell
        cell_desc = f"{cell.scenario_id}/{cell.prompt_type}/{cell.skill_mode} rep={cell.replicate}"

        if not decision.should_run:
            terminal_ui.experiment_skipped(cell_desc, decision.reason)
            continue

        scenario = scenarios_dict[cell.scenario_id]
        effective_index = sum(1 for d in decisions[:run_index] if d.should_run)

        # L'intestazione viene mostrata DOPO il preflight: usiamo un evento manuale
        def _event_callback(event: str, **data):
            if event == "run_started":
                terminal_ui.experiment_run_header(
                    run_index=effective_index,
                    run_total=run_total,
                    scenario_id=cell.scenario_id,
                    prompt_type=cell.prompt_type,
                    skill_mode=cell.skill_mode,
                    replicate=cell.replicate,
                    physical_run_name=data.get("run_path", "").split("/")[-1],
                )
                if "available_skills" in data:
                    terminal_ui.skill_details(
                        cell.skill_mode, data["available_skills"], data.get("forced_skills", [])
                    )
            elif event == "pipeline_state":
                terminal_ui.pipeline_state(
                    data["state"], error=data.get("error"), details_path=data.get("details_path")
                )
            elif event == "correction_ready":
                terminal_ui.pipeline_event("Correction ready")
            elif event == "checker_running":
                terminal_ui.pipeline_event("Checker running", success=False)
            elif event == "metrics_collected":
                terminal_ui.pipeline_event("Metrics collected")
            elif event == "result":
                metrics = data["metrics"]
                checker = metrics.get("checker") or {}
                pass_rate = checker.get("pass_rate")
                aut_state = metrics.get("status") or "UNKNOWN"
                print(f"\n  AUT:      {aut_state}")
                print(f"  Checker:  {'COMPLETED' if metrics.get('status') == 'COMPLETED' else aut_state}")
                if pass_rate is not None:
                    print(f"  Pass rate:{pass_rate:.2%}")
                terminal_ui.result(metrics)

        try:
            run = run_one(
                config,
                scenario,
                agent,
                cell.prompt_type,
                skill_mode=cell.skill_mode if agent == "codex" else None,
                ui_context={},
                event_callback=_event_callback,
                experiment_id=cell.experiment_id,
                replicate=cell.replicate,
            )
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            pipeline_state = manifest.get("pipeline_state")
            if pipeline_state == "COMPLETED":
                completed_count += 1
            else:
                infra_fail_count += 1
                failed = True
                if not config.data["benchmark"]["continue_on_error"]:
                    print(f"\n  ✗ Errore fatale su {cell_desc}. Interruzione.", file=sys.stderr)
                    break
        except KeyboardInterrupt:
            print("\n\n  Interruzione manuale. Aggregazione risultati parziali...", file=sys.stderr)
            break
        except Exception as exc:
            print(f"\n  ✗ Errore esecuzione {cell_desc}: {exc}", file=sys.stderr)
            infra_fail_count += 1
            failed = True
            if not config.data["benchmark"]["continue_on_error"]:
                break

    # 8. Aggregazione finale
    aggregate(runs_root, results_dir)
    terminal_ui.pipeline_event("Results aggregated")

    terminal_ui.experiment_complete(
        experiment_id=spec.experiment_id,
        expected=run_total,
        completed=completed_count,
        failures=infra_fail_count,
        results_path=str(results_dir.resolve()),
    )

    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        raise SystemExit(1)
