#!/usr/bin/env python3
"""Exercise the production phased scheduler with real spawned processes.

Default: deterministic local payloads. --live: real Codex sandbox environments
and Kathara checkers. --model-turn also performs tiny model requests.
All data belongs to this probe.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark_core.config import Config
from benchmark_core.experiment import RunCell, ResumeDecision
from benchmark_core.phased_execution import execute_phased
from benchmark_core.run_identity import cell_metadata, identity_fields
from benchmark_core.task_catalog import TaskAssignment
from benchmark_core.workspace import tree_hash, write_json
from benchmark_core.parallel_limits import GENERATION_MAX_WORKERS, CHECKER_MAX_WORKERS


def probe_key(cell):
    return cell.prompt_type if cell.skill_mode == "no_skill" else f"{cell.prompt_type}_{cell.skill_mode}"


def event(root, phase, kind, identity, **details):
    write_json(root / "events" / f"{time.time_ns()}-{os.getpid()}-{uuid.uuid4().hex}.json",
               {"phase": phase, "kind": kind, "id": identity, "pid": os.getpid(),
                "at": time.monotonic(), **details})


def barrier(root, phase, identity, count):
    directory = root / "barriers" / phase
    directory.mkdir(parents=True, exist_ok=True)
    (directory / identity).touch()
    deadline = time.monotonic() + 150
    while len(list(directory.iterdir())) < count:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{phase}: fewer than {count} simultaneous workers")
        time.sleep(.05)


def command(args, log, timeout=120, input_text=None):
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CODEX_API_KEY", None)
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=input_text, env=env)
    write_json(log, {"command": args, "returncode": result.returncode,
                     "stdout": result.stdout, "stderr": result.stderr})
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")
    return result


def generate_probe(config, scenario, agent, cell):
    root, live = config.root, config.data["probe"]["live"]
    ident = probe_key(cell)
    event(root, "generation", "start", ident)
    run = root / "runs" / ident / "r001"
    lab = run / "lab"
    lab.mkdir(parents=True)
    (run / "logs").mkdir()
    (lab / "lab.conf").write_text('LAB_NAME="SharedProbeName"\npc1[0]="A"\npc1[image]="kathara/base"\n')
    (lab / "pc1.startup").write_text(f"printf '%s\\n' {ident} > /tmp/parallel-probe-marker\n")
    (lab / "private_marker").write_text(ident)
    before = tree_hash(lab)
    name = "parallel-probe-" + root.name[-8:] + "-" + ident.lower()
    try:
        if live:
            exe = shutil.which("sbx")
            command([exe, "create", "codex", str(lab), "--name", name, "--skills", "off",
                     "--memory", "3g", "--cpus", "2"], run / "logs/sandbox_create.json")
            event(root, "sandbox", "start", name)
        barrier(root, "generation", ident, config.data["parallel_execution"]["generation"]["workers"])
        if live:
            command([exe, "exec", name, "codex", "--version"], run / "logs/codex_version.json", 30)
            other = [str(root / "runs" / other_id / "r001/lab/private_marker")
                     for other_id in config.data["probe"]["job_ids"] if other_id != ident]
            code = ("import pathlib,sys,time; "
                    "assert pathlib.Path(sys.argv[1]).read_text()==sys.argv[2]; "
                    "assert all(not pathlib.Path(p).exists() for p in sys.argv[3:]); "
                    "time.sleep(3); print('workspace isolation OK')")
            command([exe, "exec", name, "python3", "-c", code,
                     str(lab / "private_marker"), ident, *other], run / "logs/isolation.json", 45)
            if config.data["probe"]["model_turn"]:
                from benchmark_core.docker_sandbox_runner import sbx_check_network_policy
                sbx_check_network_policy(name)
                barrier(root, "model", ident, config.data["parallel_execution"]["generation"]["workers"])
                event(root, "model", "start", ident)
                try:
                    prompt = ("Infrastructure concurrency test. Use the shell once to run sleep 5. "
                              "Do not read or change any files. Then reply exactly PARALLEL_OK_" + ident +
                              ". Do not ask questions.")
                    result = command([exe, "exec", "-i", "-w", str(lab), name,
                        "codex", "exec", "--json", "--ephemeral", "--disable", "memories",
                        "-c", "features.memories=false", "-c", 'approval_policy="never"',
                        "--sandbox", "workspace-write", "--skip-git-repo-check", "-C", str(lab),
                        "--model", config.data["probe"]["model"],
                        "-c", 'model_reasoning_effort="low"', "-"],
                        run / "logs/model_turn.json", timeout=120, input_text=prompt)
                    native_events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
                    assert any(e.get("type") == "turn.completed" for e in native_events), "No completed model turn"
                    assert "PARALLEL_OK_" + ident in result.stdout, "Missing model response marker"
                finally:
                    event(root, "model", "end", ident)
        else:
            time.sleep(.4)
    finally:
        if live:
            event(root, "sandbox", "end", name)
            command([shutil.which("sbx"), "rm", "--force", name], run / "logs/sandbox_cleanup.json", 90)
    assert tree_hash(lab) == before, "Sandbox altered the fixture lab"
    shutil.copytree(lab, run / "input/lab")
    import yaml
    correction = {"lab_inline": (lab / "lab.conf").read_text(), "convergence_time": 2,
                  "default_image": "kathara/base",
                  "test": {"custom_commands": {"pc1": [{
                      "command": "sh -c 'sleep 4; cat /tmp/parallel-probe-marker'",
                      "exit_code": 0, "output": ident}]}}}
    (run / "evaluation").mkdir()
    (run / "evaluation/correction.yaml").write_text(yaml.safe_dump(correction))
    metadata = {**cell_metadata(cell), "run_number": 1, "pipeline_state": "AUT_COMPLETED",
                "final_lab_sha256": before,
                "orchestration": config.data["parallel_execution"]}
    metadata.update(identity_fields(metadata))
    write_json(run / "manifest.json", metadata)
    event(root, "generation", "end", ident)
    return str(run), "AUT_COMPLETED"


def evaluate_probe(config, run_name):
    run = Path(run_name)
    ident = run.parent.name
    event(config.root, "checker", "start", ident)
    try:
        barrier(config.root, "checker", ident, config.data["parallel_execution"]["checker"]["small_workers"])
        metadata = json.loads((run / "manifest.json").read_text())
        if config.data["probe"]["live"]:
            from benchmark_core.checker_runner import run_checker
            outcome = run_checker(config, run, run / "evaluation/correction.yaml", isolated=True)
            write_json(run / "evaluation/checker_outcome.json", outcome)
            assert outcome["task_success"] is True, outcome
        else:
            time.sleep(.4)
        assert tree_hash(run / "lab") == metadata["final_lab_sha256"]
        metadata["pipeline_state"] = "COMPLETED"
        write_json(run / "manifest.json", metadata)
        return str(run), "COMPLETED"
    finally:
        event(config.root, "checker", "end", ident)


def peak(events, phase):
    active, maximum = 0, 0
    for row in sorted((e for e in events if e["phase"] == phase), key=lambda e: e["at"]):
        active += 1 if row["kind"] == "start" else -1
        maximum = max(maximum, active)
    return maximum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox-workers", type=int, choices=range(1, GENERATION_MAX_WORKERS + 1), default=5)
    parser.add_argument("--checker-workers", type=int, choices=range(1, CHECKER_MAX_WORKERS["small"] + 1), default=4)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model-turn", action="store_true", help="short real Codex turns; implies --live")
    parser.add_argument("--model", default="gpt-6.1-terra")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.live = args.live or args.model_turn
    root = (args.output or ROOT / "reports/parallel_worker_probe" /
            (datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8])).resolve()
    root.mkdir(parents=True, exist_ok=False)
    assignment = TaskAssignment("lab_01", "base", "small")
    job_count = max(5, args.sandbox_workers, args.checker_workers)
    cells = [RunCell("parallel_worker_probe", "lab_01", f"T{n}", mode, 1, assignment)
             for mode in ("no_skill", "auto") for n in range(1, 7)][:job_count]
    config = Config(root, {"probe": {"live": args.live, "model_turn": args.model_turn, "model": args.model,
                                    "job_ids": [probe_key(cell) for cell in cells]},
        "docker_sandbox": {"execution_backend": "docker_sandbox"},
        "parallel_execution": {"generation": {"workers": 2}},
        "benchmark": {"timeout_seconds": 120}, "checker": {"no_cache": True}})
    stopped = threading.Event()
    samples = []

    def monitor():
        while not stopped.wait(.25):
            result = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=5)
            pids = [int(line.strip().split(None, 1)[0]) for line in result.stdout.splitlines()
                    if str(root) in line and "-m kathara_lab_checker" in line]
            samples.append({"at": time.monotonic(), "checker_pids": pids})

    thread = threading.Thread(target=monitor, daemon=True)
    if args.live:
        thread.start()
    failed = True
    try:
        with patch("benchmark_core.phased_execution._generate", generate_probe), \
             patch("benchmark_core.phased_execution._evaluate", evaluate_probe):
            failed = execute_phased(config, None, {"lab_01": None}, "codex",
                [ResumeDecision(c, True, "missing") for c in cells], {},
                generation_workers=args.sandbox_workers,
                checker_workers={"small": args.checker_workers, "medium": args.checker_workers, "large": 1},
                update_reports=lambda: None)
    finally:
        stopped.set()
        if args.live:
            thread.join(timeout=6)
        events = [json.loads(path.read_text()) for path in (root / "events").glob("*.json")]
        starts = [e["at"] for e in events if e["phase"] == "checker" and e["kind"] == "start"]
        ends = [e["at"] for e in events if e["phase"] == "generation" and e["kind"] == "end"]
        report = {"mode": ("live infrastructure and real model turns" if args.model_turn else
                           "live infrastructure, no model requests" if args.live else "local processes"),
                  "failed": failed, "generation_peak": peak(events, "generation"),
                  "checker_peak": peak(events, "checker"), "sandbox_peak": peak(events, "sandbox"),
                  "model_turn_peak": peak(events, "model"),
                  "actual_checker_process_peak": max((len(s["checker_pids"]) for s in samples), default=0),
                  "phases_separated": bool(starts and len(ends) == job_count and min(starts) >= max(ends)),
                  "generation_pids": sorted({e["pid"] for e in events if e["phase"] == "generation"}),
                  "events": sorted(events, key=lambda e: e["at"]), "process_samples": samples}
        write_json(root / "report.json", report)
        print("PROBE REPORT", root / "report.json", flush=True)
        print(json.dumps({k: v for k, v in report.items() if k not in ("events", "process_samples")}), flush=True)
    assert not failed, "Worker failure: inspect the probe report and per-run logs"
    assert report["generation_peak"] == args.sandbox_workers
    assert report["checker_peak"] == args.checker_workers
    assert report["phases_separated"]
    if args.live:
        assert report["sandbox_peak"] == args.sandbox_workers
        assert report["actual_checker_process_peak"] == args.checker_workers
    if args.model_turn:
        assert report["model_turn_peak"] == args.sandbox_workers
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
