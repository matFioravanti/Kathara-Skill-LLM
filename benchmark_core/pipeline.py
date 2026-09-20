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
    metadata = {
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
        "prompt_sha256": hashlib.sha256(scenario.prompt.encode()).hexdigest(),
        "dns_skill_sha256": hashlib.sha256(paths["dns"].read_bytes()).hexdigest(),
        "dns_skill_bundle_sha256": tree_hash(paths["dns"].parent),
        "checker_skill_sha256": hashlib.sha256(paths["lab_checker"].read_bytes()).hexdigest(),
        "checker_schema_sha256": hashlib.sha256(paths["checker_schema"].read_bytes()).hexdigest(),
        "sandbox_image": config.data["sandbox"]["image"],
        "timeout_seconds": config.data["benchmark"]["timeout_seconds"],
        "artifacts": {"lab": "workspace/lab", "aut_logs": "codex/aut", "diff": "diff/summary.json",
                      "correction": "checker/correction.yaml", "generator_logs": "checker/generator_logs",
                      "checker_input": "checker/input/lab", "checker_reports": "checker/reports"},
    }

    def state(value: str):
        metadata["pipeline_state"] = value
        metadata["state_history"].append({"state": value, "timestamp": utc_now()})
        write_json(run / "metadata.json", metadata)
        print(f"{run.name}: {value}", flush=True)

    state("PENDING")
    stage = "AUT"
    try:
        state("AUT_RUNNING")
        try:
            run_aut(config, scenario, run, agent)
            metadata["aut_execution_success"] = True
        finally:
            metadata["aut_measurement_ended_at"] = utc_now()
            # Anche un AUT interrotto può aver modificato file: conserva il diff parziale.
            try:
                compute_diff(scenario.lab, run / "workspace/lab", run / "diff/summary.json")
            except Exception as exc:
                metadata["diff_error"] = f"{type(exc).__name__}: {exc}"
                if metadata["aut_execution_success"]:
                    raise
        if tree_hash(scenario.lab) != metadata["source_lab_sha256"]:
            raise RuntimeError("Il laboratorio sorgente è cambiato durante la run.")
        metadata["final_lab_sha256"] = tree_hash(run / "workspace/lab")
        state("AUT_COMPLETED")
        stage = "CORRECTION"
        generate_correction(config, scenario, run)
        metadata["correction_generation_success"] = True
        write_json(run / "metadata.json", metadata)
        stage = "CHECKER"
        outcome = run_checker(config, run)
        metadata["checker_execution_success"] = True
        metadata["task_success"] = outcome["task_success"]
        if tree_hash(run / "workspace/lab") != metadata["final_lab_sha256"]:
            raise RuntimeError("Lab AUT alterato durante il checker.")
        state("COMPLETED")
    except (Exception, KeyboardInterrupt) as exc:
        failure_state, field = {
            "AUT": ("AUT_FAILED", "aut_execution_success"),
            "CORRECTION": ("CORRECTION_GENERATION_FAILED", "correction_generation_success"),
            "CHECKER": ("CHECKER_FAILED", "checker_execution_success"),
        }[stage]
        metadata[field] = False
        metadata["task_success"] = None
        metadata["pipeline_error"] = f"{type(exc).__name__}: {exc}"
        (run / "pipeline_error.log").write_text(traceback.format_exc())
        state(failure_state)
        if isinstance(exc, KeyboardInterrupt):
            raise
    finally:
        metadata["completed_at"] = utc_now()
        write_json(run / "metadata.json", metadata)
    return run
