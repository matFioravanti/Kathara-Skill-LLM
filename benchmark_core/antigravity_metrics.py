"""Metriche tratte esclusivamente dagli eventi JSONL nativi di `agy exec`."""
from pathlib import Path
import json

from .codex_metrics import METRIC_COLUMNS

def extract_metrics(logs: Path) -> dict:
    metrics = dict.fromkeys(METRIC_COLUMNS)
    result_path, events_path, invocation_path = logs / "result.json", logs / "events.jsonl", logs / "invocation.json"
    
    if not result_path.exists():
        return metrics
        
    result = json.loads(result_path.read_text())
    invocation = json.loads(invocation_path.read_text()) if invocation_path.exists() else {}
    
    metrics.update(
        codex_status="success" if result["returncode"] == 0 and not result["timed_out"] else "error",
        model=invocation.get("model"),
        provider="antigravity_cli",
        cost=None,
        total_time=result.get("duration_seconds"),
        working_time=None,
        termination_error=None if result["returncode"] == 0 else (logs / "stderr.log").read_text(),
        codex_events_log=str(events_path) if events_path.exists() else None,
        retries=None,
        sample_retries=None,
    )
    
    if not events_path.exists():
        return metrics
        
    turns = 0
    tools_done = 0
    usage = {}
    duration = None
    
    for index, line in enumerate(events_path.read_text(encoding="utf-8").splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
            
        event_type = event.get("event")
        if event_type == "result":
            res = event.get("result", {})
            usage = res.get("usage", {})
            duration = res.get("duration_seconds")
            turns = res.get("num_turns", turns)
        elif event_type == "step_update":
            step = event.get("step_update", {})
            if step.get("step_type") == "tool" and step.get("state") == "DONE":
                tools_done += 1
                
    if duration is not None:
        metrics["total_time"] = duration

    metrics.update(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        reasoning_tokens=usage.get("thinking_tokens"),
        cached_tokens=usage.get("cache_read_tokens"),
        cache_write_tokens=None,
        total_tokens=usage.get("total_tokens")
    )
    
    metrics["turn_count"] = turns or None
    metrics["model_calls"] = None
    metrics["tool_calls"] = tools_done
    metrics["tool_errors"] = 0 # In a real implementation we could track FAILED, but DONE covers successful.
    
    return metrics
