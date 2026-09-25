"""Metriche normalizzate della run, derivate da trace e risultati conservati."""
from pathlib import Path
import json
import re

from .checker_runner import checker_test_rows, parse_reports

CODEX_READ_COMMAND = re.compile(r"\b(cat|sed|head|tail|less|more|bat|awk|grep|rg)\b")


def load_jsonl(path: Path) -> tuple[list[dict], bool]:
    events = []
    if not path.is_file():
        return events, False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events, bool(events)


def codex_usage(events: list[dict]) -> dict:
    """Il runner supporta turn.completed.usage; l'ultimo usage è il totale finale.

    Non somma turni completati e non ricava total_tokens dai componenti.
    """
    final_usage = None
    for event in events:
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            final_usage = event["usage"]
    if final_usage is None:
        return {
            "input": None, "cached_input": None, "output": None,
            "reasoning": None, "total": None, "cache_write_input": None,
        }
    return {
        "input": _token_value(final_usage.get("input_tokens")),
        "cached_input": _token_value(final_usage.get("cached_input_tokens")),
        "output": _token_value(final_usage.get("output_tokens")),
        "reasoning": _token_value(final_usage.get("reasoning_output_tokens")),
        "total": _token_value(final_usage.get("total_tokens")),
        "cache_write_input": _token_value(final_usage.get("cache_write_input_tokens")),
    }


def antigravity_usage(events: list[dict]) -> dict:
    final_usage = None
    for event in events:
        if event.get("event") == "result" and isinstance(event.get("result"), dict):
            usage = event["result"].get("usage")
            if isinstance(usage, dict):
                final_usage = usage
    if final_usage is None:
        return codex_usage([])
    return {
        "input": _token_value(final_usage.get("input_tokens")),
        "cached_input": _token_value(final_usage.get("cache_read_tokens")),
        "output": _token_value(final_usage.get("output_tokens")),
        "reasoning": _token_value(final_usage.get("thinking_tokens")),
        "total": _token_value(final_usage.get("total_tokens")),
        "cache_write_input": _token_value(final_usage.get("cache_write_tokens")),
    }


def _token_value(value):
    return value if type(value) is int and value >= 0 else None


def selected_skills(events: list[dict], available: list[str]) -> list[str]:
    """Only marks a skill when a traced read command names its SKILL.md file."""
    candidates = available
    found = set()
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        if item.get("status", "completed") != "completed":
            continue
        if item.get("exit_code") not in (None, 0):
            continue
        command = item.get("command")
        if not isinstance(command, str):
            continue
        read_commands = CODEX_READ_COMMAND.findall(command)
        if not read_commands or not any(name != "rg" for name in read_commands):
            if not ("rg" in read_commands and not re.search(r"\brg\s+--files\b", command)):
                continue
        if "rg" in read_commands and "rg --files" in command and not any(
            name != "rg" for name in read_commands
        ):
            continue
        for name in candidates:
            if re.search(rf"(?:^|[/\s'\"]){re.escape(name)}/SKILL\.md(?:$|[\s'\";|&])", command):
                found.add(name)
    return [name for name in candidates if name in found]


def _checker_summary(run: Path, outcome: dict | None) -> dict:
    if outcome is None:
        try:
            outcome, _ = parse_reports(run / "results")
        except Exception:
            try:
                partial = checker_test_rows(run / "results")
            except (OSError, ValueError, UnicodeError):
                partial = []
            passed = sum(row["passed"] for row in partial)
            failed = len(partial) - passed
            return {
                "passed": passed if partial else None,
                "failed": failed if partial else None,
                "total": len(partial) if partial else None,
                "pass_rate": passed / len(partial) if partial else None,
            }
    return {
        "passed": outcome.get("checks_passed"),
        "failed": outcome.get("checks_failed"),
        "total": outcome.get("checks_total"),
        "pass_rate": outcome.get("check_pass_rate"),
    }


def _duration(path: Path, key: str) -> float | None:
    try:
        value = json.loads(path.read_text()).get(key)
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def make_metrics(run: Path, metadata: dict, *, total_seconds: float | None,
                 checker_seconds: float | None, checker_outcome: dict | None) -> dict:
    logs = run / "logs/aut"
    events, trace_available = load_jsonl(logs / "events.jsonl")
    agent = metadata.get("agent")
    available = metadata.get("available_skills") if isinstance(metadata.get("available_skills"), list) else None
    if agent == "antigravity":
        tokens = antigravity_usage(events)
        selected = None
    else:
        tokens = codex_usage(events)
        selected = selected_skills(events, available or [])
    agent_seconds = _duration(logs / "result.json", "duration_seconds")
    status = metadata.get("pipeline_state", metadata.get("status"))
    agent_success = metadata.get("aut_execution_success")
    correction_sha = metadata.get("correction_sha256")
    return {
        "scenario": metadata.get("scenario_id", metadata.get("scenario")),
        "scenario_id": metadata.get("scenario_id", metadata.get("scenario")),
        "prompt_type": metadata.get("prompt_type"),
        "prompt_sha256": metadata.get("prompt_sha256"),
        "skill_mode": metadata.get("skill_mode"),
        "run_number": metadata.get("run_number", metadata.get("repetition")),
        "run_id": metadata.get("run_id"),
        "agent": agent,
        "model": metadata.get("model"),
        "reasoning_effort": metadata.get("reasoning_effort"),
        "available_skills": available,
        "forced_skills": metadata.get("forced_skills") if isinstance(metadata.get("forced_skills"), list) else None,
        "selected_skills": selected,
        "skill_trace_available": trace_available if agent != "antigravity" else False,
        "agent_success": agent_success,
        "status": status,
        "timing": {
            "agent_seconds": agent_seconds,
            "checker_seconds": checker_seconds,
            "total_seconds": total_seconds,
        },
        "tokens": tokens,
        "checker": _checker_summary(run, checker_outcome),
        "correction_sha256": correction_sha,
    }


def print_run_summary(metrics: dict) -> None:
    checker = metrics["checker"]
    if checker["passed"] is None or checker["total"] is None:
        checker_text = "n/a"
    else:
        checker_text = f"{checker['passed']}/{checker['total']}"
        if checker["pass_rate"] is not None:
            checker_text += f" ({checker['pass_rate']:.2%})"
    total_tokens = metrics["tokens"].get("total")
    selected = metrics.get("selected_skills")
    elapsed = metrics["timing"].get("total_seconds")
    elapsed_text = f"{elapsed:.1f} s" if elapsed is not None else "n/a"
    print(
        f"Scenario: {metrics.get('scenario')} | Mode: {metrics.get('skill_mode')} | "
        f"Run: r{metrics.get('run_number') or 0:03d} | Status: {metrics.get('status')} | "
        f"Checker: {checker_text} | Time: {elapsed_text} | "
        f"Tokens: {total_tokens if total_tokens is not None else 'n/a'} | "
        f"Skills selected: {';'.join(selected) if selected else ('none' if selected == [] else 'n/a')}",
        flush=True,
    )
