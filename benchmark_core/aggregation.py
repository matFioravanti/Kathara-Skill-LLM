"""Materializza CSV e workbook Excel dai metrics.json e dai report del checker."""
from pathlib import Path
import json

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .checker_runner import checker_test_rows

RUN_COLUMNS = [
    "scenario", "prompt_type", "prompt_sha256", "skill_mode", "run_number", "run_id", "agent", "model", "reasoning_effort",
    "available_skills", "forced_skills", "selected_skills", "status",
    "agent_seconds", "checker_seconds", "total_seconds",
    "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
    "tests_passed", "tests_failed", "tests_total", "pass_rate", "correction_sha256",
]
CHECK_COLUMNS = [
    "scenario", "prompt_type", "skill_mode", "run_number", "run_id", "test_description", "passed", "reason",
]
SUMMARY_COLUMNS = [
    "scenario", "prompt_type", "skill_mode", "runs", "successful_runs", "failed_runs",
    "mean_pass_rate", "min_pass_rate", "max_pass_rate",
    "mean_agent_seconds", "mean_total_seconds",
    "mean_input_tokens", "mean_output_tokens", "mean_total_tokens", "skill_selection_rate",
]
EXCEL_COLUMN_ORDER = {
    "Runs": [
        "scenario", "prompt_type", "skill_mode", "run_number", "status", "pass_rate", "tests_passed",
        "tests_failed", "tests_total", "agent_seconds", "checker_seconds", "total_seconds",
        "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
        "agent", "model", "reasoning_effort", "available_skills", "forced_skills",
        "selected_skills", "run_id", "correction_sha256",
    ],
    "Checks": ["scenario", "prompt_type", "skill_mode", "run_number", "passed", "test_description", "reason", "run_id"],
    "Summary": [
        "scenario", "skill_mode", "runs", "successful_runs", "failed_runs", "mean_pass_rate",
        "min_pass_rate", "max_pass_rate", "skill_selection_rate", "mean_agent_seconds",
        "mean_total_seconds", "mean_input_tokens", "mean_output_tokens", "mean_total_tokens",
    ],
}


def _list_cell(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    return value


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Il documento deve essere un oggetto JSON.")
    return value


def _row_from_metrics(metrics: dict) -> dict:
    timing = metrics.get("timing") or {}
    tokens = metrics.get("tokens") or {}
    checker = metrics.get("checker") or {}
    return {
        "scenario": metrics.get("scenario"),
        "prompt_type": metrics.get("prompt_type"),
        "prompt_sha256": metrics.get("prompt_sha256"),
        "skill_mode": metrics.get("skill_mode"),
        "run_number": metrics.get("run_number"),
        "run_id": metrics.get("run_id"),
        "agent": metrics.get("agent"),
        "model": metrics.get("model"),
        "reasoning_effort": metrics.get("reasoning_effort"),
        "available_skills": _list_cell(metrics.get("available_skills")),
        "forced_skills": _list_cell(metrics.get("forced_skills")),
        "selected_skills": _list_cell(metrics.get("selected_skills")),
        "status": metrics.get("status"),
        "agent_seconds": _number(timing.get("agent_seconds")),
        "checker_seconds": _number(timing.get("checker_seconds")),
        "total_seconds": _number(timing.get("total_seconds")),
        "input_tokens": _number(tokens.get("input")),
        "cached_input_tokens": _number(tokens.get("cached_input")),
        "output_tokens": _number(tokens.get("output")),
        "reasoning_tokens": _number(tokens.get("reasoning")),
        "total_tokens": _number(tokens.get("total")),
        "tests_passed": _number(checker.get("passed")),
        "tests_failed": _number(checker.get("failed")),
        "tests_total": _number(checker.get("total")),
        "pass_rate": _number(checker.get("pass_rate")),
        "correction_sha256": metrics.get("correction_sha256"),
    }


def _run_sort_key(row: dict):
    try:
        number = int(row.get("run_number"))
    except (TypeError, ValueError):
        number = -1
    return (str(row.get("scenario") or ""), str(row.get("prompt_type") or ""), str(row.get("skill_mode") or ""), number,
            str(row.get("run_id") or ""))


def _mean(values):
    usable = [_number(value) for value in values]
    usable = [value for value in usable if value is not None]
    return sum(usable) / len(usable) if usable else None


def _summary_rows(metrics_rows: list[dict]) -> list[dict]:
    groups = {}
    for metrics in metrics_rows:
        key = (metrics.get("scenario"), metrics.get("prompt_type"), metrics.get("skill_mode"))
        groups.setdefault(key, []).append(metrics)
    result = []
    for (scenario, prompt_type, skill_mode), group in sorted(
        groups.items(), key=lambda item: tuple(str(value or "") for value in item[0])
    ):
        pass_rates = [_number((row.get("checker") or {}).get("pass_rate")) for row in group]
        pass_rates = [value for value in pass_rates if value is not None]
        successful = sum(row.get("status") == "COMPLETED" for row in group)
        selection_rate = None
        if skill_mode == "auto":
            valid = [row for row in group if row.get("agent_success") is True
                     and row.get("skill_trace_available") is True
                     and isinstance(row.get("selected_skills"), list)]
            selection_rate = (sum(bool(row["selected_skills"]) for row in valid) / len(valid)
                              if valid else None)
        result.append({
            "scenario": scenario, "prompt_type": prompt_type, "skill_mode": skill_mode, "runs": len(group),
            "successful_runs": successful, "failed_runs": len(group) - successful,
            "mean_pass_rate": _mean(pass_rates),
            "min_pass_rate": min(pass_rates) if pass_rates else None,
            "max_pass_rate": max(pass_rates) if pass_rates else None,
            "mean_agent_seconds": _mean((row.get("timing") or {}).get("agent_seconds") for row in group),
            "mean_total_seconds": _mean((row.get("timing") or {}).get("total_seconds") for row in group),
            "mean_input_tokens": _mean((row.get("tokens") or {}).get("input") for row in group),
            "mean_output_tokens": _mean((row.get("tokens") or {}).get("output") for row in group),
            "mean_total_tokens": _mean((row.get("tokens") or {}).get("total") for row in group),
            "skill_selection_rate": selection_rate,
        })
    return result


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, na_rep="")
    temporary.replace(path)


def _atomic_excel(path: Path, frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]) -> None:
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    header_fill = PatternFill("solid", fgColor="17365D")
    header_font = Font(color="FFFFFF", bold=True)
    row_fills = (PatternFill("solid", fgColor="FFFFFF"), PatternFill("solid", fgColor="F2F6FA"))
    accent_fill = PatternFill("solid", fgColor="DCE6F1")
    separator = Side(style="medium", color="4472C4")
    bottom_border = Border(bottom=separator)
    widths = {
        "scenario": 22, "prompt_type": 14, "skill_mode": 18, "run_number": 13, "run_id": 42,
        "prompt_sha256": 68, "agent": 15, "model": 24, "reasoning_effort": 18, "available_skills": 32,
        "forced_skills": 32, "selected_skills": 32, "status": 20, "passed": 12,
        "test_description": 52, "reason": 52, "correction_sha256": 68,
    }
    with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
        for sheet, frame in zip(("Runs", "Checks", "Summary"), frames):
            excel_frame = frame[EXCEL_COLUMN_ORDER[sheet]]
            excel_frame.iloc[:0].to_excel(writer, sheet_name=sheet, index=False, na_rep="")
            worksheet = writer.sheets[sheet]
            worksheet.freeze_panes = "A2"
            worksheet.sheet_view.showGridLines = False
            worksheet.sheet_view.zoomScale = 90
            worksheet.sheet_properties.tabColor = "4472C4"
            worksheet.row_dimensions[1].height = 30
            for cell in worksheet[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            for column_index, column in enumerate(excel_frame.columns, start=1):
                worksheet.column_dimensions[worksheet.cell(1, column_index).column_letter].width = widths.get(
                    column, 16 if "token" in column or "seconds" in column else 15
                )

            cursor = 1
            scenario_groups = list(excel_frame.groupby("scenario", sort=False, dropna=False))
            for index, (_, block) in enumerate(scenario_groups):
                block.to_excel(writer, sheet_name=sheet, startrow=cursor, index=False,
                               header=False, na_rep="")
                end_row = cursor + len(block)
                fill = row_fills[index % len(row_fills)]
                for row_index in range(cursor + 1, end_row + 1):
                    worksheet.row_dimensions[row_index].height = 22
                    for cell in worksheet[row_index][:len(excel_frame.columns)]:
                        cell.fill = accent_fill if cell.column == 1 else fill
                        cell.alignment = Alignment(vertical="center", wrap_text=cell.column > 3)
                        if cell.column <= len(excel_frame.columns):
                            cell.border = bottom_border if row_index == end_row else Border()
                    if sheet == "Runs":
                        status_col = excel_frame.columns.get_loc("status") + 1
                        status_cell = worksheet.cell(row_index, status_col)
                        status_cell.fill = PatternFill(
                            "solid", fgColor="E2F0D9" if status_cell.value == "COMPLETED" else "FCE4D6"
                        )
                    elif sheet == "Checks":
                        passed_col = excel_frame.columns.get_loc("passed") + 1
                        passed_cell = worksheet.cell(row_index, passed_col)
                        passed_cell.fill = PatternFill(
                            "solid", fgColor="E2F0D9" if passed_cell.value is True else "FCE4D6"
                        )
                cursor = end_row + (1 if index < len(scenario_groups) - 1 else 0)
            if cursor > 1:
                worksheet.auto_filter.ref = f"A1:{worksheet.cell(cursor, len(excel_frame.columns)).coordinate}"
    temporary.replace(path)


def _saved_check_rows(run: Path) -> list[dict]:
    try:
        return checker_test_rows(run / "results")
    except (OSError, ValueError, UnicodeError):
        return []


def aggregate(runs: Path, results: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Rebuild the three CSVs and consolidated benchmark.xlsx from saved artifacts."""
    metrics_rows = []
    run_rows = []
    check_rows = []
    for metrics_path in sorted(runs.rglob("metrics.json")):
        try:
            relative_parts = metrics_path.relative_to(runs).parts
        except ValueError:
            continue
        if (len(relative_parts) != 6 or relative_parts[4:] != ("evaluation", "metrics.json")
                or not relative_parts[3].startswith("r")
                or not relative_parts[3][1:].isdigit()):
            continue
        run = metrics_path.parent.parent
        metrics = _read_json(metrics_path)
        metrics_rows.append(metrics)
        run_rows.append(_row_from_metrics(metrics))
        identity = {key: metrics.get(key) for key in ("scenario", "prompt_type", "skill_mode", "run_number", "run_id")}
        check_rows.extend({**identity, **check} for check in _saved_check_rows(run))

    run_rows.sort(key=_run_sort_key)
    check_rows.sort(key=lambda row: (*_run_sort_key(row), str(row.get("test_description") or "")))
    runs_frame = pd.DataFrame(run_rows, columns=RUN_COLUMNS)
    checks_frame = pd.DataFrame(check_rows, columns=CHECK_COLUMNS)
    summary_frame = pd.DataFrame(_summary_rows(metrics_rows), columns=SUMMARY_COLUMNS)

    results.mkdir(parents=True, exist_ok=True)
    _atomic_csv(results / "runs.csv", runs_frame)
    _atomic_csv(results / "checks.csv", checks_frame)
    _atomic_csv(results / "summary.csv", summary_frame)
    _atomic_excel(results / "benchmark.xlsx", (runs_frame, checks_frame, summary_frame))
    return runs_frame, checks_frame, summary_frame
