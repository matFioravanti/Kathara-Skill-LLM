"""Inspect Adapter: converte la telemetria dell'esecuzione LLM/Codex in log nativi Inspect AI (.eval).

Non esegue né avvolge l'AUT: legge result.json ed events.jsonl generati dalla CLI
e produce un file .eval conforme a Inspect AI v2, verificabile tramite read_eval_log
e `inspect log dump`.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

from inspect_ai.event import ToolEvent
from inspect_ai.log import (
    EvalConfig,
    EvalDataset,
    EvalError,
    EvalLog,
    EvalPlan,
    EvalResults,
    EvalSample,
    EvalSpec,
    EvalStats,
    write_eval_log,
)
from inspect_ai.model import ModelOutput, ModelUsage
from inspect_ai.tool import ToolCallError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_inspect_eval_log(
    logs: Path,
    run_id: str,
    prompt: str = "",
    agent: str = "codex",
    model: str | None = None,
) -> Path | None:
    """Crea il log .eval nativo Inspect AI leggendo result.json ed events.jsonl.

    La generazione del log è esclusivamente telemetrica e non altera l'esito dell'AUT.
    """
    try:
        result_path = logs / "result.json"
        events_path = logs / "events.jsonl"
        invocation_path = logs / "invocation.json"
        stderr_path = logs / "stderr.log"

        if not result_path.exists():
            return None

        result = json.loads(result_path.read_text(encoding="utf-8"))
        invocation = json.loads(invocation_path.read_text(encoding="utf-8")) if invocation_path.exists() else {}

        raw_model = model or invocation.get("model") or "unknown"
        provider = "openai" if agent == "codex" else ("google" if agent == "antigravity" else agent)
        inspect_model = f"{provider}/{raw_model}" if "/" not in raw_model else raw_model

        returncode = result.get("returncode", 0)
        timed_out = result.get("timed_out", False)
        duration = float(result.get("duration_seconds", 0.0) or 0.0)
        status = "success" if returncode == 0 and not timed_out else "error"
        final_message = result.get("final_message", "") or ""

        usage = result.get("usage") or {}
        if agent == "antigravity":
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            reasoning_tokens = usage.get("thinking_tokens")
            input_tokens_cache_read = usage.get("cache_read_tokens")
            total_tokens = usage.get("total_tokens")
        else:
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            reasoning_tokens = usage.get("reasoning_output_tokens")
            input_tokens_cache_read = usage.get("cached_input_tokens")
            total_tokens = None
            if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                total_tokens = input_tokens + output_tokens

        model_usage = ModelUsage(
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
            total_tokens=total_tokens or ((input_tokens or 0) + (output_tokens or 0)),
            reasoning_tokens=reasoning_tokens or 0,
            input_tokens_cache_read=input_tokens_cache_read or 0,
            input_tokens_cache_write=0,
            total_cost=0.0,
        )

        tool_events = []
        turn_count = 0
        if events_path.exists():
            seen_tools = {}
            for line in events_path.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if agent == "codex":
                    if event.get("type") == "turn.completed":
                        turn_count += 1
                    item = event.get("item") if isinstance(event, dict) else None
                    if isinstance(item, dict) and item.get("type") in {"command_execution", "mcp_tool_call", "web_search"}:
                        item_id = str(item.get("id", len(seen_tools)))
                        is_failed = item.get("status") == "failed" or (
                            isinstance(item.get("exit_code"), int) and item.get("exit_code") != 0
                        )
                        cmd = item.get("command") or item.get("arguments") or {}
                        out = str(item.get("aggregated_output") or item.get("output") or "")
                        seen_tools[item_id] = ToolEvent(
                            id=item_id,
                            function=item.get("type"),
                            arguments=cmd if isinstance(cmd, dict) else {"cmd": str(cmd)},
                            result=out[:1000] if out else "",
                            failed=is_failed,
                            error=ToolCallError(type="unknown", message=out[:500] or "tool failed") if is_failed else None,
                            timestamp=0.0,
                            working_time=0.0,
                        )
                elif agent == "antigravity":
                    event_type = event.get("event")
                    if event_type == "result":
                        res = event.get("result", {})
                        turn_count = res.get("num_turns", turn_count)
                    elif event_type == "step_update":
                        step = event.get("step_update", {})
                        if step.get("step_type") == "tool":
                            tool_id = str(step.get("step_id") or len(seen_tools))
                            state = step.get("state")
                            is_failed = state == "FAILED"
                            seen_tools[tool_id] = ToolEvent(
                                id=tool_id,
                                function=step.get("tool_name", "tool"),
                                arguments=step.get("inputs") or {},
                                result=str(step.get("outputs", ""))[:1000],
                                failed=is_failed,
                                error=ToolCallError(type="unknown", message="tool failed") if is_failed else None,
                                timestamp=0.0,
                                working_time=0.0,
                            )
            tool_events = list(seen_tools.values())

        stderr_content = stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
        error_obj = None
        if status != "success" and stderr_content.strip():
            error_obj = EvalError(message=stderr_content.strip()[:1000])

        eval_spec = EvalSpec(
            eval_id=run_id,
            run_id=run_id,
            created=utc_now(),
            task="kathara_dns_aut",
            model=inspect_model,
            dataset=EvalDataset(samples=1, sample_ids=[run_id]),
            config=EvalConfig(),
            metadata={
                "agent": agent,
                "execution_backend": invocation.get("execution_backend", f"{agent}_cli"),
                "reasoning_effort": invocation.get("reasoning_effort"),
            },
        )

        prompt_text = prompt
        if not prompt_text and (logs / "prompt.txt").exists():
            prompt_text = (logs / "prompt.txt").read_text(encoding="utf-8")

        sample = EvalSample(
            id=run_id,
            epoch=1,
            input=prompt_text,
            target="",
            output=ModelOutput.from_content(model=inspect_model, content=final_message),
            total_time=duration,
            working_time=duration,
            turn_count=turn_count or 1,
            events=tool_events,
            error=error_obj,
        )

        eval_log = EvalLog(
            eval=eval_spec,
            plan=EvalPlan(name="aut_execution", steps=[]),
            status=status,
            stats=EvalStats(
                started_at=utc_now(),
                completed_at=utc_now(),
                model_usage={inspect_model: model_usage},
            ),
            results=EvalResults(total_samples=1, completed_samples=1 if status == "success" else 0),
            samples=[sample],
            error=error_obj,
        )

        eval_path = logs / f"{run_id}.eval"
        write_eval_log(eval_log, str(eval_path))
        return eval_path
    except Exception as exc:
        print(f"Avviso telemetria Inspect per {run_id}: {exc}", file=sys.stderr)
        return None
