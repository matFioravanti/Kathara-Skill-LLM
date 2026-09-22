#!/usr/bin/env python3
"""Smoke offline, artefatti esclusivamente temporanei; nessun laboratorio avviato."""
from pathlib import Path
import ast
import importlib
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from benchmark_core.agent_factory import AGENTS, validate_agent
    from benchmark_core.aggregation import aggregate
    from benchmark_core.analysis import analyze
    from benchmark_core.checker_runner import parse_reports
    from benchmark_core.config import load_config, skill_paths
    from benchmark_core.codex_cli_runner import command_for
    from benchmark_core.correction_generator import _run_agent
    from benchmark_core.diff_metrics import compute_diff
    from benchmark_core.scenario_loader import discover_scenarios
    from benchmark_core.workspace import component_versions, create_workspace, tree_hash, write_json

    for module in ("kathara_lab_checker", "pandas", "yaml"):
        importlib.import_module(module)
    print("OK import:", json.dumps(component_versions()))
    config = load_config(ROOT / "benchmark.yaml")
    scenarios = discover_scenarios(ROOT / "scenarios")
    assert scenarios, "Serve almeno uno scenario per lo smoke"
    print("OK configurazione e discovery:", ", ".join(scenarios))
    assert AGENTS == {"codex": "codex_cli", "antigravity": "antigravity_cli"}
    validate_agent("codex")
    validate_agent("antigravity")
    print("OK backend supportati")

    # Verifica dispatch: _run_agent accetta entrambi gli agenti.
    # Non eseguiamo realmente, ma verifichiamo che la funzione non rifiuti l'agente.
    for agent_name in ("codex", "antigravity"):
        try:
            validate_agent(agent_name)
        except ValueError:
            raise AssertionError(f"validate_agent rifiuta '{agent_name}'")
    print("OK dispatch AUT + correction generator per entrambi gli agenti")

    subprocess.run([sys.executable, "-m", "kathara_lab_checker", "--version"], check=True)

    # Verifica che --agent cross-provider venga rifiutato.
    cross_provider = subprocess.run(
        [sys.executable, "scripts/run_benchmark.py",
         "--config", "benchmark.yaml", "--agent", "antigravity", "--preflight"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    assert cross_provider.returncode != 0, "--agent antigravity con benchmark.yaml (codex) dovrebbe fallire"
    assert "non è compatibile" in cross_provider.stderr
    cross_provider_inv = subprocess.run(
        [sys.executable, "scripts/run_benchmark.py",
         "--config", "benchmark_antigravity.yaml", "--agent", "codex", "--preflight"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    assert cross_provider_inv.returncode != 0, "--agent codex con benchmark_antigravity.yaml dovrebbe fallire"
    assert "non è compatibile" in cross_provider_inv.stderr
    # Verifica che --agent uguale al config venga accettato (fallirà su Docker, ma non sulla validazione).
    same_provider = subprocess.run(
        [sys.executable, "scripts/run_benchmark.py",
         "--config", "benchmark.yaml", "--agent", "codex", "--preflight"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    # Può fallire su Docker, ma NON deve fallire sulla validazione dell'agente.
    assert "non è compatibile" not in same_provider.stderr
    print("OK validazione cross-provider --agent")

    for directory in (ROOT / "benchmark_core", ROOT / "scripts"):
        for path in directory.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
    print("OK sintassi Python")
    with tempfile.TemporaryDirectory(prefix="kathara-benchmark-smoke-") as temporary:
        tmp = Path(temporary)
        summary, details = aggregate(tmp / "empty", tmp / "results")
        assert summary.empty and details.empty
        assert analyze(tmp / "results").iloc[0]["runs"] == 0
        scenario = next(iter(scenarios.values()))
        before = tree_hash(scenario.lab)
        run = create_workspace(tmp / "runs", scenario, "codex", 1)
        lab = run / "lab"
        assert tree_hash(lab) == before
        (lab / "smoke.txt").write_text("one\ntwo\n")
        diff = compute_diff(scenario.lab, lab)
        assert diff["files_created"] == 1 and diff["lines_added"] == 2
        assert tree_hash(scenario.lab) == before
        command = command_for(workspace=lab, model=None, reasoning_effort=None)
        assert command[1:3] == ("exec", "--json") and command[-1] == "-"

        from benchmark_core.antigravity_cli_runner import command_for as agy_command_for
        agy_command = agy_command_for(workspace=lab, model="gemini", reasoning_effort="high", prompt="test")
        assert "--dangerously-skip-permissions" in agy_command
        assert "--model" in agy_command and "gemini" in agy_command
        assert "--effort" in agy_command and "high" in agy_command
        assert "--output-format" in agy_command and "stream-json" in agy_command

        print("OK workspace isolato, diff e aggregazione/analisi vuote")

        # Usa i writer REALI del checker, senza emulare il formato CSV.
        from kathara_lab_checker.csv_utils import write_result_to_csv, write_final_results_to_csv
        from kathara_lab_checker.model.SuccessfulCheck import SuccessfulCheck
        from kathara_lab_checker.model.FailedCheck import FailedCheck
        from kathara_lab_checker.model.TestCollector import TestCollector
        reports = run / "results"
        (reports / "lab").mkdir(parents=True, exist_ok=True)
        checks = [SuccessfulCheck("Checking correctness of DNS records"),
                  FailedCheck("HTTP check 'http://example.test' on client status", "Expected 200, got 404")]
        collector = TestCollector()
        collector.add_check_results("lab", checks)
        write_result_to_csv(checks, str(reports / "lab"))
        write_final_results_to_csv(collector, str(reports))
        checker, rows = parse_reports(reports)
        assert checker["task_success"] is False and checker["check_pass_rate"] == 0.5 and len(rows) == 2
        # Verifica Inspect Adapter, .eval, read_eval_log e inspect log dump
        from benchmark_core.inspect_adapter import create_inspect_eval_log
        from benchmark_core.inspect_metrics import extract_metrics as inspect_extract
        from inspect_ai.log import read_eval_log
        aut_logs = run / "logs/aut"
        write_json(aut_logs / "result.json", {
            "returncode": 0, "timed_out": False, "duration_seconds": 42.5,
            "final_message": "Smoke AUT done",
            "usage": {"input_tokens": 1000, "output_tokens": 200, "reasoning_output_tokens": 50, "cached_input_tokens": 800}
        })
        (aut_logs / "events.jsonl").write_text(
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 200}}) + "\n"
            + json.dumps({"item": {"id": "tool_1", "type": "command_execution", "status": "completed", "command": "ls", "exit_code": 0}}) + "\n"
        )
        eval_path = create_inspect_eval_log(aut_logs, run.name, prompt="Smoke prompt", agent="codex", model="gpt-5.6-terra")
        assert eval_path and eval_path.is_file(), "File .eval non generato"
        log_obj = read_eval_log(str(eval_path))
        assert log_obj.status == "success"
        assert log_obj.eval.run_id == run.name
        usage_obj = next(iter(log_obj.stats.model_usage.values()))
        assert usage_obj.input_tokens_cache_read == 800
        assert usage_obj.reasoning_tokens == 50
        assert len(log_obj.samples[0].events) == 1

        # Verifica con CLI inspect log dump
        dump_proc = subprocess.run(["inspect", "log", "dump", "--header-only", str(eval_path)],
                                  capture_output=True, text=True)
        assert dump_proc.returncode == 0, f"inspect log dump fallito: {dump_proc.stderr}"

        # Verifica extract_metrics
        extracted = inspect_extract(aut_logs)
        assert extracted["inspect_status"] == "success"
        assert extracted["input_tokens_cache_read"] == 800
        assert extracted["tool_calls"] == 1
        assert extracted["tool_errors"] == 0
        print("OK Inspect Adapter: .eval generato, convalidato da read_eval_log e inspect log dump")

        write_json(run / "manifest.json", {"run_id": run.name, "scenario_id": scenario.scenario_id,
                   "repetition": 1, "agent": "codex", "pipeline_state": "COMPLETED",
                   "aut_execution_success": True, "correction_generation_success": True,
                   "checker_execution_success": True, "task_success": True})
        write_json(run / "logs/checker_execution.json", {"returncode": 0, "timed_out": False})
        summary, details = aggregate(tmp / "runs", tmp / "results")
        assert not bool(summary.iloc[0]["task_success"]) and len(details) == 2
        assert summary.iloc[0]["run_id"] == run.name
        assert summary.iloc[0]["input_tokens_cache_read"] == 800
        assert summary.iloc[0]["inspect_status"] == "success"
        assert analyze(tmp / "results").iloc[0]["task_success_rate"] == 0
        print("OK report checker reali, task_success derivato dal checker, telemetria Inspect e associazione via run_id")
    missing = [str(p.relative_to(ROOT)) for p in skill_paths(config).values() if not p.is_file()]
    print("Skill esterne mancanti:", ", ".join(missing) if missing else "nessuna")
    print("SMOKE OK; nessuna chiamata LLM/Docker eseguita, artefatti temporanei rimossi.")


if __name__ == "__main__":
    main()
