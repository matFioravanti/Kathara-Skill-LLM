"""Orchestrazione sequenziale; la finestra AUT termina prima del generatore."""
from pathlib import Path
import hashlib
import json
import shutil
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


def run_one(config, scenario, agent: str, prompt_type: str, skill_mode: str | None = None,
            ui_context: dict | None = None, event_callback=None) -> Path:
    skill_mode = skill_mode or "dns_only"
    skill_selection = mode_details(skill_mode)
    correction_source = scenario.correction
    correction_source_relative = correction_path(config.root, scenario.scenario_id).relative_to(config.root).as_posix()
    correction_content, correction_sha256 = read_correction(correction_source)
    from .prompts import resolve_prompt
    resolved_prompt = resolve_prompt(config.root, scenario.scenario_id, prompt_type)
    prompt_text = resolved_prompt.read_text(encoding="utf-8")
    total_started = time.monotonic()
    run = create_workspace(config.root / "runs", scenario, prompt_type, skill_mode, prompt_text)
    run_number = int(run.name[1:])
    run_id = logical_run_id(scenario.scenario_id, prompt_type, skill_mode, run_number)
    paths = skill_paths(config)
    context = ui_context or {}
    if event_callback:
        event_callback(
            "run_started", scenario_id=scenario.scenario_id, prompt_type=prompt_type,
            agent=agent, skill_mode=skill_mode, repetition=run_number,
            run_path=run.relative_to(config.root).as_posix(), **context,
        )
    manifest = {
        "run_id": run_id, "run_number": run_number,
        "scenario_id": scenario.scenario_id, "prompt_type": prompt_type, "repetition": run_number,
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
        "prompt_sha256": hashlib.sha256(resolved_prompt.read_bytes()).hexdigest(),
        "prompt_source": str(resolved_prompt.relative_to(config.root)),
        "dns_skill_sha256": hashlib.sha256(paths["dns"].read_bytes()).hexdigest(),
        "dns_skill_bundle_sha256": tree_hash(paths["dns"].parent),
        "correction_source": correction_source_relative,
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
        if value.startswith("CHECKER"):
            details = "logs/checker_stderr.log"
        elif value.startswith("AUT"):
            details = "logs/aut/stderr.log"
        else:
            details = "evaluation/correction.yaml"
        if event_callback:
            event_callback(
                "pipeline_state", state=value, error=manifest.get("pipeline_error"),
                details_path=str(run / details) if value.endswith("FAILED") or value in (
                    "CORRECTION_MISSING", "CORRECTION_INVALID") else None,
            )

    stage = "AUT"
    checker_seconds = None
    checker_outcome = None
    try:
        state("PENDING")
        state("AUT_RUNNING")
        try:
            run_aut(config, scenario, run, agent, prompt_text, skill_mode=skill_mode, run_id=run_id)
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
        if event_callback:
            event_callback("correction_ready")
            event_callback("checker_running")
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
        if event_callback:
            event_callback("metrics_collected")
            event_callback("result", metrics={**metrics, "task_success": manifest.get("task_success")})
    return run


def reevaluate_run(config, run: Path) -> Path:
    """Riesegue solo checker/evaluation su una run AUT completata, in-place."""
    from .correction_input import InvalidCorrectionError, MissingCorrectionError

    manifest_path = run / "manifest.json"
    if not manifest_path.is_file() or not (run / "lab").is_dir() or not (run / "input/lab").is_dir():
        raise ValueError(f"Run incompleta: attesi manifest.json, lab/ e input/lab/: {run}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("aut_execution_success") is not True or manifest.get("pipeline_state") not in (
        "AUT_COMPLETED", "COMPLETED", "CHECKER_FAILED", "CORRECTION_MISSING", "CORRECTION_INVALID"
    ):
        raise ValueError(f"AUT non completato; run non rivalutata: {run}")

    scenario_id = manifest.get("scenario_id")
    source = correction_path(config.root, scenario_id)
    # read_correction valida prima che qualunque snapshot/report esistente venga toccato.
    content, digest = read_correction(source)
    previous_total_seconds = _metric_total_seconds(run)
    source_lab_hash = tree_hash(run / "lab")
    input_lab_hash = tree_hash(run / "input/lab")
    evaluation = run / "evaluation"
    evaluation.mkdir(parents=True, exist_ok=True)
    snapshot = evaluation / "correction.yaml"
    snapshot.write_bytes(content)
    if validate_correction(snapshot) != digest:
        raise InvalidCorrectionError(f"Invalid correction snapshot: {snapshot}")

    manifest["correction_source"] = source.relative_to(config.root).as_posix()
    manifest["correction_snapshot"] = "evaluation/correction.yaml"
    manifest["correction_sha256"] = digest
    manifest["checker_execution_success"] = None
    manifest["task_success"] = None
    manifest.pop("pipeline_error", None)
    results = run / "results"
    # Elimina solo report checker noti, senza toccare altri artefatti della run.
    for relative in ("results.csv", "lab/lab_result_all.csv", "lab/lab_result_failed.csv",
                     "lab/lab_result_summary.csv", "lab/lab_result.xlsx"):
        (results / relative).unlink(missing_ok=True)
    (results / "lab").mkdir(parents=True, exist_ok=True)
    if results.exists():
        (results / "lab" / "results.csv").unlink(missing_ok=True)

    for name in ("checker_invocation.json", "checker_execution.json", "checker_stdout.log", "checker_stderr.log"):
        (run / "logs" / name).unlink(missing_ok=True)
    started = time.monotonic()
    outcome = None
    try:
        outcome = run_checker(config, run, snapshot)
        manifest["checker_execution_success"] = True
        manifest["task_success"] = outcome["task_success"]
        manifest["pipeline_state"] = "COMPLETED"
        manifest.setdefault("state_history", []).append({"state": "COMPLETED", "timestamp": utc_now()})
    except Exception as exc:
        if isinstance(exc, MissingCorrectionError):
            state = "CORRECTION_MISSING"
        elif isinstance(exc, InvalidCorrectionError):
            state = "CORRECTION_INVALID"
        else:
            state = "CHECKER_FAILED"
        manifest["checker_execution_success"] = False
        manifest["task_success"] = None
        manifest["pipeline_state"] = state
        manifest["pipeline_error"] = f"{type(exc).__name__}: {exc}"
        manifest.setdefault("state_history", []).append({"state": state, "timestamp": utc_now()})
        (run / "logs").mkdir(parents=True, exist_ok=True)
        (run / "logs/pipeline_error.log").write_text(traceback.format_exc())
    checker_seconds = time.monotonic() - started
    if tree_hash(run / "lab") != source_lab_hash or tree_hash(run / "input/lab") != input_lab_hash:
        raise RuntimeError("Il checker ha alterato lab/ o input/lab/.")
    manifest["completed_at"] = utc_now()
    write_json(manifest_path, manifest)
    metrics = make_metrics(run, manifest,
                           total_seconds=previous_total_seconds,
                           checker_seconds=checker_seconds,
                           checker_outcome=outcome)
    # Nessun report valido dopo un errore tecnico: non recuperare conteggi da artefatti parziali.
    if outcome is None:
        metrics["checker"] = {"passed": None, "failed": None, "total": None, "pass_rate": None}
    write_json(evaluation / "metrics.json", metrics)
    print_run_summary({**metrics, "task_success": manifest.get("task_success")})
    return run


def _metric_total_seconds(run: Path):
    """Conserva il tempo AUT/complessivo storico leggendo le metriche precedenti."""
    import json
    try:
        metrics = json.loads((run / "evaluation/metrics.json").read_text(encoding="utf-8"))
        value = (metrics.get("timing") or {}).get("total_seconds")
        return value if isinstance(value, (int, float)) else None
    except (OSError, ValueError, AttributeError):
        return None
