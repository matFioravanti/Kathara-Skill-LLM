"""Orchestrazione sequenziale; la finestra AUT termina prima del generatore."""
from pathlib import Path
import hashlib
import time
import traceback

from .checker_runner import run_checker
from .config import skill_paths
from .correction_input import correction_path, read_correction, validate_correction
from .diff_metrics import compute_diff
from .inspect_runner import run_aut
from .skill_modes import mode_details
from .run_metrics import make_metrics, print_run_summary
from .workspace import component_versions, create_workspace, logical_run_id, tree_hash, utc_now, write_json


def run_one(config, scenario, agent: str, skill_mode: str | None = None) -> Path:
    skill_mode = skill_mode or "dns_only"
    skill_selection = mode_details(skill_mode)
    correction_source = correction_path(config.root, scenario.scenario_id)
    correction_content, correction_sha256 = read_correction(correction_source)
    total_started = time.monotonic()
    run = create_workspace(config.root / "runs", scenario, skill_mode)
    run_number = int(run.name[1:])
    run_id = logical_run_id(scenario.scenario_id, skill_mode, run_number)
    paths = skill_paths(config)
    manifest = {
        "run_id": run_id, "run_number": run_number,
        "scenario_id": scenario.scenario_id, "repetition": run_number,
        "run_directory": str(run.relative_to(config.root / "runs")),
        "agent": agent, "agent_version": config.data["aut"]["version"], "model": config.model(),
        "reasoning_effort": config.reasoning_effort(),
        "execution_backend": f"{agent}_cli",
        "authentication": "local_chatgpt_login" if agent == "codex" else "local_google_login",
        "api_key_used": False,
        "skill_mode": skill_mode,
        "available_skills": list(skill_selection.available_skills) if skill_selection else [],
        "forced_skills": list(skill_selection.forced_skills) if skill_selection else [],
        "started_at": utc_now(), "completed_at": None,
        "component_versions": component_versions(), "pipeline_state": "PENDING", "state_history": [],
        "aut_execution_success": None,
        "checker_execution_success": None, "task_success": None,
        "source_lab_sha256": tree_hash(scenario.lab),
        "input_lab_sha256": tree_hash(run / "input/lab"),
        "prompt_sha256": hashlib.sha256(scenario.prompt.encode()).hexdigest(),
        "dns_skill_sha256": hashlib.sha256(paths["dns"].read_bytes()).hexdigest(),
        "dns_skill_bundle_sha256": tree_hash(paths["dns"].parent),
        "correction_source": correction_source.relative_to(config.root).as_posix(),
        "correction_sha256": correction_sha256,
        "sandbox_image": config.data["sandbox"]["image"],
        "timeout_seconds": config.data["benchmark"]["timeout_seconds"],
        "artifacts": {
            "input_lab": "input/lab",
            "lab": "lab",
            "aut_logs": "logs/aut",
            "inspect_eval_log": f"logs/aut/{run_id}.eval",
            "correction_snapshot": "evaluation/correction.yaml",
            "results": "results",
        },
    }

    def state(value: str):
        manifest["pipeline_state"] = value
        manifest["state_history"].append({"state": value, "timestamp": utc_now()})
        write_json(run / "manifest.json", manifest)
        print(f"{run_id}: {value}", flush=True)

    stage = "AUT"
    checker_seconds = None
    checker_outcome = None
    try:
        state("PENDING")
        state("AUT_RUNNING")
        try:
            run_aut(config, scenario, run, agent, skill_mode=skill_mode, run_id=run_id)
            manifest["aut_execution_success"] = True
        finally:
            manifest["aut_measurement_ended_at"] = utc_now()
            # Anche un AUT interrotto può aver modificato file: conserva il diff parziale.
            try:
                compute_diff(scenario.lab, run / "lab", run / "logs/diff.json")
            except Exception as exc:
                manifest["diff_error"] = f"{type(exc).__name__}: {exc}"
                if manifest["aut_execution_success"]:
                    raise
        if tree_hash(scenario.lab) != manifest["source_lab_sha256"]:
            raise RuntimeError("Il laboratorio sorgente è cambiato durante la run.")
        if tree_hash(run / "input/lab") != manifest["input_lab_sha256"]:
            raise RuntimeError("Il baseline input/lab è cambiato durante la run.")
        manifest["final_lab_sha256"] = tree_hash(run / "lab")
        state("AUT_COMPLETED")
        stage = "EVALUATION"
        evaluation = run / "evaluation"
        evaluation.mkdir()
        correction_snapshot = evaluation / "correction.yaml"
        correction_snapshot.write_bytes(correction_content)
        snapshot_digest = validate_correction(correction_snapshot)
        if snapshot_digest != correction_sha256:
            raise RuntimeError("Lo snapshot della correction non corrisponde all'input letto prima della run.")
        manifest["correction_snapshot"] = "evaluation/correction.yaml"
        write_json(run / "manifest.json", manifest)
        checker_started = time.monotonic()
        try:
            outcome = run_checker(config, run, correction_snapshot)
            checker_outcome = outcome
        finally:
            checker_seconds = time.monotonic() - checker_started
        manifest["checker_execution_success"] = True
        manifest["task_success"] = outcome["task_success"]
        if tree_hash(run / "lab") != manifest["final_lab_sha256"]:
            raise RuntimeError("Lab AUT alterato durante il checker.")
        if tree_hash(run / "input/lab") != manifest["input_lab_sha256"]:
            raise RuntimeError("Il baseline input/lab è cambiato durante la run.")
        state("COMPLETED")
    except (Exception, KeyboardInterrupt) as exc:
        if stage == "AUT":
            failure_state, field = "AUT_FAILED", "aut_execution_success"
        elif stage == "EVALUATION":
            from .correction_input import InvalidCorrectionError, MissingCorrectionError
            if isinstance(exc, MissingCorrectionError):
                failure_state, field = "CORRECTION_MISSING", "checker_execution_success"
            elif isinstance(exc, InvalidCorrectionError):
                failure_state, field = "CORRECTION_INVALID", "checker_execution_success"
            else:
                failure_state, field = "CHECKER_FAILED", "checker_execution_success"
        else:
            failure_state, field = "CHECKER_FAILED", "checker_execution_success"
        manifest[field] = False
        manifest["task_success"] = None
        manifest["pipeline_error"] = f"{type(exc).__name__}: {exc}"
        (run / "logs/pipeline_error.log").write_text(traceback.format_exc())
        state(failure_state)
        if isinstance(exc, KeyboardInterrupt):
            raise
    finally:
        manifest["completed_at"] = utc_now()
        write_json(run / "manifest.json", manifest)
        evaluation = run / "evaluation"
        evaluation.mkdir(parents=True, exist_ok=True)
        metrics = make_metrics(
            run, manifest,
            total_seconds=time.monotonic() - total_started,
            checker_seconds=checker_seconds,
            checker_outcome=checker_outcome,
        )
        write_json(evaluation / "metrics.json", metrics)
        print_run_summary(metrics)
    return run
