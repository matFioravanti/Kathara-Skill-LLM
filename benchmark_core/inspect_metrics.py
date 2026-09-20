"""Metriche esclusivamente dai log ufficiali della prima evaluation."""
from pathlib import Path
import json

from inspect_ai.log import read_eval_log

METRIC_COLUMNS = [
    "inspect_status", "model", "provider", "input_tokens", "output_tokens", "reasoning_tokens",
    "cached_tokens", "cache_write_tokens", "total_tokens", "cost", "total_time", "working_time",
    "turn_count", "model_calls", "tool_calls", "tool_errors", "retries", "sample_retries",
    "termination_error", "termination_limit", "inspect_log", "metrics_error",
]


def available_sum(values):
    values = list(values)
    return sum(values) if values and all(v is not None for v in values) else None


def events_recursive(events):
    for event in events:
        yield event
        yield from events_recursive(getattr(event, "events", []))


def extract_metrics(logs: Path) -> dict:
    metrics = dict.fromkeys(METRIC_COLUMNS)
    files = sorted(logs.glob("*.eval"))
    if not files:
        return metrics
    if len(files) != 1:
        raise ValueError(f"Atteso un solo log AUT, trovati {len(files)} in {logs}")
    log = read_eval_log(files[0])
    metrics.update(inspect_log=str(files[0]), inspect_status=log.status, model=log.eval.model,
                   provider=log.eval.model.split("/", 1)[0] if "/" in log.eval.model else None)
    usage = list(log.stats.model_usage.values())
    for column, field in {
        "input_tokens": "input_tokens", "output_tokens": "output_tokens", "total_tokens": "total_tokens",
        "reasoning_tokens": "reasoning_tokens", "cached_tokens": "input_tokens_cache_read",
        "cache_write_tokens": "input_tokens_cache_write", "cost": "total_cost",
    }.items():
        metrics[column] = available_sum(getattr(item, field) for item in usage)
    samples = log.samples or []
    for field in ("total_time", "working_time", "turn_count"):
        metrics[field] = available_sum(getattr(s, field) for s in samples)
    model_events, tool_events, requested = [], {}, set()
    event_count = 0
    for index, sample in enumerate(samples):
        seen = set()
        for event in events_recursive(sample.events):
            key = event.uuid or id(event)
            if key in seen:
                continue
            seen.add(key)
            event_count += 1
            if event.event == "model":
                model_events.append(event)
                for call in event.output.message.tool_calls or []:
                    requested.add((index, call.id))
            elif event.event == "tool":
                tool_events[(index, event.id)] = event
    if event_count:
        metrics["model_calls"] = len(model_events)
        all_tools = requested | tool_events.keys()
        metrics["tool_calls"] = len(all_tools)
        # SWE strumenti interni: il bridge registra le richieste nel ModelEvent,
        # ma spesso non emette ToolEvent. Non inferire errori dal testo libero.
        if all_tools and all_tools <= tool_events.keys():
            metrics["tool_errors"] = sum(bool(e.error or e.failed) for e in tool_events.values())
        elif not all_tools:
            metrics["tool_errors"] = 0
    metrics["retries"] = available_sum(e.retries for e in model_events)
    metrics["sample_retries"] = available_sum(len(s.error_retries) if s.error_retries is not None else None
                                               for s in samples)
    errors = ([log.error.message] if log.error else []) + [s.error.message for s in samples if s.error]
    limits = [s.limit.model_dump(mode="json") for s in samples if s.limit]
    metrics["termination_error"] = "\n".join(dict.fromkeys(errors)) or None
    metrics["termination_limit"] = json.dumps(limits) if limits else None
    return metrics
