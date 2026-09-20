"""Orchestrazione sequenziale; la finestra AUT termina prima del generatore."""
from pathlib import Path
import hashlib
import traceback

from .correction_generator import generate_correction
from .checker_runner import run_checker
from .config import skill_paths
from .diff_metrics import compute_diff
from .inspect_runner import run_aut
from .workspace import component_versions, create_workspace, tree_hash, utc_now, write_json


def run_one(config, scenario, agent: str, repetition: int) -> Path:
    run = create_workspace(config.root / "runs", scenario, agent, repetition)
    paths = skill_paths(config)
    manifest = {
        "run_id": run.name, "scenario_id": scenario.scenario_id, "repetition": repetition,
        "agent": agent, "agent_version": config.data["aut"]["version"], "model": config.model(),
        "reasoning_effort": config.reasoning_effort(),
        "execution_backend": "codex_cli", "authentication": "local_chatgpt_login", "api_key_used": False,
        "correction_model": config.model("correction_generator"),
        "correction_agent_version": config.data["correction_generator"]["version"],
        "started_at": utc_now(), "completed_at": None,
        "component_versions": component_versions(), "pipeline_state": "PENDING", "state_history": [],
        "aut_execution_success": None, "correction_generation_success": None,
        "checker_execution_success": None, "task_success": None,
        "source_lab_sha256": tree_hash(scenario.lab),
        "input_lab_sha256": tree_hash(run / "input/lab"),
        "prompt_sha256": hashlib.sha256(scenario.prompt.encode()).hexdigest(),
        "dns_skill_sha256": hashlib.sha256(paths["dns"].read_bytes()).hexdigest(),
        "dns_skill_bundle_sha256": tree_hash(paths["dns"].parent),
        "checker_skill_sha256": hashlib.sha256(paths["lab_checker"].read_bytes()).hexdigest(),
        "checker_schema_sha256": hashlib.sha256(paths["checker_schema"].read_bytes()).hexdigest(),
        "sandbox_image": config.data["sandbox"]["image"],
        "timeout_seconds": config.data["benchmark"]["timeout_seconds"],
        "artifacts": {
            "input_lab": "input/lab",
            "lab": "lab",
            "aut_logs": "logs/aut",
            "correction": "correction.yaml",
            "generator_logs": "logs/generator",
            "results": "results",
        },
    }

    def state(value: str):
        manifest["pipeline_state"] = value
        manifest["state_history"].append({"state": value, "timestamp": utc_now()})
        write_json(run / "manifest.json", manifest)
        print(f"{run.name}: {value}", flush=True)

    state("PENDING")
    stage = "AUT"
    try:
        state("AUT_RUNNING")
        try:
            run_aut(config, scenario, run, agent)
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
        stage = "CORRECTION"
        generate_correction(config, scenario, run)
        manifest["correction_generation_success"] = True
        write_json(run / "manifest.json", manifest)
        stage = "CHECKER"
        outcome = run_checker(config, run)
        manifest["checker_execution_success"] = True
        manifest["task_success"] = outcome["task_success"]
        if tree_hash(run / "lab") != manifest["final_lab_sha256"]:
            raise RuntimeError("Lab AUT alterato durante il checker.")
        if tree_hash(run / "input/lab") != manifest["input_lab_sha256"]:
            raise RuntimeError("Il baseline input/lab è cambiato durante la run.")
        state("COMPLETED")
    except (Exception, KeyboardInterrupt) as exc:
        failure_state, field = {
            "AUT": ("AUT_FAILED", "aut_execution_success"),
            "CORRECTION": ("CORRECTION_GENERATION_FAILED", "correction_generation_success"),
            "CHECKER": ("CHECKER_FAILED", "checker_execution_success"),
        }[stage]
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
    return run
