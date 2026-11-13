#!/usr/bin/env python3
"""Rivaluta le run Small dell'esperimento in coppie isolate.

Installazione: copiare in scripts/rivaluta_small_parallelo.py.
Uso: .venv/bin/python scripts/rivaluta_small_parallelo.py --plan
     .venv/bin/python scripts/rivaluta_small_parallelo.py --workers 2

Attenzione: --rerun-correction è in-place: i vecchi report vengono conservati
nel meccanismo di history di benchmark_core.pipeline. Non avvia l'LLM.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def uniquify_copied_lab_conf(lab_conf: Path) -> str:
    """Cambia l'identità Kathara della SOLA copia temporanea usata dal checker."""
    if lab_conf.is_symlink() or not lab_conf.is_file():
        raise RuntimeError(f"lab.conf mancante o simbolico nella copia: {lab_conf}")
    name = f"ParallelSmall{secrets.token_hex(12)}"
    lines = lab_conf.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    found = False
    for line in lines:
        if re.match(r"^\s*LAB_NAME\s*=", line):
            if not found:
                out.append(f'LAB_NAME="{name}"\n')
                found = True
        else:
            out.append(line)
    if not found:
        out.insert(0, f'LAB_NAME="{name}"\n')
    lab_conf.write_text("".join(out), encoding="utf-8")
    return name


def install_isolation():
    """Adatta solo il copy interno del checker, senza modificare run/lab o input/lab."""
    from benchmark_core import checker_runner
    original_copy = checker_runner.copy_lab

    def copy_isolated(source: Path, target: Path):
        original_copy(source, target)
        uniquify_copied_lab_conf(Path(target) / "lab.conf")

    checker_runner.copy_lab = copy_isolated


def collect_runs(config, spec) -> list[Path]:
    found = []
    for assignment in spec.assignments:
        if assignment.task_level != "small":
            continue
        for prompt in spec.prompt_types:
            for mode in spec.skill_modes:
                base = (config.root / "runs" / spec.experiment_id / assignment.lab_id /
                        assignment.dns_tree_id / "small" / prompt / mode)
                if not base.is_dir():
                    continue
                for run in sorted(base.iterdir()):
                    if (run.is_dir() and re.fullmatch(r"r\d{3,}", run.name)
                            and (run / "manifest.json").is_file()):
                        found.append(run)
    return found


def result_for(run: Path, started: float) -> dict:
    from benchmark_core.pipeline import reevaluate_run
    try:
        reevaluate_run(_CONFIG, run)
    except Exception as exc:
        return {"run": run, "status": "ERROR", "reason": f"{type(exc).__name__}: {exc}",
                "seconds": time.monotonic() - started, "checks": None}
    try:
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        metrics = json.loads((run / "evaluation/metrics.json").read_text(encoding="utf-8"))
        checks = metrics.get("checker") or {}
        status = ("PASS" if manifest.get("task_success") is True else
                  "FAIL" if manifest.get("task_success") is False and manifest.get("pipeline_state") == "COMPLETED" else
                  "ERROR")
        return {"run": run, "status": status, "reason": manifest.get("pipeline_error", ""),
                "seconds": time.monotonic() - started,
                "checks": {k: checks.get(k) for k in ("passed", "failed", "total")}}
    except (OSError, ValueError, AttributeError) as exc:
        return {"run": run, "status": "ERROR", "reason": f"report: {exc}",
                "seconds": time.monotonic() - started, "checks": None}


def evaluate(run: Path) -> dict:
    return result_for(run, time.monotonic())


def counts(results: list[dict]) -> dict:
    return {status: sum(r["status"] == status for r in results)
            for status in ("PASS", "FAIL", "ERROR")}


def check_docker_idle() -> None:
    """Non interferire con altri container Docker già in funzione."""
    try:
        completed = subprocess.run(["docker", "ps", "--format", "{{.ID}}"],
                                   capture_output=True, text=True, timeout=15, check=True)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Impossibile verificare Docker: {exc}") from exc
    if completed.stdout.strip():
        raise RuntimeError("Docker ha già container attivi. Terminare prima le altre prove "+
                           "Kathara (senza usare pulizie globali sui container altrui).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rivaluta Small in parallelo, con report dopo ogni coppia")
    parser.add_argument("--workers", type=int, default=2, choices=(1, 2),
                        help="numero di checker simultanei; massimo 2 per prudenza (default 2)")
    parser.add_argument("--plan", action="store_true", help="mostra le run selezionate, senza modificarle")
    args = parser.parse_args()

    from benchmark_core.config import load_config
    from benchmark_core.experiment import load_experiment
    from benchmark_core.aggregation import aggregate, validate_report_destination
    from benchmark_core.report_paths import general_experiment

    config = load_config(ROOT / "benchmark.yaml")
    spec = load_experiment(ROOT / "experiments/thesis_final.yaml")
    runs = collect_runs(config, spec)
    if not runs:
        raise RuntimeError("Nessuna run Small trovata")
    print(f"Small selezionate: {len(runs)} run, {args.workers} checker contemporanei", flush=True)
    if args.plan:
        for run in runs:
            print("  ", run.relative_to(config.root))
        print("Nessun file modificato (plan).")
        return 0

    # Usa ESATTAMENTE lo stesso lock dell'esperimento previsto da run_experiment.py.
    lock_root = Path(tempfile.gettempdir()) / "kathara-experiment-locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_id = hashlib.sha256(f"{config.root.resolve()}\0{spec.experiment_id}".encode()).hexdigest()
    output = general_experiment(config, spec.experiment_id).resolve()
    validate_report_destination(output)
    with (lock_root / f"{lock_id}.lock").open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Esperimento già in esecuzione. Non avviare in parallelo un altro runner.") from exc
        check_docker_idle()
        install_isolation()
        global _CONFIG
        _CONFIG = config
        all_results: list[dict] = []
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for start in range(0, len(runs), args.workers):
                batch = runs[start:start + args.workers]
                print(f"\n===== GRUPPO {start // args.workers + 1}: "
                      f"{', '.join(str(r.relative_to(config.root)) for r in batch)} =====", flush=True)
                futures = {pool.submit(evaluate, run): run for run in batch}
                for future in as_completed(futures):
                    try:
                        row = future.result()
                    except Exception as exc:
                        row = {"run": futures[future], "status": "ERROR",
                               "reason": f"{type(exc).__name__}: {exc}", "seconds": 0, "checks": None}
                    all_results.append(row)
                    c = row["checks"] or {}
                    summary = (f'{c.get("passed")}/{c.get("total")}' if c.get("total") is not None else "N/D")
                    print(f'  [{len(all_results)}/{len(runs)}] {row["run"].relative_to(config.root)}: '
                          f'{row["status"]}, test={summary}, {row["seconds"]:.1f}s', flush=True)
                    if row["reason"]:
                        print(f'      {row["reason"]}', flush=True)

                # Nessun checker ancora in scrittura: aggregazione sempre su dati coerenti.
                print("Aggiornamento statistiche e report aggregati...", flush=True)
                try:
                    aggregate(config.root / "runs", output, experiment_id=spec.experiment_id)
                    print(f"Report aggiornati: {output}", flush=True)
                except Exception as exc:
                    print(f"ERRORE aggiornamento report: {type(exc).__name__}: {exc}",
                          file=sys.stderr, flush=True)
                    return 2
                c = counts(all_results)
                print(f'PROGRESSO {len(all_results)}/{len(runs)} | PASS={c["PASS"]} '
                      f'| FAIL={c["FAIL"]} | ERROR={c["ERROR"]} '
                      f'| {time.monotonic()-started:.1f}s', flush=True)

        c = counts(all_results)
        print(f'\nFINE. {len(all_results)} Small rivalutate: PASS={c["PASS"]}, '
              f'FAIL={c["FAIL"]}, ERROR={c["ERROR"]}.')
        print(f'Report: {output}')
        return 1 if c["ERROR"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        raise SystemExit(1)
