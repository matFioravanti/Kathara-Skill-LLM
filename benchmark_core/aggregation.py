"""Rigenera integralmente entrambi i CSV usando solo gli artefatti in runs/."""
from pathlib import Path
import json

import pandas as pd

from .checker_runner import CATEGORIES, REPORT_COLUMNS, parse_reports
from .inspect_adapter import create_inspect_eval_log
from .inspect_metrics import METRIC_COLUMNS, extract_metrics

RUN_COLUMNS = [
    "run_id", "scenario_id", "repetition", "agent", "model", "provider", "agent_version",
    "execution_backend", "authentication", "api_key_used",
    "dns_skill_sha256", "dns_skill_bundle_sha256", "checker_skill_sha256", "checker_schema_sha256",
    "component_versions", "pipeline_state", "aut_execution_success", "correction_generation_success",
    "checker_execution_success", "task_success", "checks_passed", "checks_failed", "checks_total",
    "check_pass_rate", *[f"{c}_pass_rate" for c in CATEGORIES],
    *[x for x in METRIC_COLUMNS if x not in ("model", "provider")],
    "files_created", "files_modified", "files_deleted", "files_changed", "lines_added", "lines_deleted",
    "started_at", "completed_at", "pipeline_error", "checker_problems", "detailed_report_available",
    "aggregation_error",
]
DETAIL_COLUMNS = ["run_id", "scenario_id", "repetition", "agent", *REPORT_COLUMNS]


def aggregate(runs: Path, results: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary, details = [], []
    for metadata_path in sorted(runs.glob("*/manifest.json")):
        run = metadata_path.parent
        row = dict.fromkeys(RUN_COLUMNS)
        row["run_id"] = run.name
        errors = []
        try:
            metadata = json.loads(metadata_path.read_text())
        except (ValueError, OSError) as exc:
            row["aggregation_error"] = str(exc)
            summary.append(row)
            continue
        row.update({k: v for k, v in metadata.items() if k in row})
        row["component_versions"] = json.dumps(metadata.get("component_versions", {}), sort_keys=True)
        aut_logs = run / "logs/aut"
        try:
            # Assicura presenza del log nativo Inspect AI (.eval)
            eval_files = list(aut_logs.glob("*.eval"))
            if not eval_files and (aut_logs / "result.json").exists():
                create_inspect_eval_log(
                    logs=aut_logs,
                    run_id=run.name,
                    prompt="",
                    agent=metadata.get("agent", "codex"),
                    model=metadata.get("model"),
                )
                eval_files = list(aut_logs.glob("*.eval"))

            if eval_files:
                metrics = extract_metrics(aut_logs)
            elif metadata.get("agent") == "antigravity":
                from .antigravity_metrics import extract_metrics as antigravity_extract
                metrics = antigravity_extract(aut_logs)
            else:
                from .codex_metrics import extract_metrics as codex_extract
                metrics = codex_extract(aut_logs)

            # In assenza di log conserva il modello richiesto nei metadata.
            row.update({k: v for k, v in metrics.items() if v is not None})
        except Exception as exc:
            row["metrics_error"] = f"{type(exc).__name__}: {exc}"
            errors.append(row["metrics_error"])
        diff = run / "logs/diff.json"
        if diff.exists():
            try:
                row.update({k: v for k, v in json.loads(diff.read_text()).items() if k in row})
            except (ValueError, OSError) as exc:
                errors.append(f"Diff: {exc}")
        # Mai recuperare task_success da metadati, da un LLM o dall'esito AUT.
        row["task_success"] = None
        if metadata.get("checker_execution_success") is True and metadata.get("correction_generation_success") is True:
            try:
                execution = json.loads((run / "logs/checker_execution.json").read_text())
                if execution["returncode"] != 0 or execution["timed_out"]:
                    raise ValueError("Esecuzione checker non riuscita.")
                checker, check_rows = parse_reports(run / "results")
                row.update(checker)
                identity = {k: row[k] for k in DETAIL_COLUMNS if k not in REPORT_COLUMNS}
                details.extend({**identity, **check} for check in check_rows)
            except Exception as exc:
                row["checker_execution_success"] = False
                row["task_success"] = None
                row["pipeline_state"] = "CHECKER_FAILED"
                errors.append(f"Report checker: {type(exc).__name__}: {exc}")
        row["aggregation_error"] = "\n".join(errors) or None
        summary.append(row)
    summary_frame = pd.DataFrame(summary, columns=RUN_COLUMNS)
    detail_frame = pd.DataFrame(details, columns=DETAIL_COLUMNS)
    results.mkdir(parents=True, exist_ok=True)
    for filename, frame in (("benchmark_results.csv", summary_frame), ("benchmark_detailed.csv", detail_frame)):
        temporary = results / f"{filename}.tmp"
        frame.to_csv(temporary, index=False, na_rep="")
        temporary.replace(results / filename)
    return summary_frame, detail_frame
