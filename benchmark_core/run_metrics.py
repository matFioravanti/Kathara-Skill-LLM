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


def observed_skills(events: list[dict], available: list[str]) -> list[str]:
    """Only marks a skill when a traced read command names its SKILL.md file.
    
    Observed skills represent only skills for which the trace contains observable evidence of reading the corresponding SKILL.md. They do not represent native Codex skill selection when the CLI does not expose skill-loading events.
    """
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


def forced_skill_satisfaction(forced: list[str] | None, observed: list[str] | None, observation_status: str | None = None) -> tuple[bool | None, list[str]]:
    """Computes whether all forced skills were observed in the trace.

    Returns (forced_skills_satisfied, missing_forced_skills).
    - If forced is None or empty (no_skill / auto): returns (None, []).
    - If observed contains all forced skills: returns (True, []).
    - If observation_status == "native_loading_unobservable" and there are missing skills: returns (None, missing_forced_skills).
    """
    if not forced:  # None or empty list -> no forcing (no_skill / auto)
        return None, []
    if observed is None:
        # Trace not available
        return None, []
    missing = [name for name in forced if name not in observed]
    
    if len(missing) == 0:
        return True, []
    
    if observation_status == "native_loading_unobservable":
        return None, missing
        
    return False, missing


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
        observed = None
    else:
        tokens = codex_usage(events)
        observed = observed_skills(events, available or [])
    agent_seconds = _duration(logs / "result.json", "duration_seconds")
    status = metadata.get("pipeline_state", metadata.get("status"))
    agent_success = metadata.get("aut_execution_success")
    correction_sha = metadata.get("correction_sha256")
    forced = metadata.get("forced_skills") if isinstance(metadata.get("forced_skills"), list) else None
    
    protocol = metadata.get("skill_protocol")
    if metadata.get("skill_mode") == "no_skill":
        observation_status = "not_applicable"
    elif metadata.get("skill_mode") == "auto":
        observation_status = "native_loading_unobservable"
    elif protocol == "explicit_read_v1":
        observation_status = "explicit_read_checkpoint"
    else:
        observation_status = "native_loading_unobservable" if agent == "codex" else None
        
    satisfied, missing = forced_skill_satisfaction(forced, observed, observation_status)
    return {
        "scenario": metadata.get("scenario_id", metadata.get("scenario")),
        "scenario_id": metadata.get("scenario_id", metadata.get("scenario")),
        "prompt_type": metadata.get("prompt_type"),
        "prompt_sha256": metadata.get("prompt_sha256"),
        "prompt_sent_sha256": metadata.get("prompt_sent_sha256"),
        "skill_mode": metadata.get("skill_mode"),
        "skill_protocol": protocol,
        "run_number": metadata.get("run_number", metadata.get("repetition")),
        "replicate": metadata.get("replicate"),
        "experiment_id": metadata.get("experiment_id"),
        "run_id": metadata.get("run_id"),
        "agent": agent,
        "model": metadata.get("model"),
        "reasoning_effort": metadata.get("reasoning_effort"),
        "available_skills": available,
        "forced_skills": forced,
        "observed_skills": observed,
        "skill_observation_status": observation_status,
        "forced_skills_satisfied": satisfied,
        "missing_forced_skills": missing,
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
        "evaluation_revision": metadata.get("evaluation_revision", 0),
        "last_reevaluated_at": metadata.get("last_reevaluated_at"),
    }



def print_run_summary(metrics: dict) -> None:
    from .terminal_ui import result
    result(metrics)
