"""Metriche tratte esclusivamente dagli eventi JSONL nativi di `codex exec`."""
from pathlib import Path
import json

METRIC_COLUMNS = [
    "codex_status", "model", "provider", "input_tokens", "output_tokens", "reasoning_tokens",
    "cached_tokens", "cache_write_tokens", "total_tokens", "cost", "total_time", "working_time",
    "turn_count", "model_calls", "tool_calls", "tool_errors", "retries", "sample_retries",
    "termination_error", "termination_limit", "codex_events_log", "metrics_error",
]


def extract_metrics(logs: Path) -> dict:
    metrics = dict.fromkeys(METRIC_COLUMNS)
    result_path, events_path, invocation_path = logs / "result.json", logs / "events.jsonl", logs / "invocation.json"
    if not result_path.exists():
        return metrics
    result = json.loads(result_path.read_text())
    invocation = json.loads(invocation_path.read_text()) if invocation_path.exists() else {}
    metrics.update(codex_status="success" if result["returncode"] == 0 and not result["timed_out"] else "error",
                   model=invocation.get("model"), provider="codex_cli", cost=None,
                   total_time=result.get("duration_seconds"), working_time=None,
                   termination_error=None if result["returncode"] == 0 else (logs / "stderr.log").read_text(),
                   codex_events_log=str(events_path) if events_path.exists() else None)
    usage = result.get("usage") or {}
    metrics.update(input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                   reasoning_tokens=usage.get("reasoning_output_tokens"),
                   cached_tokens=usage.get("cached_input_tokens"), cache_write_tokens=None)
    values = [usage.get("input_tokens"), usage.get("output_tokens")]
    metrics["total_tokens"] = sum(value for value in values if isinstance(value, int)) if all(isinstance(value, int) for value in values) else None
    if not events_path.exists():
        return metrics
    events, tools, failed_tools, turns = [], set(), set(), 0
    for index, line in enumerate(events_path.read_text(encoding="utf-8").splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(event)
        if event.get("type") == "turn.completed":
            turns += 1
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and item.get("type") in {"command_execution", "mcp_tool_call", "web_search"}:
            identifier = item.get("id", index)
            tools.add(identifier)
            if item.get("status") == "failed":
                failed_tools.add(identifier)
    metrics["turn_count"] = turns or None
    metrics["model_calls"] = None  # Codex JSONL non espone una chiamata provider per ogni evento.
    metrics["tool_calls"] = len(tools)
    metrics["tool_errors"] = len(failed_tools)
    metrics["retries"] = None
    metrics["sample_retries"] = None
    return metrics
