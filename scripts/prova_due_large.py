#!/usr/bin/env python3
"""Prova isolata: due kathara-lab-checker Large in parallelo, senza LLM.

Eseguire dalla root Tesi-Skill con il Python del progetto:
  .venv/bin/python scripts/prova_due_large.py --plan
  .venv/bin/python scripts/prova_due_large.py

NON modifica le run sorgenti né le correction; usa copie in results/parallel_large_test/.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time


def log(*args):
    print(*args, flush=True)


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def select_runs(root: Path, experiment: str, explicit: list[Path]) -> list[Path]:
    runs_root = (root / "runs" / experiment).resolve()
    if len(explicit) not in (0, 2):
        raise ValueError("Specificare esattamente due --run, oppure nessuno per la selezione automatica")
    if explicit:
        candidates = [p.expanduser().resolve() for p in explicit]
    else:
        candidates = sorted(p.parent.resolve() for p in runs_root.glob("**/large/**/r*/manifest.json"))
    eligible = []
    for run in candidates:
        if not run.is_relative_to(runs_root):
            if explicit:
                raise ValueError(f"La run non appartiene all'esperimento selezionato: {run}")
            continue
        manifest = read_json(run / "manifest.json")
        if ("large" not in run.relative_to(runs_root).parts or
                manifest.get("aut_execution_success") is not True or
                not (run / "lab/lab.conf").is_file() or
                not (run / "evaluation/correction.yaml").is_file()):
            if explicit:
                raise ValueError(f"Run non idonea (servono AUT completo, lab.conf e correction snapshot): {run}")
            continue
        eligible.append(run)
    if len(eligible) < 2:
        raise ValueError(f"Trovate soltanto {len(eligible)} run Large idonee in {runs_root}")
    if explicit:
        chosen = eligible
    else:
        # Preferiamo due valutazioni gia' completate e, se possibile, con skill_mode diversi.
        completed = [p for p in eligible if read_json(p / "manifest.json").get("pipeline_state") == "COMPLETED"]
        pool = completed if len(completed) >= 2 else eligible
        first = pool[0]
        first_mode = read_json(first / "manifest.json").get("skill_mode")
        second = next((p for p in pool[1:] if read_json(p / "manifest.json").get("skill_mode") != first_mode), pool[1])
        chosen = [first, second]
    if chosen[0] == chosen[1]:
        raise ValueError("Le due run devono essere diverse")
    return chosen


def cmd(args, timeout=15) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def preflight() -> int:
    for exe in ("docker", "kathara"):
        if not shutil.which(exe):
            raise RuntimeError(f"Comando non disponibile: {exe}")
    docker_info = cmd(["docker", "info", "--format", "{{.MemTotal}}"], timeout=30)
    if docker_info.returncode:
        raise RuntimeError("Docker Engine non raggiungibile: " + docker_info.stderr.strip()[:300])
    mem = int(docker_info.stdout.strip()) if docker_info.stdout.strip().isdigit() else 0
    check = cmd([sys.executable, "-c", "import kathara_lab_checker"], timeout=15)
    if check.returncode:
        raise RuntimeError("kathara_lab_checker non disponibile nel Python corrente")
    return mem


def reject_external_symlinks(source: Path):
    base = source.resolve()
    for p in source.rglob("*"):
        if p.is_symlink() and not p.resolve().is_relative_to(base):
            raise RuntimeError(f"Link simbolico esterno alla sandbox, copia rifiutata: {p}")


def set_isolated_lab_name(lab_conf: Path, worker_number: int) -> str:
    """Give the copied lab a unique Kathara identity without changing its topology.

    Kathara derives Lab.hash from LAB_NAME when it is present. Two checker
    directories called ``lab`` otherwise collide on Docker network names.
    Only call this for the staged COPY, never for a source run.
    """
    if lab_conf.is_symlink():
        raise RuntimeError(f"lab.conf simbolico: non modificarlo per sicurezza: {lab_conf}")
    name = f"ParallelLarge{worker_number}{secrets.token_hex(10)}"
    original = lab_conf.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    changed = []
    replaced = False
    for line in lines:
        if re.match(r"^\s*LAB_NAME\s*=", line):
            if not replaced:
                changed.append(f'LAB_NAME="{name}"\n')
                replaced = True
            # Ignore additional LAB_NAME entries to avoid duplicate/conflicting IDs.
        else:
            changed.append(line)
    if not replaced:
        changed.insert(0, f'LAB_NAME="{name}"\n')
    lab_conf.write_text("".join(changed), encoding="utf-8")
    return name


def stage(run: Path, base: Path, number: int) -> dict:
    home = base / f"checker_{number}"
    labs = home / "labs"
    labs.mkdir(parents=True)
    destination = labs / "lab"
    source = run / "lab"
    reject_external_symlinks(source)
    shutil.copytree(source, destination, symlinks=True)
    isolated_name = set_isolated_lab_name(destination / "lab.conf", number)
    # Come nel runner originale: report preesistenti non devono influenzare il checker.
    for name in ("lab_result_all.csv", "lab_result_failed.csv", "lab_result_summary.csv", "lab_result.xlsx"):
        (destination / name).unlink(missing_ok=True)
    correction = home / "correction.yaml"
    shutil.copy2(run / "evaluation/correction.yaml", correction)
    return dict(source=run, home=home, labs=labs, lab=destination, correction=correction,
                isolation_lab_name=isolated_name,
                stdout=home / "stdout.log", stderr=home / "stderr.log",
                process=None, started=None, ended=None, timeout=False, aborted=False, returncode=None)


def parse_report(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != 1:
        return {"error": f"Numero righe non atteso: {len(rows)}"}
    row = rows[0]
    try:
        passed = int(row["Tests Passed"])
        failed = int(row["Tests Failed"])
        total = int(row["Tests Total Number"])
    except (ValueError, TypeError, KeyError):
        return {"error": "Formato results.csv inatteso"}
    return {"passed": passed, "failed": failed, "total": total, "task_success": failed == 0}


def details(path: Path) -> Counter | None:
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or any("Test Description" not in r or "Passed" not in r for r in rows):
        return None
    return Counter((r["Test Description"], r["Passed"]) for r in rows)


def historical_comparison(job: dict) -> dict:
    original = job["source"] / "results"
    parallel = job["labs"]
    prior = parse_report(original / "results.csv")
    current = parse_report(parallel / "results.csv")
    base = details(original / "lab/lab_result_all.csv")
    fresh = details(parallel / "lab/lab_result_all.csv")
    result = {"previous_summary": prior, "parallel_summary": current,
              "summary_equal": bool(prior and current and prior == current),
              "per_check_equal": None, "differences": []}
    if base is not None and fresh is not None:
        missing = base - fresh
        extra = fresh - base
        result["per_check_equal"] = not missing and not extra
        result["differences"] = ([{"kind": "missing", "description": desc[:300], "passed": passed, "count": count}
                                  for (desc, passed), count in missing.items()] +
                                 [{"kind": "added", "description": desc[:300], "passed": passed, "count": count}
                                  for (desc, passed), count in extra.items()])[:30]
    return result


def to_mib(text: str) -> float:
    text = text.strip().replace(" ", "")
    m = re.fullmatch(r"([\d.]+)(B|KiB|MiB|GiB|TiB|kB|MB|GB|TB)", text, re.IGNORECASE)
    if not m:
        return 0.0
    value, unit = float(m.group(1)), m.group(2).lower()
    factors = {"b": 1 / 1048576, "kib": 1 / 1024, "mib": 1, "gib": 1024, "tib": 1024 * 1024,
               "kb": 1000 / 1048576, "mb": 1000000 / 1048576,
               "gb": 1e9 / 1048576, "tb": 1e12 / 1048576}
    return value * factors[unit]


def docker_snapshot() -> dict | None:
    try:
        result = cmd(["docker", "stats", "--no-stream", "--format", "{{json .}}"], timeout=25)
        if result.returncode:
            return None
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        memory = sum(to_mib(str(row.get("MemUsage", "")).split("/")[0]) for row in rows)
        cpu = sum(float(str(row.get("CPUPerc", "0")).strip("%"))
                  for row in rows if re.fullmatch(r"[\d.]+%", str(row.get("CPUPerc", ""))))
        return {"time": datetime.now(timezone.utc).isoformat(), "containers_running": len(rows),
                "memory_mib": round(memory, 1), "cpu_percent_sum": round(cpu, 1)}
    except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError):
        return None


def stop(job: dict):
    p = job["process"]
    if p and p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            p.wait(timeout=35)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
    if job["ended"] is None:
        job["ended"] = time.monotonic()
    if p:
        job["returncode"] = p.returncode


def cleanup(job: dict) -> dict:
    # Solo laboratorio di questa copia temporanea. Mai kathara wipe / global clean.
    try:
        p = cmd(["kathara", "lclean", "-d", str(job["lab"])], timeout=120)
        return {"returncode": p.returncode, "stderr": p.stderr[-1000:]}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Prova 2 checker Large paralleli sulle run esistenti: non modifica il runner")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="root del repository Tesi-Skill")
    parser.add_argument("--experiment", default="thesis_final")
    parser.add_argument("--run", type=Path, action="append", default=[], help="ripetere due volte per scegliere run specifiche")
    parser.add_argument("--plan", action="store_true", help="mostra le due run senza avviare Docker")
    parser.add_argument("--timeout", type=int, default=900, help="massimo secondi per ciascun checker (default 900)")
    parser.add_argument("--sample-seconds", type=int, default=10, help="intervallo di campionamento Docker")
    parser.add_argument("--abort-memory-percent", type=float, default=90.0,
                        help="interrompi se docker stats supera questa percentuale della RAM Docker per 2 campioni consecutivi (0 disattiva)")
    parser.add_argument("--no-cache", action="store_true", help="aggiungi --no-cache al checker")
    parser.add_argument("--output", type=Path, default=None, help="cartella nuova per report della prova")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if args.timeout <= 0 or args.sample_seconds <= 0:
        parser.error("timeout e sample-seconds devono essere > 0")
    try:
        chosen = select_runs(root, args.experiment, args.run)
        log("Due run selezionate:")
        for i, p in enumerate(chosen, 1):
            meta = read_json(p / "manifest.json")
            log(f"  [{i}] {p.relative_to(root)} (stato: {meta.get('pipeline_state')}, task_success: {meta.get('task_success')})")
        if args.plan:
            log("Piano verificato; Docker non avviato. Rimuovi --plan per la prova reale.")
            return 0
        memory_bytes = preflight()
        output = (args.output or root / "results" / "parallel_large_test" /
                  datetime.now().strftime("%Y%m%d_%H%M%S")).expanduser().resolve()
        if output.exists():
            raise ValueError(f"Cartella report già esistente: {output}")
        if any(output.is_relative_to(p) for p in chosen):
            raise ValueError("La cartella output non può essere interna alle run originali")
        output.mkdir(parents=True)
        log("Report prova:", output)
        log("RAM Docker configurata:", f"{memory_bytes / 1024 ** 3:.2f} GiB" if memory_bytes else "non rilevata")
        jobs = []
        snapshots = []
        abnormal = None
        pre_snapshot = docker_snapshot()
        if pre_snapshot:
            log("Container Docker già attivi:", pre_snapshot["containers_running"])
        base = (output / "isolated_labs").resolve()
        base.mkdir()
        log("Directory copie isolate (conservate per diagnosi):", base)
        for number, p in enumerate(chosen, 1):
            job = stage(p, base, number)
            jobs.append(job)
            log(f"Identità Kathara isolata {number}: {job['isolation_lab_name']}")
        try:
            for n, job in enumerate(jobs, 1):
                stdout = job["stdout"].open("w", encoding="utf-8")
                stderr = job["stderr"].open("w", encoding="utf-8")
                invocation = [sys.executable, "-m", "kathara_lab_checker",
                              "--config", str(job["correction"]), "--labs", str(job["labs"]),
                              "--report-type", "csv"]
                if args.no_cache:
                    invocation.append("--no-cache")
                job["invocation"] = invocation
                job["started"] = time.monotonic()
                try:
                    job["process"] = subprocess.Popen(invocation, stdout=stdout, stderr=stderr,
                                                      cwd=str(root), start_new_session=True)
                finally:
                    stdout.close(); stderr.close()
                log(f"Checker {n} avviato (PID {job['process'].pid})")
            overload_streak = 0
            last_sample = 0.0
            while True:
                now = time.monotonic()
                for n, job in enumerate(jobs, 1):
                    if job["ended"] is None and job["process"].poll() is not None:
                        job["ended"] = time.monotonic()
                        job["returncode"] = job["process"].returncode
                        log(f"Checker {n} terminato: codice {job['returncode']}, durata {job['ended'] - job['started']:.1f}s")
                    if job["ended"] is None and now - job["started"] > args.timeout:
                        abnormal = f"Checker {n} ha superato il timeout {args.timeout}s"
                        job["timeout"] = True
                if all(job["ended"] is not None for job in jobs):
                    break
                if abnormal:
                    log("Interruzione di sicurezza:", abnormal)
                    break
                if now - last_sample >= args.sample_seconds:
                    last_sample = now
                    stat = docker_snapshot()
                    if stat:
                        snapshots.append(stat)
                        p = stat["memory_mib"] * 1024 * 1024 / memory_bytes * 100 if memory_bytes else None
                        label = f"{p:.1f}% della RAM Docker" if p is not None else "percentuale RAM non disponibile"
                        log(f"[docker] {stat['containers_running']} container, {stat['memory_mib']:.0f} MiB ({label}), CPU cumulativa {stat['cpu_percent_sum']:.0f}%")
                        if p is not None and args.abort_memory_percent > 0 and p >= args.abort_memory_percent:
                            overload_streak += 1
                            if overload_streak >= 2:
                                abnormal = f"Uso RAM container >= {args.abort_memory_percent}% per 2 campioni"
                        else:
                            overload_streak = 0
                time.sleep(1)
        except KeyboardInterrupt:
            abnormal = "Interrotto dall'utente (Ctrl+C)"
            log("Interruzione richiesta; chiusura dei due checker...")
        finally:
            for job in jobs:
                if job["ended"] is None:
                    job["aborted"] = True
                stop(job)
            cleanup_results = [cleanup(job) for job in jobs]
            summary = {"experiment": args.experiment, "test": "2 large checkers concurrently", "aborted_reason": abnormal,
                       "docker_preexisting": pre_snapshot,
                       "docker_samples": snapshots,
                       "peak_containers": max((s["containers_running"] for s in snapshots), default=None),
                       "peak_memory_mib": max((s["memory_mib"] for s in snapshots), default=None),
                       "peak_cpu_percent_sum": max((s["cpu_percent_sum"] for s in snapshots), default=None),
                       "jobs": []}
            for n, (job, result) in enumerate(zip(jobs, cleanup_results), 1):
                target = output / f"checker_{n}"
                target.mkdir()
                if (job["labs"] / "results.csv").is_file():
                    shutil.copy2(job["labs"] / "results.csv", target / "results.csv")
                if (job["labs"] / "lab").is_dir():
                    for fn in ("lab_result_all.csv", "lab_result_failed.csv", "lab_result_summary.csv"):
                        source = job["labs"] / "lab" / fn
                        if source.is_file():
                            shutil.copy2(source, target / fn)
                for kind in ("stdout", "stderr"):
                    shutil.copy2(job[kind], target / (kind + ".log"))
                comparison = historical_comparison(job)
                duration = (job["ended"] - job["started"]) if job["ended"] is not None else None
                history = read_json(job["source"] / "evaluation" / "metrics.json")
                baseline_time = (history.get("timing") or {}).get("checker_seconds")
                if type(baseline_time) not in (int, float):
                    baseline_time = None
                summary["jobs"].append({"source": str(job["source"]),
                                       "isolation_lab_name": job["isolation_lab_name"],
                                       "duration_seconds": duration,
                                       "historical_checker_seconds": baseline_time,
                                       "exit_code": job["returncode"], "timeout": job["timeout"],
                                       "aborted": job["aborted"], "cleanup": result,
                                       "comparison": comparison})
                log(f"[Risultato {n}] durata={duration:.1f}s, esiti storici uguali: "
                    f"{comparison['per_check_equal']}, cleanup={result.get('returncode', 'errore')}")
            if len(jobs) == 2:
                begin = max(job["started"] for job in jobs)
                end = min(job["ended"] for job in jobs)
                summary["overlap_seconds"] = round(max(0, end - begin), 1)
                summary["test_wall_seconds"] = round(max(job["ended"] for job in jobs) - min(job["started"] for job in jobs), 1)
            (output / "report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            log("\nReport JSON:", output / "report.json")
            log("Sovrapposizione checker:", summary.get("overlap_seconds"), "s")
            log("Durata della prova:", summary.get("test_wall_seconds"), "s")
            if abnormal:
                log("ATTENZIONE:", abnormal)
            if any(r.get("returncode") != 0 or r.get("error") for r in cleanup_results):
                log("ATTENZIONE: cleanup fallito; verificare i container Kathara residui prima di altri test")
                exit_code = 3
            elif abnormal or any(job["returncode"] != 0 for job in jobs):
                exit_code = 2
            else:
                exit_code = 0
        return exit_code
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        log("Errore:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
