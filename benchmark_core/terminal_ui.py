"""Rendering testuale deterministico dell'esecuzione benchmark."""
from __future__ import annotations


_STATE_LINES = {
    "PENDING": ("✓", "Prepare run"),
    "AUT_RUNNING": ("•", "AUT running"),
    "AUT_COMPLETED": ("✓", "AUT completed"),
    "CHECKER_FAILED": ("✗", "Checker failed"),
    "AUT_FAILED": ("✗", "AUT failed"),
    "CORRECTION_MISSING": ("✗", "Correction missing"),
    "CORRECTION_INVALID": ("✗", "Correction invalid"),
    "COMPLETED": ("✓", "Checker completed"),
}


def _rule(title: str, width: int = 64) -> str:
    label = f" {title} "
    return label.center(width, "─")


def benchmark_header(scenario_id: str, prompt_type: str, agent: str, skill_mode: str,
                     repetition: int, run_path: str, run_index: int | None = None,
                     run_total: int | None = None) -> None:
    if run_index is not None and run_total is not None:
        print(f"\n{_rule(f'RUN {run_index} / {run_total}')}")
        print(f"\n {skill_mode} · r{repetition:03d}")
        print(f" Run path\n {run_path}\n")
    else:
        print("╭──────────────────────────────────────────────────────────────╮")
        print("│                  KATHARA SKILL BENCHMARK                     │")
        print("╰──────────────────────────────────────────────────────────────╯")
        print(f"\n Scenario       {scenario_id}")
        print(f" Prompt         {prompt_type}")
        print(f" Agent          {agent}")
        print(f" Skill mode     {skill_mode}")
        print(f" Repetition     r{repetition:03d}")
        print(f"\n Run path\n {run_path}")
    print(f"\n{_rule('PIPELINE')}\n", flush=True)


def scenario_header(index: int, total: int, scenario_id: str, prompt_type: str) -> None:
    print(f"\n╭─ Scenario {index} / {total} {'─' * 42}╮")
    print(f"│ {scenario_id} · {prompt_type}")
    print(f"╰{'─' * 64}╯\n", flush=True)


def pipeline_event(label: str, *, success: bool = True) -> None:
    symbol = "•" if label.endswith("running") else "✓" if success else "✗"
    print(f"  {symbol}  {label}", flush=True)


def skill_details(mode: str, available: list[str], forced: list[str]) -> None:
    print(f" Available skills  {', '.join(available) or 'none'}")
    print(f" Forced skills     {', '.join(forced) or 'none'}\n", flush=True)


def pipeline_state(state: str, *, error: str | None = None, details_path: str | None = None) -> None:
    symbol, label = _STATE_LINES.get(state, ("•", state.replace("_", " ").capitalize()))
    print(f"  {symbol}  {label}", flush=True)
    if state.endswith("FAILED") or state in ("CORRECTION_MISSING", "CORRECTION_INVALID"):
        if error:
            print(f"\n  Error\n  {error}", flush=True)
        if details_path:
            print(f"\n  Details\n  {details_path}", flush=True)


def result(metrics: dict) -> None:
    checker = metrics.get("checker") or {}
    timing = metrics.get("timing") or {}
    tokens = metrics.get("tokens") or {}
    print(f"\n{_rule('RESULT')}")
    _metric("Checks", _pair(checker.get("passed"), checker.get("total")))
    rate = checker.get("pass_rate")
    _metric("Pass rate", f"{rate:.2%}" if isinstance(rate, (int, float)) else None)
    task_success = metrics.get("task_success")
    _metric("Task success", "PASS" if task_success is True else "FAIL" if task_success is False else None)
    _metric("Input tokens", _integer(tokens.get("input")))
    _metric("Output tokens", _integer(tokens.get("output")))
    duration = timing.get("total_seconds")
    _metric("Duration", f"{duration:.1f} s" if isinstance(duration, (int, float)) else None)
    status = metrics.get("status")
    symbol = "✓" if status == "COMPLETED" else "✗"
    identity = [metrics.get("scenario"), metrics.get("prompt_type"), metrics.get("skill_mode")]
    identity = [str(value) for value in identity if value]
    identity.append(f"r{metrics.get('run_number'):03d}" if isinstance(metrics.get("run_number"), int) else None)
    label = " · ".join(value for value in identity if value)
    print(f"\n {symbol} {label} {'completed' if status == 'COMPLETED' else 'failed'}\n", flush=True)


def _metric(label: str, value: str | None) -> None:
    if value is not None:
        print(f" {label:<16} {value}")


def _pair(value, total) -> str | None:
    if isinstance(value, (int, float)) and isinstance(total, (int, float)):
        return f"{int(value)} / {int(total)}"
    return None


def _integer(value) -> str | None:
    return f"{value:,}" if isinstance(value, int) else None


def result_table(rows: list[dict], *, multiple_scenarios: bool) -> None:
    if len(rows) < 2:
        return
    columns = (["Scenario", "Prompt", "Skill mode", "Repetition", "Result", "Checks", "Pass rate", "Duration"]
               if multiple_scenarios else
               ["Skill mode", "Repetition", "Result", "Checks", "Pass rate", "Duration"])
    data = []
    for row in rows:
        metrics = row["metrics"]
        checker = metrics.get("checker") or {}
        timing = metrics.get("timing") or {}
        task_result = metrics.get("task_success")
        result_label = ("PASS" if task_result is True else "FAIL" if task_result is False else
                        "COMPLETED" if metrics.get("status") == "COMPLETED" else "FAILED")
        values = {
            "Scenario": metrics.get("scenario"), "Prompt": metrics.get("prompt_type"),
            "Skill mode": metrics.get("skill_mode"), "Repetition": f"r{metrics.get('run_number') or 0:03d}",
            "Result": result_label,
            "Checks": _pair(checker.get("passed"), checker.get("total")) or "—",
            "Pass rate": f"{checker['pass_rate']:.2%}" if isinstance(checker.get("pass_rate"), (int, float)) else "—",
            "Duration": f"{timing['total_seconds']:.1f} s" if isinstance(timing.get("total_seconds"), (int, float)) else "—",
        }
        data.append([str(values[column] or "—") for column in columns])
    widths = [max(len(column), *(len(row[i]) for row in data)) for i, column in enumerate(columns)]
    print(f"\n{_rule('RUN SUMMARY')}")
    print("  " + "  ".join(column.ljust(widths[i]) for i, column in enumerate(columns)))
    print("  " + "  ".join("─" * width for width in widths))
    for row in data:
        print("  " + "  ".join(value.ljust(widths[i]) for i, value in enumerate(row)))
    print(flush=True)


def render_run_event(event: str, **data) -> None:
    """Render domain-neutral events emitted by the run orchestration."""
    if event == "run_started":
        benchmark_header(
            data["scenario_id"], data["prompt_type"], data["agent"], data["skill_mode"],
            data["repetition"], data["run_path"], data.get("run_index"), data.get("run_total"),
        )
        if "available_skills" in data:
            skill_details(data["skill_mode"], data["available_skills"], data.get("forced_skills", []))
    elif event == "pipeline_state":
        pipeline_state(data["state"], error=data.get("error"), details_path=data.get("details_path"))
    elif event == "correction_ready":
        pipeline_event("Correction ready")
    elif event == "checker_running":
        pipeline_event("Checker running", success=False)
    elif event == "metrics_collected":
        pipeline_event("Metrics collected")
    elif event == "result":
        result(data["metrics"])
