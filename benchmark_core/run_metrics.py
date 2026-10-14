"""Metriche normalizzate della run, derivate da trace e risultati conservati."""
from pathlib import Path
import json

from .checker_runner import checker_test_rows, parse_reports



def load_jsonl(path: Path) -> list[dict]:
    events = []
    if not path.is_file():
        return events
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def codex_usage(events: list[dict]) -> dict:
    """Il runner supporta turn.completed.usage; l'ultimo usage è il totale finale.

    Rende coerente il conteggio dei token tra JSON, CSV, Excel e Inspect:
    - Distingue il totale riportato dal modello da quello calcolato
    - Non duplica i reasoning token (i reasoning token sono già un sottoinsieme di output_tokens)
    """
    final_usage = None
    for event in events:
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            final_usage = event["usage"]
    if final_usage is None:
        return {
            "input": None, "cached_input": None, "output": None,
            "reasoning": None, "total": None, "total_reported": None,
            "total_calculated": None, "cache_write_input": None,
        }
    input_tokens = _token_value(final_usage.get("input_tokens"))
    cached_input = _token_value(final_usage.get("cached_input_tokens"))
    output_tokens = _token_value(final_usage.get("output_tokens"))
    reasoning_tokens = _token_value(final_usage.get("reasoning_output_tokens"))
    total_reported = _token_value(final_usage.get("total_tokens"))
    cache_write = _token_value(final_usage.get("cache_write_input_tokens"))
    total_calculated = (
        input_tokens + output_tokens
        if (input_tokens is not None and output_tokens is not None)
        else None
    )
    total = total_reported if total_reported is not None else total_calculated
    return {
        "input": input_tokens,
        "cached_input": cached_input,
        "output": output_tokens,
        "reasoning": reasoning_tokens,
        "total": total,
        "total_reported": total_reported,
        "total_calculated": total_calculated,
        "cache_write_input": cache_write,
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
    input_tokens = _token_value(final_usage.get("input_tokens"))
    cached_input = _token_value(final_usage.get("cache_read_tokens"))
    output_tokens = _token_value(final_usage.get("output_tokens"))
    reasoning_tokens = _token_value(final_usage.get("thinking_tokens"))
    total_reported = _token_value(final_usage.get("total_tokens"))
    cache_write = _token_value(final_usage.get("cache_write_tokens"))
    total_calculated = (
        input_tokens + output_tokens
        if (input_tokens is not None and output_tokens is not None)
        else None
    )
    total = total_reported if total_reported is not None else total_calculated
    return {
        "input": input_tokens,
        "cached_input": cached_input,
        "output": output_tokens,
        "reasoning": reasoning_tokens,
        "total": total,
        "total_reported": total_reported,
        "total_calculated": total_calculated,
        "cache_write_input": cache_write,
    }


def _token_value(value):
    return value if type(value) is int and value >= 0 else None




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


def _sandbox_meta(logs: Path) -> dict:
    """Legge sandbox_metadata.json se presente; restituisce dict vuoto altrimenti."""
    path = logs / "sandbox_metadata.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def make_metrics(run: Path, metadata: dict, *, total_seconds: float | None,
                 checker_seconds: float | None, checker_outcome: dict | None) -> dict:
    logs = run / "logs/aut"
    events = load_jsonl(logs / "events.jsonl")
    agent = metadata.get("agent")
    available = metadata.get("available_skills") if isinstance(metadata.get("available_skills"), list) else None
    if agent == "antigravity":
        tokens = antigravity_usage(events)
    else:
        tokens = codex_usage(events)
    agent_seconds = _duration(logs / "result.json", "duration_seconds")
    sandbox_overhead = _duration(logs / "result.json", "sandbox_overhead_seconds")
    sandbox_meta = _sandbox_meta(logs)
    status = metadata.get("pipeline_state", metadata.get("status"))
    agent_success = metadata.get("aut_execution_success")
    correction_sha = metadata.get("correction_sha256")
    forced = metadata.get("forced_skills") if isinstance(metadata.get("forced_skills"), list) else None
    
    protocol = metadata.get("skill_protocol")
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
        "agent_success": agent_success,
        "status": status,
        "execution_backend": metadata.get("execution_backend"),
        "authentication": metadata.get("authentication") or (
            "sbx_oauth_proxy" if metadata.get("execution_backend") == "docker_sandbox" else None
        ),
        "codex_host_version": metadata.get("codex_host_version") or sandbox_meta.get("codex_host_version"),
        "codex_sandbox_version": metadata.get("codex_sandbox_version") or sandbox_meta.get("codex_sandbox_version"),
        "sandbox": {
            "name": sandbox_meta.get("sandbox_name"),
            "id": sandbox_meta.get("sandbox_id"),
            "sbx_version": sandbox_meta.get("sbx_version"),
            "codex_host_version": sandbox_meta.get("codex_host_version"),
            "codex_sandbox_version": sandbox_meta.get("codex_sandbox_version"),
            "cleanup_ok": sandbox_meta.get("cleanup_ok"),
            "cleanup_error": sandbox_meta.get("cleanup_error"),
        } if sandbox_meta else None,
        "timing": {
            "agent_seconds": agent_seconds,
            "sandbox_overhead_seconds": sandbox_overhead,
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
