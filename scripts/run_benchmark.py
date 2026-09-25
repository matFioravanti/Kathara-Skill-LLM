#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark_core.agent_factory import AGENTS
from benchmark_core.aggregation import aggregate
from benchmark_core.config import load_config, verify_skills
from benchmark_core.pipeline import reevaluate_run, run_one
from benchmark_core.preflight import preflight
from benchmark_core.scenario_loader import discover_scenarios
from benchmark_core.prompts import PROMPT_TYPES, missing_prompts
from benchmark_core.skill_modes import SKILL_MODE_CHOICES, execute_skill_modes, mode_details
from benchmark_core import terminal_ui


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Codex CLI locale / Kathara DNS-web")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.yaml")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scenario")
    group.add_argument("--all", action="store_true")
    group.add_argument("--check-skills", action="store_true")
    group.add_argument("--preflight", action="store_true")
    parser.add_argument("--rerun-correction", action="store_true",
                        help="Rivaluta in-place le run esistenti senza eseguire l'AUT")
    parser.add_argument("--agent", choices=list(AGENTS))
    parser.add_argument("--skill-mode", choices=SKILL_MODE_CHOICES, default=None,
                        help="Modalità Skill Codex (default: dns_only)")
    parser.add_argument("--all-skill-modes", action="store_true",
                        help="Esegue in sequenza tutte le cinque modalità Skill Codex")
    parser.add_argument("--prompt-type", choices=PROMPT_TYPES,
                        help="Tipo di prompt da usare (obbligatorio per i benchmark AUT)")
    parser.add_argument("--repetitions", type=int)
    args = parser.parse_args()
    if args.all_skill_modes and args.skill_mode is not None:
        parser.error("--all-skill-modes è mutuamente esclusivo con --skill-mode")
    if args.all_skill_modes and (args.check_skills or args.preflight or args.rerun_correction):
        parser.error("--all-skill-modes è disponibile solo per benchmark AUT")
    if args.rerun_correction and args.repetitions is not None:
        parser.error("--repetitions non è applicabile con --rerun-correction")
    if args.rerun_correction and (args.check_skills or args.preflight):
        parser.error("--rerun-correction si usa con --scenario o --all, non con --check-skills/--preflight")
    config = load_config(args.config)
    if args.check_skills:
        for name, path in verify_skills(config).items():
            print(f"OK {name}: {path}")
        return 0
    agent = config.data["aut"]["agent"]
    if (args.skill_mode is not None or args.all_skill_modes) and agent != "codex":
        parser.error("--skill-mode è supportato solo con --agent codex.")
    if args.agent and args.agent != agent:
        parser.error(
            f"--agent {args.agent} non è compatibile con la configurazione "
            f"in {args.config} (aut.agent: {agent}). "
            f"Usa il file di configurazione corretto per l'agente desiderato."
        )
    repetitions = args.repetitions if args.repetitions is not None else config.data["benchmark"]["repetitions"]
    if repetitions < 1:
        parser.error("--repetitions deve essere positivo")
    if not (args.scenario or args.all or args.preflight or args.check_skills):
        parser.error("specificare --scenario, --all, --check-skills o --preflight")
    scenarios = discover_scenarios(config.root / "scenarios")
    if args.scenario and args.scenario not in scenarios:
        parser.error(f"Scenario non trovato: {args.scenario}; disponibili: {', '.join(scenarios)}")
    if not scenarios:
        raise ValueError("Nessuno scenario trovato.")
    if not (args.preflight or args.check_skills):
        if not args.prompt_type:
            parser.error("--prompt-type è obbligatorio per eseguire un benchmark")
    selected = [scenarios[args.scenario]] if args.scenario else list(scenarios.values())
    if args.prompt_type and not args.rerun_correction:
        missing = missing_prompts(config.root, [scenario.scenario_id for scenario in selected], args.prompt_type)
        if missing:
            parser.error("Prompt mancanti:\n" + "\n".join(missing))
    if args.rerun_correction:
        selected_ids = {scenario.scenario_id for scenario in ([scenarios[args.scenario]] if args.scenario else scenarios.values())}
        if not args.prompt_type:
            parser.error("--prompt-type è obbligatorio con --rerun-correction")
        modes = ("no_skill", "creation_only", "dns_only", "both_forced", "auto") if args.skill_mode is None else (args.skill_mode,)
        runs_root = config.root / "runs"
        candidates = []
        for scenario_id in sorted(selected_ids):
            for mode in modes:
                mode_root = runs_root / scenario_id / args.prompt_type / mode
                candidates.extend(sorted((p for p in mode_root.iterdir()
                                          if p.is_dir() and re.fullmatch(r"r\d{3,}", p.name)),
                                         key=lambda p: int(p.name[1:])) if mode_root.is_dir() else [])
        if not candidates:
            parser.error("Nessuna run esistente trovata per i criteri selezionati")
        failed = False
        try:
            for run in candidates:
                try:
                    reevaluate_run(config, run)
                    metadata = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
                    failed |= metadata.get("pipeline_state") != "COMPLETED"
                except Exception as exc:
                    print(f"Errore rivalutazione {run}: {exc}", file=sys.stderr)
                    failed = True
        finally:
            aggregate(runs_root, config.path(config.data["results"]["directory"]))
        return 1 if failed else 0
    skill_mode = ("all" if args.all_skill_modes else (args.skill_mode or "dns_only")) if agent == "codex" else None
    preflight(config, agent, skill_mode=skill_mode,
              scenario_ids=[scenario.scenario_id for scenario in selected])
    if args.preflight:
        print("Prerequisiti disponibili; nessuna chiamata modello eseguita.")
        return 0
    failed = False
    result_rows = []
    try:
        for scenario_index, scenario in enumerate(selected, start=1):
            if args.all:
                terminal_ui.scenario_header(scenario_index, len(selected), scenario.scenario_id, args.prompt_type)
            for repetition in range(1, repetitions + 1):
                selected_mode = skill_mode or ("dns_only" if agent == "codex" else "no_skill")

                def execute_mode(mode: str, index: int, total: int) -> bool:
                    try:
                        effective_mode = mode if agent == "codex" else None
                        selection = mode_details(mode) if agent == "codex" else None
                        context = {"run_index": index, "run_total": total} if selected_mode == "all" else {}
                        if selection:
                            context.update({"available_skills": list(selection.available_skills),
                                            "forced_skills": list(selection.forced_skills)})
                        run = run_one(
                            config, scenario, agent, args.prompt_type, skill_mode=effective_mode,
                            ui_context=context, event_callback=terminal_ui.render_run_event,
                        )
                        metadata = json.loads((run / "manifest.json").read_text())
                        result_rows.append({"run": run, "metrics": json.loads((run / "evaluation/metrics.json").read_text())})
                        return metadata["pipeline_state"] != "COMPLETED"
                    except Exception as exc:
                        terminal_ui.pipeline_state("PREPARATION_FAILED", error=str(exc))
                        return True

                for mode, _, _, run_failed in execute_skill_modes(selected_mode, execute_mode):
                    failed |= run_failed
                    if run_failed and not config.data["benchmark"]["continue_on_error"]:
                        return 1
    finally:
        aggregate(config.root / "runs", config.path(config.data["results"]["directory"]))
        terminal_ui.pipeline_event("Results aggregated")
        terminal_ui.result_table(result_rows, multiple_scenarios=bool(args.all))
    # Un task scorretto con checker completato è un risultato valido, non un errore CLI.
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        raise SystemExit(1)
