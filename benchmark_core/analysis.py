"""Analisi descrittiva con denominatori espliciti e valori assenti esclusi."""
from pathlib import Path

import pandas as pd


def summarize(frame: pd.DataFrame) -> dict:
    success = frame["task_success"].astype("string").str.lower().map({"true": True, "false": False})
    known = success.notna()
    successful = success.eq(True).fillna(False)
    result = {"runs": len(frame), "evaluated_runs": int(known.sum()),
              "unscored_runs": int((~known).sum()),
              "task_success_rate": success[known].mean() if known.any() else None}
    for field in ("check_pass_rate", "total_tokens", "total_time", "working_time", "tool_calls",
                  "files_created", "files_modified", "files_deleted", "files_changed", "lines_added", "lines_deleted"):
        values = pd.to_numeric(frame[field], errors="coerce")
        result[f"{field}_n"] = int(values.notna().sum())
        result[f"{field}_mean"] = values.mean()
        result[f"{field}_median"] = values.median()
        if field in ("total_tokens", "total_time", "tool_calls"):
            result[f"{field}_std"] = values.std(ddof=1) if values.notna().sum() > 1 else None
        if field in ("total_tokens", "total_time"):
            result[f"successful_{field}_mean"] = values[successful].mean()
    calls = pd.to_numeric(frame["tool_calls"], errors="coerce")
    errors = pd.to_numeric(frame["tool_errors"], errors="coerce")
    paired = calls.notna() & errors.notna()
    denominator = calls[paired].sum()
    result["tool_error_rate"] = errors[paired].sum() / denominator if denominator > 0 else None
    result["tool_error_rate_runs"] = int(paired.sum())
    return result


def analyze(results: Path) -> pd.DataFrame:
    frame = pd.read_csv(results / "benchmark_results.csv")
    rows = [{"scope": "overall", "scenario_id": None, "agent": None, "model": None, **summarize(frame)}]
    # Le deviazioni standard per gruppo confrontano ripetizioni dello stesso esperimento.
    for identity, group in frame.groupby(["scenario_id", "agent", "model", "dns_skill_bundle_sha256"], dropna=False):
        rows.append(dict(scope="experiment", scenario_id=identity[0], agent=identity[1], model=identity[2],
                         dns_skill_bundle_sha256=identity[3], **summarize(group)))
    output = pd.DataFrame(rows)
    output.to_csv(results / "analysis_summary.csv", index=False, na_rep="")
    return output
